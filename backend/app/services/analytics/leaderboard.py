"""Global / friends comparison. Only users who opted in are ever visible to others."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FriendLink, Stream, Track, User, UserPreference
from app.models.enums import FriendStatus
from app.services.analytics.top import COUNTS_AS_STREAM


async def leaderboard(
    db: AsyncSession,
    viewer_id,
    start: datetime | None,
    end: datetime,
    scope: str = "friends",
    metric: str = "minutes",
    limit: int = 25,
) -> list[dict]:
    if scope == "friends":
        friend_ids = select(FriendLink.friend_user_id).where(
            FriendLink.user_id == viewer_id, FriendLink.status == FriendStatus.accepted
        )
        visible = select(UserPreference.user_id).where(
            UserPreference.share_stats_with_friends.is_(True), UserPreference.user_id.in_(friend_ids)
        )
    else:
        visible = select(UserPreference.user_id).where(UserPreference.share_stats_globally.is_(True))

    value = (
        func.coalesce(func.sum(func.coalesce(Stream.ms_played, Track.duration_ms)), 0) / 60000
        if metric == "minutes"
        else func.count()
    )
    q = (
        select(User.id, User.display_name, User.avatar_url, value.label("value"))
        .join(Stream, Stream.user_id == User.id)
        .outerjoin(Track, Track.id == Stream.track_id)
        .where((User.id.in_(visible)) | (User.id == viewer_id), COUNTS_AS_STREAM, Stream.played_at <= end)
    )
    if start:
        q = q.where(Stream.played_at >= start)
    q = q.group_by(User.id, User.display_name, User.avatar_url).order_by(value.desc()).limit(limit)
    rows = (await db.execute(q)).all()
    return [
        {
            "rank": i + 1,
            "user_id": str(r.id),
            "display_name": r.display_name,
            "avatar_url": r.avatar_url,
            "value": float(r.value),
            "is_me": r.id == viewer_id,
        }
        for i, r in enumerate(rows)
    ]
