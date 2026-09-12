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
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import redact
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

# How many linked accounts to try before reporting catalogue hydration as failed.
CATALOG_ACCOUNT_ATTEMPTS = 5

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
    """Users to sweep, detached from the session on purpose.

    A rollback expires every instance still attached to the session. The sweeps roll back
    whenever one user fails, so the users queued behind them would be left needing a silent
    refresh — and a refresh is IO, which under asyncio raises MissingGreenlet from whatever
    innocent line happened to touch the attribute. That error then escaped the per-user guard
    and failed the whole sweep, hiding the original failure completely.

    Every column is loaded here and never written back, so detaching costs nothing and makes
    the loops immune to what the session does between iterations.
    """
    q = select(User).join(UserPreference).where(User.is_active.is_(True))
    if logger_only:
        q = q.where(UserPreference.stream_logger_enabled.is_(True))
    users = list((await db.execute(q.limit(limit))).scalars().all())
    for user in users:
        db.expunge(user)
    return users


async def sweep_recently_played(db: AsyncSession, max_users: int = 100) -> SweepResult:
    """Pillar 2: poll /me/player/recently-played for every user with the logger enabled."""
    result = SweepResult()
    inserted = 0
    for user in await _active_users(db, max_users, logger_only=True):
        try:
            # Inside the guard on purpose: this refreshes the Spotify token, so it fails for a
            # revoked or expired grant. Outside, one stale account returned 500 for the whole
            # sweep and nothing was ingested for anyone.
            client = await _client_for(db, user)
            if client is None:
                continue
            async with client:
                inserted += await ingest_recently_played(db, client, user)
            result.processed += 1
        except Exception as exc:  # noqa: BLE001 — one bad account must not stop the sweep
            await db.rollback()
            result.failed += 1
            result.errors.append(redact(f"{user.spotify_id}: {exc}", 200))
            log.warning("sweep.recently_played.user_failed", user=str(user.id), error=str(exc))
    result.detail["streams_inserted"] = inserted
    return result


async def hydrate_orphan_tracks(db: AsyncSession, client: SpotifyClient, limit: int) -> int:
    """Fill in metadata for streams that carry only a track URI, as an import leaves them."""
    rows = await db.execute(
        select(func.split_part(Stream.spotify_track_uri, ":", 3))
        .where(
            Stream.track_id.is_(None),
            Stream.spotify_track_uri.like("spotify:track:%"),
        )
        .distinct()
        .limit(limit)
    )
    track_ids = [r[0] for r in rows.all() if r[0]]
    if track_ids:
        await upsert_tracks(db, await client.tracks(track_ids))
    return len(track_ids)


async def sweep_catalog(db: AsyncSession, artist_limit: int = 500, track_limit: int = 200) -> SweepResult:
    """Hydrate artist genres and the tracks referenced only by URI from an import.

    Catalogue rows are shared between everyone, so any linked account's token can fetch them
    — and that cuts both ways: betting the whole stage on one arbitrarily chosen account
    meant a single account Spotify refuses stopped catalogue hydration for every user, every
    sweep, forever. Accounts are tried in turn until one is usable.

    The two halves are independent because they fail for different reasons. An account with
    a dead grant fails both; an endpoint Spotify refuses for the *application* fails one and
    would keep working through every account to no purpose. Production hit the second case —
    403 on GET /artists — and it cost the track hydration that never got to run.
    """
    result = SweepResult()
    errors: list[str] = []
    for user in await _active_users(db, CATALOG_ACCOUNT_ATTEMPTS):
        try:
            client = await _client_for(db, user)
        except Exception as exc:  # noqa: BLE001 — a dead grant: try the next account
            await db.rollback()
            errors.append(redact(f"{user.spotify_id}: {exc}", 200))
            continue
        if client is None:
            continue

        halves = (
            ("artists", lambda c: hydrate_missing_artists(db, c, artist_limit)),
            ("tracks", lambda c: hydrate_orphan_tracks(db, c, track_limit)),
        )
        succeeded = 0
        async with client:
            for name, work in halves:
                try:
                    result.detail[f"{name}_hydrated"] = await work(client)
                    await db.commit()
                    succeeded += 1
                except Exception as exc:  # noqa: BLE001
                    await db.rollback()
                    errors.append(redact(f"{user.spotify_id} {name}: {exc}", 200))
                    log.warning("sweep.catalog.failed", half=name, user=str(user.id), error=str(exc))
        if succeeded:
            # The account itself is fine. Anything still failing is the endpoint, and no
            # other account would answer it differently.
            result.processed = 1
            break
    result.failed = 1 if errors else 0
    result.errors = errors
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
            result.errors.append(redact(str(exc), 200))
    result.detail["milestones_awarded"] = awarded
    return result


