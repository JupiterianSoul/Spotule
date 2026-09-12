"""Scheduler endpoint auth. These endpoints run privileged sweeps, so getting the guard
wrong would expose every user's ingestion to the internet."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

ENDPOINTS = [
    "/api/v1/cron/run",
    "/api/v1/cron/ingest",
    "/api/v1/cron/catalog",
    "/api/v1/cron/milestones",
    "/api/v1/cron/automations",
]


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "test-cron-secret")
    return "test-cron-secret"


@pytest.mark.asyncio
async def test_disabled_when_no_secret_configured(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for path in ENDPOINTS:
            r = await c.post(path)
            assert r.status_code == 503, path


@pytest.mark.asyncio
async def test_rejects_missing_and_wrong_credentials(secret):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for path in ENDPOINTS:
            assert (await c.post(path)).status_code == 401, path
            bad = await c.post(path, headers={"Authorization": "Bearer nope"})
            assert bad.status_code == 401, path
            # A correct secret in the wrong scheme must not pass either.
            raw = await c.post(path, headers={"Authorization": secret})
            assert raw.status_code == 401, path


@pytest.mark.asyncio
async def test_accepts_the_configured_secret(secret):
    """With no users in the database every sweep is a well-formed no-op."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/cron/ingest", headers={"Authorization": f"Bearer {secret}"})
        assert r.status_code == 200
        assert r.json()["processed"] == 0

        r = await c.post("/api/v1/cron/run", headers={"Authorization": f"Bearer {secret}"})
        assert r.status_code == 200
        body = r.json()
        assert set(body) >= {"recently_played", "catalog", "milestones", "automations", "ran_at"}
        assert body["recently_played"]["failed"] == 0


@pytest.mark.asyncio
async def test_one_broken_stage_does_not_fail_the_whole_sweep(secret, monkeypatch):
    """A stage that raises must be reported, not turned into a 500.

    The scheduler used to get an opaque HTTP 500 on every run: one Spotify token refresh
    failing anywhere aborted the request, so nothing ingested, nothing was awarded, and the
    error text never left the server. Each stage now stands on its own.
    """
    from app.services import sweeps

    async def boom(*_a, **_kw):
        raise RuntimeError("token refresh exploded")

    monkeypatch.setattr(sweeps, "sweep_recently_played", boom)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/cron/run", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200
    body = r.json()
    assert body["recently_played"]["failed"] == 1
    assert "token refresh exploded" in body["recently_played"]["errors"][0]
    # The stages after the broken one still ran.
    assert body["milestones"]["failed"] == 0
    assert body["automations"]["failed"] == 0


@pytest.mark.asyncio
async def test_one_broken_account_does_not_stop_ingestion(secret, monkeypatch):
    """Refreshing a token happens per user and can fail per user; the batch must survive it."""
    import uuid

    from app.models import User
    from app.services import sweeps

    good = User(id=uuid.uuid4(), spotify_id="good", display_name="good")
    bad = User(id=uuid.uuid4(), spotify_id="bad", display_name="bad")

    async def two_users(*_a, **_kw):
        return [bad, good]

    async def refresh(_db, user):
        if user.spotify_id == "bad":
            raise RuntimeError("refresh_token revoked")
        return None  # no usable link; counts as skipped, not failed

    monkeypatch.setattr(sweeps, "_active_users", two_users)
    monkeypatch.setattr(sweeps, "_client_for", refresh)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/cron/ingest", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200
    body = r.json()
    assert body["failed"] == 1
    assert "refresh_token revoked" in body["errors"][0]
