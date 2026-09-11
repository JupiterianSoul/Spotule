"""Milestone detection. Runs after every ingest batch; idempotent via `uq_milestone_once`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Artist, Milestone, Stream, Track, TrackArtist
from app.models.enums import MilestoneKind
from app.services.analytics.top import COUNTS_AS_STREAM

THRESHOLDS: dict[MilestoneKind, list[int]] = {
    MilestoneKind.total_minutes: [1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000],
    MilestoneKind.total_streams: [1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000],
    MilestoneKind.artist_streams: [100, 250, 500, 1_000, 2_500, 5_000, 10_000],
    MilestoneKind.track_streams: [50, 100, 250, 500, 1_000],
    MilestoneKind.unique_artists: [100, 500, 1_000, 2_500, 5_000],
    MilestoneKind.unique_tracks: [500, 1_000, 5_000, 10_000, 25_000],
}


async def detect_milestones(db: AsyncSession, user_id) -> int:
    now = datetime.now(UTC)
    rows: list[dict] = []

    total = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(func.coalesce(Stream.ms_played, Track.duration_ms)), 0) / 60000,
                func.count(func.distinct(Stream.track_id)),
            )
            .outerjoin(Track, Track.id == Stream.track_id)
            .where(Stream.user_id == user_id, COUNTS_AS_STREAM)
        )
    ).one()
    streams, minutes, unique_tracks = int(total[0]), int(total[1]), int(total[2])
    for kind, value in (
        (MilestoneKind.total_streams, streams),
        (MilestoneKind.total_minutes, minutes),
        (MilestoneKind.unique_tracks, unique_tracks),
    ):
        rows += [
            {
                "user_id": user_id,
                "kind": kind,
                "threshold": t,
                "entity_id": "",
                "achieved_at": now,
                "value_at_achievement": value,
            }
            for t in THRESHOLDS[kind]
            if value >= t
        ]

    artist_counts = (
        await db.execute(
            select(Artist.id, Artist.name, func.count())
            .join(TrackArtist, TrackArtist.artist_id == Artist.id)
            .join(Stream, Stream.track_id == TrackArtist.track_id)
            .where(Stream.user_id == user_id, TrackArtist.position == 0, COUNTS_AS_STREAM)
            .group_by(Artist.id, Artist.name)
            .having(func.count() >= THRESHOLDS[MilestoneKind.artist_streams][0])
        )
    ).all()
    for aid, name, n in artist_counts:
        rows += [
            {
                "user_id": user_id,
                "kind": MilestoneKind.artist_streams,
                "threshold": t,
                "entity_id": aid,
                "entity_name": name,
                "achieved_at": now,
                "value_at_achievement": n,
            }
            for t in THRESHOLDS[MilestoneKind.artist_streams]
            if n >= t
        ]
    if len(artist_counts) >= THRESHOLDS[MilestoneKind.unique_artists][0]:
        rows += [
            {
                "user_id": user_id,
                "kind": MilestoneKind.unique_artists,
                "threshold": t,
                "entity_id": "",
                "achieved_at": now,
                "value_at_achievement": len(artist_counts),
            }
            for t in THRESHOLDS[MilestoneKind.unique_artists]
            if len(artist_counts) >= t
        ]

    if not rows:
        return 0
    res = await db.execute(insert(Milestone).values(rows).on_conflict_do_nothing())
    await db.commit()
    return res.rowcount or 0
