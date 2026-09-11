"""Listening clocks: 24×7 heatmap in the user's own timezone."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StreamHourlyRollup


async def listening_clock(db: AsyncSession, user_id, tz: str, start: datetime | None, end: datetime) -> dict:
    zone = ZoneInfo(tz or "UTC")
    q = select(
        StreamHourlyRollup.bucket_start, StreamHourlyRollup.streams, StreamHourlyRollup.ms_played
    ).where(StreamHourlyRollup.user_id == user_id, StreamHourlyRollup.bucket_start <= end)
    if start:
        q = q.where(StreamHourlyRollup.bucket_start >= start)
    grid = [[0] * 24 for _ in range(7)]  # [weekday][hour] streams
    minutes = [[0.0] * 24 for _ in range(7)]
    for bucket, streams, ms in (await db.execute(q)).all():
        local = bucket.astimezone(zone)
        grid[local.weekday()][local.hour] += streams
        minutes[local.weekday()][local.hour] += ms / 60000
    by_hour = [sum(grid[d][h] for d in range(7)) for h in range(24)]
    by_weekday = [sum(grid[d]) for d in range(7)]
    return {
        "timezone": tz,
        "grid": grid,
        "minutes": minutes,
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "peak_hour": max(range(24), key=by_hour.__getitem__),
        "peak_weekday": max(range(7), key=by_weekday.__getitem__),
    }
