"""Top tracks / artists / albums / genres from the lifetime ledger (not Spotify's own
/me/top which is opaque and capped at 50)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Integer, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Album, Artist, ArtistGenre, Genre, Stream, Track, TrackArtist

# A play counts as a "stream" if we know it lasted ≥30 s, or if duration is unknown (api_poll
# rows are already filtered to ≥30 s by Spotify).
COUNTS_AS_STREAM = (Stream.ms_played.is_(None)) | (Stream.ms_played >= 30_000)


def _scoped(user_id: uuid.UUID, start: datetime | None, end: datetime):
    conds = [Stream.user_id == user_id, Stream.played_at <= end, COUNTS_AS_STREAM]
    if start:
        conds.append(Stream.played_at >= start)
    return and_(*conds)


def _minutes():
    # Fallback to track duration when ms_played unknown (api_poll rows)
    return func.coalesce(func.sum(func.coalesce(Stream.ms_played, Track.duration_ms)), 0) / 60000


async def top_tracks(db: AsyncSession, user_id, start, end, limit=50, offset=0):
    q = (
        select(
            Track.id,
            Track.name,
            Album.image_url,
            Album.name.label("album"),
            func.count().label("streams"),
            _minutes().label("minutes"),
        )
        .join(Track, Track.id == Stream.track_id)
        .outerjoin(Album, Album.id == Track.album_id)
        .where(_scoped(user_id, start, end))
        .group_by(Track.id, Track.name, Album.image_url, Album.name)
        .order_by(func.count().desc())
        .limit(limit)
        .offset(offset)
    )
    return [dict(r._mapping) for r in (await db.execute(q)).all()]


async def top_artists(db: AsyncSession, user_id, start, end, limit=50, offset=0):
    q = (
        select(
            Artist.id,
            Artist.name,
            Artist.image_url,
            func.count().label("streams"),
            _minutes().label("minutes"),
        )
        .join(Track, Track.id == Stream.track_id)
        .join(TrackArtist, TrackArtist.track_id == Track.id)
        .join(Artist, Artist.id == TrackArtist.artist_id)
        .where(_scoped(user_id, start, end), TrackArtist.position == 0)
        .group_by(Artist.id, Artist.name, Artist.image_url)
        .order_by(func.count().desc())
        .limit(limit)
        .offset(offset)
    )
    return [dict(r._mapping) for r in (await db.execute(q)).all()]


async def top_albums(db: AsyncSession, user_id, start, end, limit=50, offset=0):
    q = (
        select(
            Album.id,
            Album.name,
            Album.image_url,
            Artist.name.label("artist"),
            func.count().label("streams"),
            _minutes().label("minutes"),
        )
        .join(Track, Track.id == Stream.track_id)
        .join(Album, Album.id == Track.album_id)
        .outerjoin(Artist, Artist.id == Album.primary_artist_id)
        .where(_scoped(user_id, start, end))
        .group_by(Album.id, Album.name, Album.image_url, Artist.name)
        .order_by(func.count().desc())
        .limit(limit)
        .offset(offset)
    )
    return [dict(r._mapping) for r in (await db.execute(q)).all()]


async def top_genres(db: AsyncSession, user_id, start, end, limit=30):
    """Each stream contributes 1/N to each of the primary artist's N genres."""
    per_artist_genre_count = (
        select(ArtistGenre.artist_id, func.count().label("n")).group_by(ArtistGenre.artist_id).subquery()
    )
    weight = 1.0 / func.cast(per_artist_genre_count.c.n, Integer)
    q = (
        select(Genre.name, func.sum(weight).label("weighted_streams"), func.count().label("streams"))
        .join(Track, Track.id == Stream.track_id)
        .join(TrackArtist, and_(TrackArtist.track_id == Track.id, TrackArtist.position == 0))
        .join(ArtistGenre, ArtistGenre.artist_id == TrackArtist.artist_id)
        .join(Genre, Genre.id == ArtistGenre.genre_id)
        .join(per_artist_genre_count, per_artist_genre_count.c.artist_id == ArtistGenre.artist_id)
        .where(_scoped(user_id, start, end))
        .group_by(Genre.name)
        .order_by(func.sum(weight).desc())
        .limit(limit)
    )
    return [dict(r._mapping) for r in (await db.execute(q)).all()]


async def overview(db: AsyncSession, user_id, start, end) -> dict:
    q = (
        select(
            func.count().label("streams"),
            _minutes().label("minutes"),
            func.count(func.distinct(Stream.track_id)).label("unique_tracks"),
            func.count(func.distinct(TrackArtist.artist_id)).label("unique_artists"),
            func.sum(case((Stream.skipped.is_(True), 1), else_=0)).label("skips"),
        )
        .outerjoin(Track, Track.id == Stream.track_id)
        .outerjoin(TrackArtist, and_(TrackArtist.track_id == Track.id, TrackArtist.position == 0))
        .where(_scoped(user_id, start, end))
    )
    row = (await db.execute(q)).one()
    return {k: (float(v) if k == "minutes" else int(v or 0)) for k, v in row._mapping.items()}
