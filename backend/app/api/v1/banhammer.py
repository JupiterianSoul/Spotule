from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Locale, Spotify
from app.core.i18n import t
from app.models import BannedArtist, BannedGenre, BlacklistExemption, PurgeRun, SkipEvent, UserPreference
from app.schemas.banhammer import (
    BannedArtistIn,
    BannedGenreIn,
    BannedGenreOut,
    ExemptionIn,
    GuardEventIn,
    PurgeRequest,
    SkipEventOut,
)
from app.services.banhammer.registry import Blacklist
from app.services.banhammer.skip_guard import guard_tick
from app.workers.tasks import banhammer as tasks

router = APIRouter(prefix="/banhammer", tags=["ban-hammer"])


async def load_blacklist(db, user_id) -> Blacklist:
    genres = (await db.execute(select(BannedGenre).where(BannedGenre.user_id == user_id))).scalars().all()
    artists = (await db.execute(select(BannedArtist).where(BannedArtist.user_id == user_id))).scalars().all()
    ex = (
        (await db.execute(select(BlacklistExemption).where(BlacklistExemption.user_id == user_id)))
        .scalars()
        .all()
    )
    return Blacklist.from_rows(genres, artists, ex)


@router.get("/genres", response_model=list[BannedGenreOut])
async def list_genres(user: CurrentUser, db: DB):
    rows = (
        (
            await db.execute(
                select(BannedGenre).where(BannedGenre.user_id == user.id).order_by(BannedGenre.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        BannedGenreOut(id=str(g.id), **{k: getattr(g, k) for k in BannedGenreOut.model_fields if k != "id"})
        for g in rows
    ]


@router.post("/genres", response_model=BannedGenreOut, status_code=201)
async def add_genre(user: CurrentUser, db: DB, body: BannedGenreIn, locale: Locale):
    exists = await db.execute(
        select(BannedGenre).where(
            BannedGenre.user_id == user.id,
            BannedGenre.pattern == body.pattern.lower(),
            BannedGenre.match_mode == body.match_mode,
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, t("banhammer.rule_exists", locale))
    g = BannedGenre(user_id=user.id, **{**body.model_dump(), "pattern": body.pattern.lower()})
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return BannedGenreOut(
        id=str(g.id), **{k: getattr(g, k) for k in BannedGenreOut.model_fields if k != "id"}
    )


@router.delete("/genres/{rule_id}", status_code=204)
async def delete_genre(user: CurrentUser, db: DB, rule_id: uuid.UUID):
    g = await db.get(BannedGenre, rule_id)
    if g and g.user_id == user.id:
        await db.delete(g)
        await db.commit()


@router.post("/artists", status_code=201)
async def ban_artist(user: CurrentUser, db: DB, body: BannedArtistIn):
    db.add(BannedArtist(user_id=user.id, **body.model_dump()))
    await db.commit()
    return {"ok": True}


@router.post("/exemptions", status_code=201)
async def add_exemption(user: CurrentUser, db: DB, body: ExemptionIn):
    db.add(BlacklistExemption(user_id=user.id, **body.model_dump()))
    await db.commit()
    return {"ok": True}


@router.post("/purge")
async def purge(user: CurrentUser, db: DB, body: PurgeRequest):
    run = PurgeRun(user_id=user.id, **body.model_dump())
    db.add(run)
    await db.commit()
    tasks.run_purge_task.delay(str(run.id))
    return {"run_id": str(run.id), "status": run.status.value, "dry_run": run.dry_run}


@router.get("/purge/{run_id}")
async def purge_status(user: CurrentUser, db: DB, run_id: uuid.UUID):
    run = await db.get(PurgeRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404)
    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "dry_run": run.dry_run,
        "scanned": run.scanned_count,
        "matched": run.matched_count,
        "removed": run.removed_count,
        "report": run.report,
        "backup_id": str(run.backup_id) if run.backup_id else None,
        "error": run.error,
    }


@router.post("/guard/toggle")
async def toggle_guard(user: CurrentUser, db: DB, enabled: bool, locale: Locale):
    if enabled and user.product != "premium":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, t("banhammer.premium_required", locale))
    pref = await db.get(UserPreference, user.id)
    pref.skip_guard_enabled = enabled
    await db.commit()
    tasks.refresh_guard_roster.delay()
    return {"enabled": enabled}


@router.post("/guard/event")
async def guard_event(user: CurrentUser, db: DB, client: Spotify, body: GuardEventIn):
    """Web Playback SDK bridge — zero-latency path when the dashboard tab is open."""
    bl = await load_blacklist(db, user.id)
    tick = await guard_tick(db, client, user.id, bl, state=body.state)
    return {"skipped": tick.skipped, "track_id": tick.track_id}


@router.get("/guard/events", response_model=list[SkipEventOut])
async def guard_events(user: CurrentUser, db: DB, limit: int = 50):
    rows = (
        (
            await db.execute(
                select(SkipEvent)
                .where(SkipEvent.user_id == user.id)
                .order_by(SkipEvent.detected_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [SkipEventOut.model_validate(r) for r in rows]
