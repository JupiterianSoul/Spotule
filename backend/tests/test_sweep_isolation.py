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
