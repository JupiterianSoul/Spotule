"""Worker-free sweeps.

Every background job in Spotule falls into one of two categories:

  * **Periodic** (recently-played logging, catalogue hydration, milestones, weekly
    automations). These only need to run every few minutes, so they can be driven by any
    external scheduler — GitHub Actions, a Cloudflare cron trigger, `cron` on any machine —
    calling the endpoints in `api/v1/cron.py`. No always-on process required.
  * **Continuous** (the real-time skip guard). This polls playback every few seconds and
    genuinely needs a resident process; there is no cron substitute.

The functions here are the periodic half, written so the Celery tasks and the cron endpoints
share one implementation. Each sweep isolates failures per user: one revoked token or one
rate-limited account never aborts the batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import (
    AutomationJob,
    SpotifyCredential,
    Stream,
    ToolRun,
    User,
    UserPreference,
)
from app.models.enums import BackupKind, StreamSource
from app.services.analytics.milestones import detect_milestones
from app.services.catalog import hydrate_missing_artists, upsert_tracks
from app.services.ingest.recently_played import ingest_recently_played
from app.services.spotify import SpotifyClient
from app.services.spotify.auth import get_valid_access_token
from app.services.tools.runner import execute_tool_run

log = get_logger("sweeps")

# Which tool each automation kind runs, and the params it defaults to.
AUTOMATION_TOOLS: dict[str, tuple[str, dict]] = {
    "backup_discover_weekly": ("backup.playlist", {"kind": BackupKind.discover_weekly.value}),
    "backup_release_radar": ("backup.playlist", {"kind": BackupKind.release_radar.value}),
    "liked_songs_snapshot": ("backup.liked_songs", {"kind": BackupKind.manual.value}),
}


@dataclass
class SweepResult:
    processed: int = 0
    failed: int = 0
    detail: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        out: dict = {"processed": self.processed, "failed": self.failed, **self.detail}
        if self.errors:
            out["errors"] = self.errors[:5]
        return out


async def _client_for(db: AsyncSession, user: User) -> SpotifyClient | None:
    """A ready-to-use client for one user, or None if they have no usable link."""
    cred = await db.get(SpotifyCredential, user.id)
    if cred is None or cred.revoked_at is not None:
        return None
    token = await get_valid_access_token(db, cred)
    return SpotifyClient(token)


async def _active_users(db: AsyncSession, limit: int, logger_only: bool = False) -> list[User]:
    q = select(User).join(UserPreference).where(User.is_active.is_(True))
    if logger_only:
        q = q.where(UserPreference.stream_logger_enabled.is_(True))
    return list((await db.execute(q.limit(limit))).scalars().all())


async def sweep_recently_played(db: AsyncSession, max_users: int = 100) -> SweepResult:
    """Pillar 2: poll /me/player/recently-played for every user with the logger enabled."""
    result = SweepResult()
    inserted = 0
    for user in await _active_users(db, max_users, logger_only=True):
        client = await _client_for(db, user)
        if client is None:
            continue
        try:
            async with client:
                inserted += await ingest_recently_played(db, client, user)
            result.processed += 1
        except Exception as exc:  # noqa: BLE001 — one bad account must not stop the sweep
            await db.rollback()
            result.failed += 1
            result.errors.append(f"{user.spotify_id}: {exc}"[:200])
            log.warning("sweep.recently_played.user_failed", user=str(user.id), error=str(exc))
    result.detail["streams_inserted"] = inserted
    return result


async def sweep_catalog(db: AsyncSession, artist_limit: int = 500, track_limit: int = 200) -> SweepResult:
    """Hydrate artist genres and the tracks referenced only by URI from an import."""
    result = SweepResult()
    users = await _active_users(db, 1)
    if not users:
        return result
    client = await _client_for(db, users[0])
    if client is None:
        return result
    try:
        async with client:
            # Catalogue rows are shared, so any linked account's token can fetch them.
            result.detail["artists_hydrated"] = await hydrate_missing_artists(db, client, artist_limit)

            rows = await db.execute(
                select(func.split_part(Stream.spotify_track_uri, ":", 3))
                .where(
                    Stream.track_id.is_(None),
                    Stream.spotify_track_uri.like("spotify:track:%"),
                )
                .distinct()
                .limit(track_limit)
            )
            track_ids = [r[0] for r in rows.all() if r[0]]
            if track_ids:
                await upsert_tracks(db, await client.tracks(track_ids))
            await db.commit()
            result.detail["tracks_hydrated"] = len(track_ids)
        result.processed = 1
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        result.failed = 1
        result.errors.append(str(exc)[:200])
    return result


async def relink_imported_streams(db: AsyncSession, max_rows: int = 200_000) -> int:
    """Attach track_id to imported rows whose track is now in the catalogue."""
    from app.models import Track

    stmt = (
        Stream.__table__.update()
        .where(
            Stream.track_id.is_(None),
            Stream.source == StreamSource.json_import,
            func.split_part(Stream.spotify_track_uri, ":", 3).in_(select(Track.id)),
        )
        .values(track_id=func.split_part(Stream.spotify_track_uri, ":", 3))
    )
    linked = (await db.execute(stmt)).rowcount or 0
    await db.commit()
    return linked


async def sweep_milestones(db: AsyncSession, max_users: int = 100) -> SweepResult:
    result = SweepResult()
    awarded = 0
    for user in await _active_users(db, max_users):
        try:
            awarded += await detect_milestones(db, user.id)
            result.processed += 1
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            result.failed += 1
            result.errors.append(str(exc)[:200])
    result.detail["milestones_awarded"] = awarded
    return result


def automation_is_due(job: AutomationJob, now: datetime) -> bool:
    if not job.enabled or not croniter.is_valid(job.cron):
        return False
    base = job.last_run_at or job.created_at
    return croniter(job.cron, base).get_next(datetime) <= now


async def sweep_automations(db: AsyncSession, max_jobs: int = 50) -> SweepResult:
    """Fire every due per-user automation and run its tool inline."""
    result = SweepResult()
    now = datetime.now(UTC)
    jobs = list(
        (
            await db.execute(
                select(AutomationJob).where(AutomationJob.enabled.is_(True)).limit(max_jobs)
            )
        )
        .scalars()
        .all()
    )
    for job in jobs:
        if croniter.is_valid(job.cron):
            job.next_run_at = croniter(job.cron, job.last_run_at or job.created_at).get_next(datetime)
        if not automation_is_due(job, now):
            continue
        mapping = AUTOMATION_TOOLS.get(job.kind.value)
        if mapping is None:
            job.last_run_at = now  # nothing wired up yet; don't re-evaluate every minute
            continue
        tool_key, defaults = mapping
        user = await db.get(User, job.user_id)
        if user is None:
            continue
        client = await _client_for(db, user)
        if client is None:
            continue
        run = ToolRun(
            user_id=user.id,
            automation_job_id=job.id,
            tool_key=tool_key,
            params={**defaults, **job.config},
        )
        db.add(run)
        await db.flush()
        try:
            async with client:
                await execute_tool_run(db, client, user, run)
            result.processed += 1
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            result.failed += 1
            result.errors.append(str(exc)[:200])
        job.last_run_at = now
    await db.commit()
    return result


async def sweep_all(db: AsyncSession) -> dict:
    """Everything a scheduler needs in one call."""
    ingest = await sweep_recently_played(db)
    catalog = await sweep_catalog(db)
    relinked = await relink_imported_streams(db)
    milestones = await sweep_milestones(db)
    automations = await sweep_automations(db)
    return {
        "recently_played": ingest.as_dict(),
        "catalog": {**catalog.as_dict(), "streams_relinked": relinked},
        "milestones": milestones.as_dict(),
        "automations": automations.as_dict(),
        "ran_at": datetime.now(UTC).isoformat(),
    }