def automation_is_due(job: AutomationJob, now: datetime) -> bool:
    if not job.enabled or not croniter.is_valid(job.cron):
        return False
    base = job.last_run_at or job.created_at
    return croniter(job.cron, base).get_next(datetime) <= now


async def sweep_automations(db: AsyncSession, max_jobs: int = 50) -> SweepResult:
    """Fire every due per-user automation and run its tool inline.

    Each job gets its own transaction. Sharing one meant a rollback for the job that failed
    also threw away the bookkeeping of every job already handled, so those would fire again
    on the next sweep; and it expired the job rows still waiting their turn, which turned the
    next attribute read into IO that asyncio cannot perform there.
    """
    result = SweepResult()
    now = datetime.now(UTC)
    jobs = list(
        (await db.execute(select(AutomationJob).where(AutomationJob.enabled.is_(True)).limit(max_jobs)))
        .scalars()
        .all()
    )
    # Everything the loop needs, read out while the rows are certainly loaded.
    plan = [
        (
            job.id,
            job.user_id,
            job.kind.value,
            dict(job.config),
            automation_is_due(job, now),
            croniter(job.cron, job.last_run_at or job.created_at).get_next(datetime)
            if croniter.is_valid(job.cron)
            else None,
        )
        for job in jobs
    ]
    for job_id, _user, _kind, _config, _due, next_run in plan:
        if next_run is not None:
            await db.execute(
                update(AutomationJob).where(AutomationJob.id == job_id).values(next_run_at=next_run)
            )
    await db.commit()

    async def mark_ran(job_id) -> None:
        await db.execute(
            update(AutomationJob).where(AutomationJob.id == job_id).values(last_run_at=now)
        )
        await db.commit()

    for job_id, user_id, kind, config, due, _next in plan:
        if not due:
            continue
        mapping = AUTOMATION_TOOLS.get(kind)
        if mapping is None:
            await mark_ran(job_id)  # nothing wired up yet; don't re-evaluate every minute
            continue
        tool_key, defaults = mapping
        try:
            user = await db.get(User, user_id)
            if user is None:
                continue
            # Inside the guard: this refreshes the Spotify token over HTTP, so a stale grant
            # fails here and must cost only this job.
            client = await _client_for(db, user)
            if client is None:
                continue
            run = ToolRun(
                user_id=user_id,
                automation_job_id=job_id,
                tool_key=tool_key,
                params={**defaults, **config},
            )
            db.add(run)
            await db.flush()
            async with client:
                await execute_tool_run(db, client, user, run)
            result.processed += 1
        except Exception as exc:  # noqa: BLE001 — one job must not stop the rest
            await db.rollback()
            result.failed += 1
            result.errors.append(redact(str(exc), 200))
        await mark_ran(job_id)
    return result


async def _stage(db: AsyncSession, name: str, coro) -> dict:
    """Run one sweep stage, reporting a failure instead of aborting the others.

    The rollback matters as much as the catch: Postgres refuses every statement on a
    connection whose transaction has already errored, so without it the first broken stage
    would take all the later ones down with it for a reason unrelated to their own work.
    """
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        log.exception("sweep.stage_failed", stage=name)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001 — the session may already be unusable
            pass
        return {"processed": 0, "failed": 1, "errors": [redact(str(exc), 300)]}


async def sweep_all(db: AsyncSession) -> dict:
    """Everything a scheduler needs in one call.

    Stages are independent: ingestion failing must not cost you milestones or backups, and a
    scheduler that reports which stage broke is far easier to act on than a bare 500.
    """

    async def _relink() -> dict:
        return {"processed": 1, "failed": 0, "streams_relinked": await relink_imported_streams(db)}

    async def _as_dict(coro) -> dict:
        return (await coro).as_dict()

    catalog = await _stage(db, "catalog", _as_dict(sweep_catalog(db)))
    relinked = await _stage(db, "relink", _relink())
    return {
        "recently_played": await _stage(db, "recently_played", _as_dict(sweep_recently_played(db))),
        "catalog": {**catalog, "streams_relinked": relinked.get("streams_relinked", 0)},
        "milestones": await _stage(db, "milestones", _as_dict(sweep_milestones(db))),
        "automations": await _stage(db, "automations", _as_dict(sweep_automations(db))),
        "ran_at": datetime.now(UTC).isoformat(),
    }
