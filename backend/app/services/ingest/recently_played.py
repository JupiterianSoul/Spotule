"""Lifetime Stream Logger — incremental /me/player/recently-played ingestion.

Spotify keeps only the last 50 plays (>30 s each). Polling every ≤5 min per user with the
`after` cursor captures everything for anyone who plays fewer than 50 tracks per interval;
`RECENTLY_PLAYED_POLL_SECONDS` can be tightened for heavy listeners. Idempotent via the
`uq_stream_dedupe` constraint.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.counts import inserted_count
from app.models import Stream, StreamHourlyRollup, SyncCursor, User
from app.models.enums import StreamSource, SyncKind
from app.services.catalog import upsert_tracks
from app.services.spotify import SpotifyClient


async def ingest_recently_played(db: AsyncSession, client: SpotifyClient, user: User) -> int:
    cursor = await db.get(SyncCursor, (user.id, SyncKind.recently_played))
    if cursor is None:
        cursor = SyncCursor(user_id=user.id, kind=SyncKind.recently_played)
        db.add(cursor)
    cursor.last_run_at = datetime.now(UTC)

    after_ms = int(cursor.cursor) if cursor.cursor else None
    try:
        data = await client.recently_played(after_ms=after_ms)
    except Exception as exc:  # noqa: BLE001 — recorded, worker decides on back-off
        cursor.consecutive_errors += 1
        cursor.last_error = str(exc)[:500]
        await db.commit()
        raise

    items = data.get("items", [])
    if not items:
        cursor.consecutive_errors = 0
        cursor.last_success_at = datetime.now(UTC)
        await db.commit()
        return 0

    await upsert_tracks(db, [i["track"] for i in items])
    rows = [
        {
            "user_id": user.id,
            "track_id": i["track"].get("id"),
            "spotify_track_uri": i["track"].get("uri"),
            "played_at": datetime.fromisoformat(i["played_at"].replace("Z", "+00:00")),
            "ms_played": None,
            "source": StreamSource.api_poll,
            "track_name": i["track"].get("name"),
            "artist_name": ", ".join(a["name"] for a in i["track"].get("artists", [])),
            "album_name": (i["track"].get("album") or {}).get("name"),
            "context_uri": (i.get("context") or {}).get("uri"),
            "context_type": (i.get("context") or {}).get("type"),
        }
        for i in items
    ]
    inserted = inserted_count(
        await db.execute(insert(Stream).values(rows).on_conflict_do_nothing().returning(Stream.id))
    )

    newest = max(r["played_at"] for r in rows)
    cursor.cursor = str(int(newest.timestamp() * 1000))
    cursor.consecutive_errors = 0
    cursor.last_success_at = datetime.now(UTC)
    await refresh_hourly_rollups(db, user.id, since=min(r["played_at"] for r in rows))
    await db.commit()
    return inserted


async def refresh_hourly_rollups(db: AsyncSession, user_id, since: datetime) -> None:
    """Recompute listening-clock buckets from `since` (truncated to the hour) onwards."""
    bucket = func.date_trunc("hour", Stream.played_at)
    q = (
        select(
            bucket.label("bucket_start"),
            func.count().label("streams"),
            func.coalesce(func.sum(Stream.ms_played), 0).label("ms_played"),
            func.count(func.distinct(Stream.track_id)).label("unique_tracks"),
        )
        .where(Stream.user_id == user_id, Stream.played_at >= func.date_trunc("hour", since))
        .group_by(bucket)
    )
    rows = (await db.execute(q)).all()
    if not rows:
        return
    stmt = insert(StreamHourlyRollup).values(
        [
            {
                "user_id": user_id,
                "bucket_start": r.bucket_start,
                "streams": r.streams,
                "ms_played": int(r.ms_played),
                "unique_tracks": r.unique_tracks,
            }
            for r in rows
        ]
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[StreamHourlyRollup.user_id, StreamHourlyRollup.bucket_start],
            set_={
                "streams": stmt.excluded.streams,
                "ms_played": stmt.excluded.ms_played,
                "unique_tracks": stmt.excluded.unique_tracks,
            },
        )
    )
