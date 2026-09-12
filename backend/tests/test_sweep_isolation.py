"""One failing account must cost only that account.

The scheduler returned HTTP 500 on every run for hours. The reported error was
MissingGreenlet from SQLAlchemy, which had nothing to do with the real problem: a rollback
expires every instance still attached to the session, so the moment the per-user error
handler rolled back and then read `user.spotify_id` to say *which* user failed, that read
became a database refresh in a place asyncio cannot perform one. The guard blew up inside
itself and the original failure was never seen.

These run against the real database, because the bug lives entirely in session state.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models import User, UserPreference
from app.services import sweeps


@pytest.fixture
async def two_logging_users():
    ids = []
    async with AsyncSessionLocal() as db:
        for name in ("sweep_a", "sweep_b"):
            user = User(spotify_id=f"test_{name}_{uuid.uuid4().hex[:6]}", display_name=name)
            db.add(user)
            await db.flush()
            db.add(UserPreference(user_id=user.id, stream_logger_enabled=True))
            ids.append(user.id)
        await db.commit()
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id.in_(ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_a_failing_account_does_not_stop_the_ones_behind_it(two_logging_users, monkeypatch):
    tried: list[str] = []

    async def always_fails(_db, user):
        tried.append(user.spotify_id)
        raise RuntimeError(f"boom for {user.spotify_id}")

    monkeypatch.setattr(sweeps, "_client_for", always_fails)

    async with AsyncSessionLocal() as db:
        result = await sweeps.sweep_recently_played(db)

    # The loop reached every user, and each failure names the account it belongs to.
    assert len(tried) >= 2, tried
    assert result.failed == len(tried)
    assert all("boom for" in err for err in result.errors), result.errors
    for spotify_id in tried:
        assert any(err.startswith(f"{spotify_id}:") for err in result.errors), spotify_id


@pytest.mark.asyncio
async def test_milestones_keep_going_after_a_rollback(two_logging_users, monkeypatch):
    """Same session-state trap, different loop: this one reads user.id on every iteration."""
    seen = []

    async def always_fails(_db, user_id):
        seen.append(user_id)
        raise RuntimeError("milestone detection exploded")

    monkeypatch.setattr(sweeps, "detect_milestones", always_fails)

    async with AsyncSessionLocal() as db:
        result = await sweeps.sweep_milestones(db)

    assert len(seen) >= 2, seen
    assert result.failed == len(seen)


@pytest.mark.asyncio
async def test_catalogue_moves_on_to_another_account(two_logging_users, monkeypatch):
    """Catalogue rows are shared, so one dead grant must not stop hydration for all."""
    attempts: list[str] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    async def first_account_is_dead(_db, user):
        attempts.append(user.spotify_id)
        if len(attempts) == 1:
            raise RuntimeError("refresh_token revoked")
        return FakeClient()

    async def nothing_pending(*_a):
        return 0

    monkeypatch.setattr(sweeps, "_client_for", first_account_is_dead)
    monkeypatch.setattr(sweeps, "hydrate_artists", nothing_pending)
    monkeypatch.setattr(sweeps, "hydrate_orphan_tracks", nothing_pending)

    async with AsyncSessionLocal() as db:
        result = await sweeps.sweep_catalog(db)

    assert len(attempts) == 2, attempts
    assert result.processed == 1
    # The dead account is still reported — it is a real problem, just not a fatal one.
    assert any("refresh_token revoked" in err for err in result.errors)


@pytest.mark.asyncio
async def test_a_refused_endpoint_does_not_cost_the_other_half(two_logging_users, monkeypatch):
    """Production hit 403 on GET /artists, which stopped the track hydration behind it.

    The two halves fail for different reasons — a dead grant fails both, an endpoint the
    application is refused fails one — so neither may depend on the other.
    """
    from app.services.spotify import SpotifyAPIError

    accounts: list[str] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    async def usable(_db, user):
        accounts.append(user.spotify_id)
        return FakeClient()

    async def refused(*_a):
        raise SpotifyAPIError(403, "Forbidden", None, "GET /artists")

    async def works(*_a):
        return 7

    monkeypatch.setattr(sweeps, "_client_for", usable)
    monkeypatch.setattr(sweeps, "hydrate_artists", refused)
    monkeypatch.setattr(sweeps, "hydrate_orphan_tracks", works)

    async with AsyncSessionLocal() as db:
        result = await sweeps.sweep_catalog(db)

    assert result.detail["tracks_hydrated"] == 7
    assert result.failed == 1
    assert any("GET /artists" in err for err in result.errors)
    # An endpoint refused for the application answers no differently for another account,
    # so the sweep must not walk the whole list hoping otherwise.
    assert len(accounts) == 1, accounts


def test_a_spotify_error_names_the_request_that_caused_it():
    """Spotify's own message is often one word; "Forbidden" alone is not actionable."""
    from app.services.spotify import SpotifyAPIError

    exc = SpotifyAPIError(403, "Forbidden", None, "GET /artists")
    assert str(exc) == "Spotify 403 on GET /artists: Forbidden"
    assert exc.status == 403
    # Callers that predate the field must still work.
    assert str(SpotifyAPIError(404, "Not found")) == "Spotify 404: Not found"
