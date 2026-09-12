"""Genres when Spotify refuses catalogue lookups to the application.

Production returns `Spotify 403 on GET /artists: Forbidden` for an account that ingests its
plays successfully in the same sweep, sending six well-formed ids against a limit of fifty.
Valid token, valid request, refused anyway — nothing on this side fixes that, and the real
remedy is Extended Quota Mode on the Spotify app.

Genres still matter though: the Ban-Hammer classifies by them. /me/top/artists and
/me/following return full artist objects, genres included, and are user-data endpoints — the
category Spotify does answer. These cover that route and the cooldowns around it.
"""

import pytest
from sqlalchemy import delete, select

from app.db.redis import Keys, get_redis
from app.db.session import AsyncSessionLocal
from app.models import Artist, ArtistGenre
from app.services.catalog import harvest_artist_genres, hydrate_artists
from app.services.spotify import SpotifyAPIError

TOP = {
    "short_term": [{"id": "fbA" + "0" * 19, "name": "Top A", "genres": ["deathcore"]}],
    "medium_term": [{"id": "fbB" + "0" * 19, "name": "Top B", "genres": ["metalcore", "deathcore"]}],
    "long_term": [{"id": "fbA" + "0" * 19, "name": "Top A", "genres": ["deathcore"]}],  # repeat
}
FOLLOWED = [{"id": "fbC" + "0" * 19, "name": "Followed C", "genres": ["black metal"]}]
IDS = [a["id"] for group in (TOP["short_term"], TOP["medium_term"], FOLLOWED) for a in group]


class ListeningOnlyClient:
    """Answers the user-data endpoints and refuses the catalogue one, as production does."""

    def __init__(self):
        self.calls: list[str] = []

    async def artists(self, _ids):
        self.calls.append("GET /artists")
        raise SpotifyAPIError(403, "Forbidden", None, "GET /artists")

    async def top_items(self, kind, time_range="medium_term", limit=50):
        self.calls.append(f"GET /me/top/{kind}?{time_range}")
        return {"items": TOP[time_range]}

    async def followed_artists(self):
        self.calls.append("GET /me/following")
        for artist in FOLLOWED:
            yield artist


@pytest.fixture
async def clean_slate():
    r = get_redis()
    await r.delete(Keys.CATALOGUE_RESTRICTED, Keys.GENRES_HARVESTED)
    yield
    await r.delete(Keys.CATALOGUE_RESTRICTED, Keys.GENRES_HARVESTED)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ArtistGenre).where(ArtistGenre.artist_id.in_(IDS)))
        await db.execute(delete(Artist).where(Artist.id.in_(IDS)))
        await db.commit()


@pytest.mark.asyncio
async def test_genres_arrive_from_listening_when_the_catalogue_is_refused(clean_slate):
    client = ListeningOnlyClient()
    async with AsyncSessionLocal() as db:
        # First sweep: the catalogue route is tried, refused, and the refusal is reported.
        db.add(Artist(id=IDS[0], name="pending"))
        await db.commit()
        with pytest.raises(SpotifyAPIError):
            await hydrate_artists(db, client)
        assert client.calls == ["GET /artists"]

        # Next sweep: no second request to a route already known to be refused.
        outcome = await hydrate_artists(db, client)
        assert outcome["artists_source"] == "listening"
        assert outcome["artists_hydrated"] == 3  # two top artists deduped, one followed
        assert client.calls.count("GET /artists") == 1

        stored = (await db.execute(select(Artist).where(Artist.id.in_(IDS)))).scalars().all()
        assert {a.name for a in stored} == {"Top A", "Top B", "Followed C"}
        assert all(a.fetched_at is not None for a in stored)  # they leave the pending list

        # And the genres themselves landed, which is the whole point.
        links = (await db.execute(select(ArtistGenre).where(ArtistGenre.artist_id.in_(IDS)))).scalars().all()
        assert len(links) == 4  # deathcore, metalcore+deathcore, black metal


@pytest.mark.asyncio
async def test_listening_is_not_re_read_on_every_sweep(clean_slate):
    """Top artists and follows move slowly; a five-minute re-read buys nothing."""
    client = ListeningOnlyClient()
    async with AsyncSessionLocal() as db:
        await get_redis().set(Keys.CATALOGUE_RESTRICTED, "1", ex=60)
        first = await hydrate_artists(db, client)
        assert first["artists_source"] == "listening"

        second = await hydrate_artists(db, client)
        assert second["artists_source"] == "listening (cached)"
        assert client.calls.count("GET /me/following") == 1


@pytest.mark.asyncio
async def test_a_non_403_failure_is_not_swallowed(clean_slate):
    """Only a refusal means "stop asking". A rate limit or an outage must still surface."""

    class RateLimited(ListeningOnlyClient):
        async def artists(self, _ids):
            raise SpotifyAPIError(429, "rate limited", 5.0, "GET /artists")

    async with AsyncSessionLocal() as db:
        db.add(Artist(id=IDS[0], name="pending"))
        await db.commit()
        with pytest.raises(SpotifyAPIError) as caught:
            await hydrate_artists(db, RateLimited())
    assert caught.value.status == 429
    assert not await get_redis().get(Keys.CATALOGUE_RESTRICTED)


@pytest.mark.asyncio
async def test_harvest_stops_paging_a_heavily_following_account(clean_slate):
    class ManyFollows(ListeningOnlyClient):
        async def followed_artists(self):
            for i in range(500):
                yield {"id": f"bulk{i:018d}", "name": f"Bulk {i}", "genres": []}

    async with AsyncSessionLocal() as db:
        found = await harvest_artist_genres(db, ManyFollows(), max_followed=10)
        await db.rollback()
    assert found <= 12  # the two top artists plus the cap
