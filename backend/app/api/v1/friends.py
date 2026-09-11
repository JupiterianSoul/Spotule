"""Friends: find people on this instance, send and accept requests, compare stats.

Links are stored as directed rows. A request creates one pending row (me -> them); accepting
it flips that row to accepted and inserts the mirror row, so both directions are accepted and
the leaderboard query, which filters on `FriendLink.user_id == viewer`, works from either side.
Declining or removing deletes both directions.

Finding someone only reveals their display name and avatar, which Spotify already shows on
their public profile. Listening data is gated separately by `share_stats_with_friends`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, or_, select

from app.api.deps import DB, CurrentUser, Locale
from app.core.i18n import t
from app.models import FriendLink, User, UserPreference
from app.models.enums import FriendStatus

router = APIRouter(prefix="/friends", tags=["friends"])


class PersonOut(BaseModel):
    user_id: str
    display_name: str | None
    avatar_url: str | None
    spotify_id: str
    shares_stats: bool = True


class LinkOut(BaseModel):
    link_id: str
    person: PersonOut
    status: str
    direction: str  # "outgoing" | "incoming" | "mutual"


class RequestIn(BaseModel):
    user_id: str | None = None
    spotify_id: str | None = None


def _person(user: User, shares: bool = True) -> PersonOut:
    return PersonOut(
        user_id=str(user.id),
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        spotify_id=user.spotify_id,
        shares_stats=shares,
    )


@router.get("/search", response_model=list[PersonOut])
async def search(user: CurrentUser, db: DB, q: str = Query(min_length=2, max_length=64)):
    """Match on display name (partial, case-insensitive) or exact Spotify user id.
    The Spotify id is the last part of a profile URL: open.spotify.com/user/<id>."""
    pattern = f"%{q.strip()}%"
    rows = await db.execute(
        select(User)
        .where(
            User.is_active.is_(True),
            User.id != user.id,
            or_(User.display_name.ilike(pattern), User.spotify_id == q.strip()),
        )
        .order_by(User.display_name)
        .limit(20)
    )
    return [_person(u) for u in rows.scalars().all()]


@router.get("", response_model=list[LinkOut])
async def list_links(user: CurrentUser, db: DB):
    """Everything involving me: friends, requests I sent, requests waiting for my answer."""
    links = (
        (
            await db.execute(
                select(FriendLink)
                .where(or_(FriendLink.user_id == user.id, FriendLink.friend_user_id == user.id))
                .order_by(FriendLink.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    other_ids = {(link.friend_user_id if link.user_id == user.id else link.user_id) for link in links}
    if not other_ids:
        return []
    people = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(other_ids)))).scalars()}
    prefs = {
        p.user_id: p
        for p in (
            await db.execute(select(UserPreference).where(UserPreference.user_id.in_(other_ids)))
        ).scalars()
    }
    seen: set[uuid.UUID] = set()
    out: list[LinkOut] = []
    for link in links:
        other_id = link.friend_user_id if link.user_id == user.id else link.user_id
        other = people.get(other_id)
        if other is None or other_id in seen:
            continue  # accepted pairs have two rows; show the person once
        seen.add(other_id)
        if link.status == FriendStatus.accepted:
            direction = "mutual"
        elif link.user_id == user.id:
            direction = "outgoing"
        else:
            direction = "incoming"
        pref = prefs.get(other_id)
        out.append(
            LinkOut(
                link_id=str(link.id),
                person=_person(other, pref.share_stats_with_friends if pref else True),
                status=link.status.value,
                direction=direction,
            )
        )
    return out


@router.post("/requests", response_model=LinkOut, status_code=201)
async def send_request(user: CurrentUser, db: DB, locale: Locale, body: RequestIn):
    if not body.user_id and not body.spotify_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, t("friends.target_required", locale))
    q = select(User).where(User.is_active.is_(True))
    if body.user_id:
        try:
            q = q.where(User.id == uuid.UUID(body.user_id))
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, t("friends.not_found", locale)) from exc
    else:
        q = q.where(User.spotify_id == body.spotify_id)
    target = (await db.execute(q)).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("friends.not_found", locale))
    if target.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, t("friends.not_yourself", locale))

    existing = (
        (
            await db.execute(
                select(FriendLink).where(
                    or_(
                        (FriendLink.user_id == user.id) & (FriendLink.friend_user_id == target.id),
                        (FriendLink.user_id == target.id) & (FriendLink.friend_user_id == user.id),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for link in existing:
        if link.status == FriendStatus.blocked:
            raise HTTPException(status.HTTP_403_FORBIDDEN, t("friends.blocked", locale))
        if link.status == FriendStatus.accepted:
            raise HTTPException(status.HTTP_409_CONFLICT, t("friends.already_friends", locale))
        if link.user_id == target.id:
            # They already asked me: treat my request as acceptance.
            return await _accept(db, user, link, target)
        raise HTTPException(status.HTTP_409_CONFLICT, t("friends.already_requested", locale))

    link = FriendLink(user_id=user.id, friend_user_id=target.id, status=FriendStatus.pending)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return LinkOut(link_id=str(link.id), person=_person(target), status="pending", direction="outgoing")


async def _accept(db, me: User, link: FriendLink, other: User) -> LinkOut:
    link.status = FriendStatus.accepted
    mirror = (
        await db.execute(
            select(FriendLink).where(FriendLink.user_id == me.id, FriendLink.friend_user_id == other.id)
        )
    ).scalar_one_or_none()
    if mirror is None:
        db.add(FriendLink(user_id=me.id, friend_user_id=other.id, status=FriendStatus.accepted))
    else:
        mirror.status = FriendStatus.accepted
    await db.commit()
    return LinkOut(link_id=str(link.id), person=_person(other), status="accepted", direction="mutual")


@router.post("/requests/{link_id}/accept", response_model=LinkOut)
async def accept_request(user: CurrentUser, db: DB, locale: Locale, link_id: uuid.UUID):
    link = await db.get(FriendLink, link_id)
    if link is None or link.friend_user_id != user.id or link.status != FriendStatus.pending:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("friends.not_found", locale))
    other = await db.get(User, link.user_id)
    if other is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("friends.not_found", locale))
    return await _accept(db, user, link, other)


@router.delete("/{other_user_id}", status_code=204)
async def remove(user: CurrentUser, db: DB, other_user_id: uuid.UUID):
    """Decline an incoming request, cancel an outgoing one, or unfriend. Idempotent."""
    await db.execute(
        delete(FriendLink).where(
            or_(
                (FriendLink.user_id == user.id) & (FriendLink.friend_user_id == other_user_id),
                (FriendLink.user_id == other_user_id) & (FriendLink.friend_user_id == user.id),
            ),
            FriendLink.status != FriendStatus.blocked,
        )
    )
    await db.commit()
