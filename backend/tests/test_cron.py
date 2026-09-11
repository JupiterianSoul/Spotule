"""Scheduler endpoint auth. These endpoints run privileged sweeps, so getting the guard
wrong would expose every user's ingestion to the internet."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

ENDPOINTS = ["/api/v1/cron/run", "/api/v1/cron/ingest", "/api/v1/cron/catalog",
             "/api/v1/cron/milestones", "/api/v1/cron/automations"]


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
