from __future__ import annotations

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import ImportJob, User, UserPreference
from app.models.enums import JobStatus
from app.services.catalog import hydrate_missing_artists
from app.services.ingest.recently_played import ingest_recently_played
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async, with_user


@celery_app.task(name="ingest.recently_played.fanout")
def recently_played_fanout() -> int:
    async def _ids() -> list[str]:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(User.id)
                .join(UserPreference)
                .where(User.is_active.is_(True), UserPreference.stream_logger_enabled.is_(True))
            )
            return [str(r[0]) for r in rows.all()]

    ids = run_async(_ids())
    for uid in ids:
        recently_played_for_user.delay(uid)
    return len(ids)


@celery_app.task(
    name="ingest.recently_played.user",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 3},
)
def recently_played_for_user(user_id: str) -> int | None:
    return run_async(with_user(user_id, lambda db, user, client: ingest_recently_played(db, client, user)))


@celery_app.task(name="catalog.hydrate")
def catalog_hydrate() -> dict:
    """Uses *any* linked user's token (catalogue data is not user-scoped) to back-fill artist
    genres and imported-track metadata, then relinks imported streams."""
    from sqlalchemy import func

    from app.db.session import SyncSessionLocal
    from app.models import Stream
    from app.services.catalog import upsert_tracks
    from app.services.ingest.json_importer import relink_imported_streams

    async def _run(db, user, client) -> dict:
        artists = await hydrate_missing_artists(db, client)
        # Imported streams referencing unknown tracks → fetch 50 at a time
        rows = await db.execute(
            select(func.split_part(Stream.spotify_track_uri, ":", 3))
            .where(Stream.track_id.is_(None), Stream.spotify_track_uri.like("spotify:track:%"))
            .distinct()
            .limit(200)
        )
        ids = [r[0] for r in rows.all()]
        if ids:
            await upsert_tracks(db, await client.tracks(ids))
        await db.commit()
        return {"artists": artists, "tracks": len(ids)}

    async def _pick_user() -> str | None:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(User.id).where(User.is_active.is_(True)).limit(1))).first()
            return str(row[0]) if row else None

    uid = run_async(_pick_user())
    if not uid:
        return {}
    out = run_async(with_user(uid, _run)) or {}
    with SyncSessionLocal() as sdb:
        for (job_user,) in sdb.execute(
            select(ImportJob.user_id).where(ImportJob.status == JobStatus.succeeded).distinct()
        ).all():
            out["relinked"] = out.get("relinked", 0) + relink_imported_streams(sdb, job_user)
        sdb.commit()
    return out


@celery_app.task(name="analytics.milestones.fanout")
def milestones_fanout() -> int:
    from app.services.analytics.milestones import detect_milestones

    async def _run() -> int:
        async with AsyncSessionLocal() as db:
            ids = [r[0] for r in (await db.execute(select(User.id).where(User.is_active.is_(True)))).all()]
            n = 0
            for uid in ids:
                n += await detect_milestones(db, uid)
            return n

    return run_async(_run())
