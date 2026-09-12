"""How many rows a conflict-tolerant insert really wrote.

The scheduler reported `streams_inserted: -1` on a run that had genuinely logged plays.
psycopg reports no count for a multi-row INSERT — SQLAlchemy sends it through the executemany
path — so `rowcount` came back -1 and was passed straight through. asyncpg does report one,
which is why development never showed it. The ZIP importer had it worse: it would have
recorded a negative insert count and one more duplicate than the batch even contained.

Both drivers are covered here because the app uses both: asyncpg or psycopg for the API,
psycopg for the importer and Alembic.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.db.counts import inserted_count
from app.db.session import AsyncSessionLocal, SyncSessionLocal
from app.models import Stream, User, UserPreference
from app.models.enums import StreamSource

BASE = datetime.now(UTC).replace(microsecond=0)


def plays(user_id, count: int, offset: int = 0) -> list[dict]:
    return [
        {
            "user_id": user_id,
            "spotify_track_uri": f"spotify:track:count{i + offset}",
            "played_at": BASE + timedelta(seconds=i + offset),
            "source": StreamSource.api_poll,
        }
        for i in range(count)
    ]


def new_plays(user_id, count: int, offset: int = 0):
    return insert(Stream).values(plays(user_id, count, offset)).on_conflict_do_nothing().returning(Stream.id)


@pytest.mark.asyncio
async def test_async_driver_counts_new_duplicate_and_mixed_batches():
    async with AsyncSessionLocal() as db:
        user = User(spotify_id=f"count_{uuid.uuid4().hex[:6]}", display_name="counts")
        db.add(user)
        await db.flush()
        db.add(UserPreference(user_id=user.id))
        await db.commit()
        try:
            assert inserted_count(await db.execute(new_plays(user.id, 3))) == 3
            # The same batch again: every row conflicts, so nothing is written.
            assert inserted_count(await db.execute(new_plays(user.id, 3))) == 0
            # Two already stored, two new — the case a real poll almost always hits.
            assert inserted_count(await db.execute(new_plays(user.id, 4, offset=1))) == 2
        finally:
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()


def test_sync_driver_counts_the_same_way():
    """The ZIP importer runs on this one, and reports both counts back to the user."""
    with SyncSessionLocal() as db:
        user = User(spotify_id=f"count_{uuid.uuid4().hex[:6]}", display_name="counts")
        db.add(user)
        db.flush()
        db.add(UserPreference(user_id=user.id))
        db.commit()
        try:
            batch = 5
            added = inserted_count(db.execute(new_plays(user.id, batch, offset=100)))
            assert added == batch
            assert batch - added == 0  # what the importer records as duplicates

            again = inserted_count(db.execute(new_plays(user.id, batch, offset=100)))
            assert again == 0
            assert batch - again == batch  # all duplicates, never more than the batch held
        finally:
            db.execute(delete(User).where(User.id == user.id))
            db.commit()
