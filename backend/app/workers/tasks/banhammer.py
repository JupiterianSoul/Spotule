"""Skip-guard scheduling. Each active user has a self-rescheduling tick on the `realtime`
queue; the roster task (every 30 s) starts ticks for users who enabled the guard and stops
them when they disable it or go idle for a long time."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.config import settings
from app.db.redis import Keys, get_sync_redis
from app.db.session import AsyncSessionLocal
from app.models import BannedArtist, BannedGenre, BlacklistExemption, PurgeRun, User, UserPreference
from app.services.banhammer.purger import run_purge
from app.services.banhammer.registry import Blacklist
from app.services.banhammer.skip_guard import guard_tick
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async, with_user

_LOCK_TTL = 15


@celery_app.task(name="guard.refresh_roster")
def refresh_guard_roster() -> int:
    async def _ids() -> list[str]:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(User.id)
                .join(UserPreference)
                .where(
                    User.is_active.is_(True),
                    UserPreference.skip_guard_enabled.is_(True),
                    User.product == "premium",
                )
                .limit(settings.skip_guard_max_active_users)
            )
            return [str(r[0]) for r in rows.all()]

    r = get_sync_redis()
    ids = run_async(_ids())
    current = set(r.smembers(Keys.GUARD_ACTIVE))
    for uid in ids:
        if uid not in current:
            r.sadd(Keys.GUARD_ACTIVE, uid)
            guard_tick_task.apply_async(args=[uid], queue="realtime")
    for uid in current - set(ids):
        r.srem(Keys.GUARD_ACTIVE, uid)
    return len(ids)


@celery_app.task(name="guard.tick", ignore_result=True)
def guard_tick_task(user_id: str) -> None:
    r = get_sync_redis()
    if not r.sismember(Keys.GUARD_ACTIVE, user_id):
        return  # disabled since scheduling
    lock = f"guard:{user_id}:lock"
    if not r.set(lock, "1", nx=True, ex=_LOCK_TTL):
        return  # another tick is in flight

    async def _run(db, user, client):
        bl = await _load_blacklist(db, user.id)
        return await guard_tick(db, client, user.id, bl)

    try:
        tick = run_async(with_user(user_id, _run, priority=True))
        delay = tick.next_poll_seconds if tick else settings.skip_guard_heartbeat_seconds * 5
    except Exception:  # noqa: BLE001 — never let one user's error stop their guard
        delay = settings.skip_guard_heartbeat_seconds * 3
    finally:
        r.delete(lock)
    guard_tick_task.apply_async(args=[user_id], countdown=delay, queue="realtime")


async def _load_blacklist(db, user_id: uuid.UUID) -> Blacklist:
    genres = (await db.execute(select(BannedGenre).where(BannedGenre.user_id == user_id))).scalars().all()
    artists = (await db.execute(select(BannedArtist).where(BannedArtist.user_id == user_id))).scalars().all()
    ex = (
        (await db.execute(select(BlacklistExemption).where(BlacklistExemption.user_id == user_id)))
        .scalars()
        .all()
    )
    return Blacklist.from_rows(genres, artists, ex)


@celery_app.task(name="banhammer.purge")
def run_purge_task(run_id: str) -> None:
    async def _run(db, user, client):
        run = await db.get(PurgeRun, uuid.UUID(run_id))
        if run is None:
            return
        bl = await _load_blacklist(db, user.id)
        await run_purge(db, client, run, bl)

    async def _owner() -> str | None:
        async with AsyncSessionLocal() as db:
            run = await db.get(PurgeRun, uuid.UUID(run_id))
            return str(run.user_id) if run else None

    uid = run_async(_owner())
    if uid:
        run_async(with_user(uid, _run))
