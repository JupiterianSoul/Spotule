"""Executes any registered tool with audit, progress and automatic pre-run backups."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.session import AsyncSessionLocal
from app.models import PlaylistBackup, ToolRun
from app.models.enums import BackupKind, JobStatus
from app.services.tools import ToolContext, registry
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async, with_user


@celery_app.task(name="tools.run", time_limit=3600)
def run_tool_task(run_id: str) -> None:
    async def _owner() -> str | None:
        async with AsyncSessionLocal() as db:
            run = await db.get(ToolRun, uuid.UUID(run_id))
            return str(run.user_id) if run else None

    async def _run(db, user, client):
        run = await db.get(ToolRun, uuid.UUID(run_id))
        tool_cls = registry.get(run.tool_key)
        tool = tool_cls()
        params = tool_cls.Params.model_validate(run.params)
        run.status, run.started_at = JobStatus.running, datetime.now(UTC)
        await db.commit()

        def progress(pct: int, msg: str | None = None) -> None:
            run.progress = max(0, min(100, int(pct)))

        try:
            if tool_cls.destructive:
                for pid in await tool.backup_targets(params):
                    uris = [
                        i["item"]["uri"]
                        async for i in client.playlist_items(pid)
                        if i.get("item") and i["item"].get("uri")
                    ]
                    name = (await client.playlist(pid))["name"]
                    b = PlaylistBackup(
                        user_id=user.id,
                        kind=BackupKind.pre_bulk,
                        source_playlist_id=pid,
                        source_name=name,
                        track_uris=uris,
                        track_count=len(uris),
                        meta={"tool_run_id": run_id, "tool": run.tool_key},
                    )
                    db.add(b)
                    await db.flush()
                    run.backup_id = b.id
                await db.commit()
            ctx = ToolContext(db=db, client=client, user=user, run_id=run_id, report_progress=progress)
            run.result = await tool.run(ctx, params)
            run.status, run.progress = JobStatus.succeeded, 100
        except Exception as exc:  # noqa: BLE001
            run.status, run.error = JobStatus.failed, str(exc)[:1000]
        run.finished_at = datetime.now(UTC)
        await db.commit()

    uid = run_async(_owner())
    if uid:
        run_async(with_user(uid, _run))
