"""Deep metric dashboards. Every response is cached in Redis for 10 min per (user, params)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

import orjson
from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.db.redis import Keys, get_redis
from app.models import Milestone, UserPreference
from app.services.analytics import clock, leaderboard, top
from app.services.analytics.timeframes import Preset, resolve

router = APIRouter(prefix="/stats", tags=["stats"])
CACHE_TTL = 600


async def _cached(user_id, name: str, params: dict, compute):
    digest = hashlib.sha1(f"{name}:{json.dumps(params, default=str, sort_keys=True)}".encode()).hexdigest()
    r = get_redis()
    hit = await r.get(Keys.stats(str(user_id), digest))
    if hit:
        return orjson.loads(hit)
    data = await compute()
    await r.set(Keys.stats(str(user_id), digest), orjson.dumps(data, default=str), ex=CACHE_TTL)
    return data


def _tf(preset: Preset, start: datetime | None, end: datetime | None):
    return resolve(preset, start, end)


@router.get("/overview")
async def overview(
    user: CurrentUser,
    db: DB,
    preset: Preset = "4w",
    start: datetime | None = None,
    end: datetime | None = None,
):
    s, e = _tf(preset, start, end)
    return await _cached(
        user.id, "overview", {"p": preset, "s": s, "e": e}, lambda: top.overview(db, user.id, s, e)
    )


@router.get("/top/{kind}")
async def top_items(
    user: CurrentUser,
    db: DB,
    kind: Literal["tracks", "artists", "albums", "genres"],
    preset: Preset = "4w",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    s, e = _tf(preset, start, end)
    fn = {"tracks": top.top_tracks, "artists": top.top_artists, "albums": top.top_albums}.get(kind)
    if kind == "genres":
        return await _cached(
            user.id,
            "top_genres",
            {"p": preset, "s": s, "e": e, "l": limit},
            lambda: top.top_genres(db, user.id, s, e, limit),
        )
    return await _cached(
        user.id,
        f"top_{kind}",
        {"p": preset, "s": s, "e": e, "l": limit, "o": offset},
        lambda: fn(db, user.id, s, e, limit, offset),
    )


@router.get("/clock")
async def listening_clock(
    user: CurrentUser,
    db: DB,
    preset: Preset = "lifetime",
    start: datetime | None = None,
    end: datetime | None = None,
):
    s, e = _tf(preset, start, end)
    pref = await db.get(UserPreference, user.id)
    tz = pref.timezone if pref else "UTC"
    return await _cached(
        user.id,
        "clock",
        {"p": preset, "s": s, "e": e, "tz": tz},
        lambda: clock.listening_clock(db, user.id, tz, s, e),
    )


@router.get("/milestones")
async def milestones(user: CurrentUser, db: DB, limit: int = 50):
    rows = (
        (
            await db.execute(
                select(Milestone)
                .where(Milestone.user_id == user.id)
                .order_by(Milestone.achieved_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(m.id),
            "kind": m.kind.value,
            "threshold": m.threshold,
            "entity_id": m.entity_id,
            "entity_name": m.entity_name,
            "achieved_at": m.achieved_at,
            "value": m.value_at_achievement,
            "new": not m.notified,
        }
        for m in rows
    ]


@router.post("/milestones/seen", status_code=204)
async def milestones_seen(user: CurrentUser, db: DB):
    """The dashboard calls this once it has shown the 'new milestones' badge."""
    from sqlalchemy import update

    await db.execute(
        update(Milestone)
        .where(Milestone.user_id == user.id, Milestone.notified.is_(False))
        .values(notified=True)
    )
    await db.commit()


@router.get("/leaderboard")
async def board(
    user: CurrentUser,
    db: DB,
    scope: Literal["friends", "global"] = "friends",
    metric: Literal["minutes", "streams"] = "minutes",
    preset: Preset = "4w",
    start: datetime | None = None,
    end: datetime | None = None,
):
    s, e = _tf(preset, start, end)
    return await _cached(
        user.id,
        "leaderboard",
        {"sc": scope, "m": metric, "p": preset, "s": s, "e": e},
        lambda: leaderboard.leaderboard(db, user.id, s, e, scope, metric),
    )
