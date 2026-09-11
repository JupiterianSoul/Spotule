"""Executes a queued ToolRun: pre-run backup for destructive tools, run, audit.

Shared by both drivers so there is exactly one implementation of the semantics:
  * the Celery task `tools.run` (used when a worker process is available), and
  * the cron endpoint `/api/v1/cron/automations` (used on hosts with no worker,
    see docs/DEPLOYMENT.md — "Running without a worker").
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlaylistBackup, ToolRun, User
from app.models.enums import BackupKind, JobStatus
from app.services.spotify import SpotifyClient
from app.services.tools.base import ToolContext, registry


async def execute_tool_run(
    db: AsyncSession, client: SpotifyClient, user: User, run: ToolRun
) -> ToolRun:
    tool_cls = registry.get(run.tool_key)
    tool = tool_cls()
    params = tool_cls.Params.model_validate(run.params)

    run.status = JobStatus.running
    run.started_at = datetime.now(UTC)
    await db.commit()

    def progress(pct: int, msg: str | None = None) -> None:
        run.progress = max(0, min(100, int(pct)))

    try:
        if tool_cls.destructive:
            for playlist_id in await tool.backup_targets(params):
                uris = [
                    item["item"]["uri"]
                    async for item in client.playlist_items(playlist_id)
                    if item.get("item") and item["item"].get("uri")
                ]
                name = (await client.playlist(playlist_id))["name"]
                backup = PlaylistBackup(
                    user_id=user.id,
                    kind=BackupKind.pre_bulk,
                    source_playlist_id=playlist_id,
                    source_name=name,
                    track_uris=uris,
                    track_count=len(uris),
                    meta={"tool_run_id": str(run.id), "tool": run.tool_key},
                )
                db.add(backup)
                await db.flush()
                run.backup_id = backup.id
            await db.commit()

        ctx = ToolContext(
            db=db, client=client, user=user, run_id=str(run.id), report_progress=progress
        )
        run.result = await tool.run(ctx, params)
        run.status = JobStatus.succeeded
        run.progress = 100
    except Exception as exc:  # noqa: BLE001 — recorded on the audit row, never re-raised
        run.status = JobStatus.failed
        run.error = str(exc)[:1000]

    run.finished_at = datetime.now(UTC)
    await db.commit()
    return run
