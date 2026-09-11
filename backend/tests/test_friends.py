"""Friend request flow with two real users and real sessions (Postgres + Redis)."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import settings
from app.core.security import new_session_id
from app.db.redis import Keys, get_redis
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import FriendLink, User, UserPreference


async def _make_user(name: str) -> User:
    async with AsyncSessionLocal() as db:
        u = User(spotify_id=f"test_{name}_{uuid.uuid4().hex[:6]}", display_name=name)
        db.add(u)
        await db.flush()
        db.add(UserPreference(user_id=u.id))
        await db.commit()
        await db.refresh(u)
        return u


async def _session_for(user: User) -> dict[str, str]:
    sid = new_session_id()
    await get_redis().set(Keys.session(sid), str(user.id), ex=600)
    return {settings.session_cookie_name: sid}


@pytest.fixture
async def two_users():
    alice, bob = await _make_user("Alice Test"), await _make_user("Bob Test")
    yield alice, bob
    async with AsyncSessionLocal() as db:
        await db.execute(delete(FriendLink).where(FriendLink.user_id.in_([alice.id, bob.id])))
        await db.execute(delete(User).where(User.id.in_([alice.id, bob.id])))
        await db.commit()


@pytest.mark.asyncio
async def test_full_request_accept_remove_cycle(two_users):
    alice, bob = two_users
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        a, b = await _session_for(alice), await _session_for(bob)

        # Alice finds Bob by partial display name
        r = await c.get("/api/v1/friends/search", params={"q": "bob t"}, cookies=a)
        assert r.status_code == 200 and any(p["user_id"] == str(bob.id) for p in r.json())
        # ...but never herself
        r = await c.get("/api/v1/friends/search", params={"q": "alice"}, cookies=a)
        assert all(p["user_id"] != str(alice.id) for p in r.json())

        # Alice sends a request
        r = await c.post("/api/v1/friends/requests", json={"user_id": str(bob.id)}, cookies=a)
        assert r.status_code == 201 and r.json()["direction"] == "outgoing"
        link_id = r.json()["link_id"]

        # Duplicate is refused, self-add is refused, localised
        r = await c.post(
            "/api/v1/friends/requests",
            json={"user_id": str(bob.id)},
            cookies=a,
            headers={"Accept-Language": "fr"},
        )
        assert r.status_code == 409 and "déjà" in r.json()["detail"]
        r = await c.post("/api/v1/friends/requests", json={"user_id": str(alice.id)}, cookies=a)
        assert r.status_code == 400

        # Bob sees it as incoming; Alice cannot accept her own request
        r = await c.get("/api/v1/friends", cookies=b)
        assert r.json()[0]["direction"] == "incoming"
        assert (await c.post(f"/api/v1/friends/requests/{link_id}/accept", cookies=a)).status_code == 404

        # Bob accepts → mutual on both sides
        r = await c.post(f"/api/v1/friends/requests/{link_id}/accept", cookies=b)
        assert r.status_code == 200 and r.json()["direction"] == "mutual"
        for who in (a, b):
            links = (await c.get("/api/v1/friends", cookies=who)).json()
            assert len(links) == 1 and links[0]["status"] == "accepted"

        # Friends leaderboard now includes both (no streams yet, so both appear via the is_me/friend join)
        r = await c.get("/api/v1/stats/leaderboard", params={"scope": "friends"}, cookies=a)
        assert r.status_code == 200

        # Alice unfriends → gone for both
        assert (await c.delete(f"/api/v1/friends/{bob.id}", cookies=a)).status_code == 204
        for who in (a, b):
            assert (await c.get("/api/v1/friends", cookies=who)).json() == []


@pytest.mark.asyncio
async def test_crossed_requests_become_friends(two_users):
    """If both people request each other, the second request acts as an acceptance."""
    alice, bob = two_users
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        a, b = await _session_for(alice), await _session_for(bob)
        assert (
            await c.post("/api/v1/friends/requests", json={"spotify_id": bob.spotify_id}, cookies=a)
        ).status_code == 201
        r = await c.post("/api/v1/friends/requests", json={"spotify_id": alice.spotify_id}, cookies=b)
        assert r.status_code == 201 and r.json()["direction"] == "mutual"


@pytest.mark.asyncio
async def test_requires_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/v1/friends")).status_code == 401
