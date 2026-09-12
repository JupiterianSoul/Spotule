"""Duplicate payloads inside one upsert.

This is the bug that stopped every play from being logged in production. Spotify's
recently-played feed returns one entry per *play*, so listening to a track twice inside one
five-minute poll put its id in the VALUES list twice, and Postgres rejects an
ON CONFLICT DO UPDATE that would touch the same row twice:

    psycopg.errors.CardinalityViolation:
    ON CONFLICT DO UPDATE command cannot affect row a second time

That killed the whole batch, not just the repeated track. Runs against the real database
because the constraint being violated is the database's.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models import Album, Artist, Track, TrackArtist
from app.services.catalog import dedupe_by_id, upsert_tracks

SUFFIX = uuid.uuid4().hex[:8]
TRACK_ID = f"tt{SUFFIX}"
ALBUM_ID = f"al{SUFFIX}"
ARTIST_ID = f"ar{SUFFIX}"


def track_payload(**over) -> dict:
    payload = {
        "id": TRACK_ID,
        "name": "Test Track",
        "type": "track",
        "duration_ms": 210_000,
        "explicit": False,
        "is_local": False,
        "preview_url": None,
        "artists": [{"id": ARTIST_ID, "name": "Test Artist"}],
        "album": {
            "id": ALBUM_ID,
            "name": "Test Album",
            "album_type": "album",
            "release_date": "2020-01-01",
            "images": [],
            "total_tracks": 1,
            "artists": [{"id": ARTIST_ID, "name": "Test Artist"}],
        },
    }
    payload.update(over)
    return payload


@pytest.fixture
async def clean_catalogue():
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(TrackArtist).where(TrackArtist.track_id == TRACK_ID))
        await db.execute(delete(Track).where(Track.id == TRACK_ID))
        await db.execute(delete(Album).where(Album.id == ALBUM_ID))
        await db.execute(delete(Artist).where(Artist.id == ARTIST_ID))
        await db.commit()


@pytest.mark.asyncio
async def test_the_same_track_played_twice_in_one_batch(clean_catalogue):
    played = track_payload()
    async with AsyncSessionLocal() as db:
        await upsert_tracks(db, [played, played, played])
        await db.commit()
        rows = (await db.execute(select(Track).where(Track.id == TRACK_ID))).scalars().all()
        links = (
            (await db.execute(select(TrackArtist).where(TrackArtist.track_id == TRACK_ID)))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert len(links) == 1


@pytest.mark.asyncio
async def test_the_fuller_payload_wins(clean_catalogue):
    """Simplified and full objects for one track can arrive in the same call."""
    simplified = track_payload()
    full = track_payload(popularity=73, external_ids={"isrc": "TEST12345678"})
    async with AsyncSessionLocal() as db:
        await upsert_tracks(db, [simplified, full])
        await db.commit()
        track = (await db.execute(select(Track).where(Track.id == TRACK_ID))).scalar_one()
        assert track.popularity == 73
        assert track.isrc == "TEST12345678"


def test_dedupe_keeps_one_entry_per_id_and_prefers_the_richer_one():
    thin, fat = {"id": "x"}, {"id": "x", "name": "n", "popularity": 1}
    assert dedupe_by_id([thin, fat]) == [fat]
    assert dedupe_by_id([fat, thin]) == [fat]
    assert len(dedupe_by_id([{"id": "a"}, {"id": "b"}, {"id": "a"}])) == 2


def test_dedupe_tolerates_the_nulls_spotify_returns_for_unknown_ids():
    """/artists answers with null in place of any id it does not recognise."""
    from app.services.catalog import dedupe_by_id as dedupe

    payloads = [a for a in [{"id": "a"}, None, {"id": "a"}] if a and a.get("id")]
    assert dedupe(payloads) == [{"id": "a"}]
