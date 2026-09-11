"""Requires Postgres + Redis (as in CI / docker compose)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_healthz_and_tool_catalogue_localised():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/healthz")).json()["ok"] is True
        en = (await c.get("/api/v1/tools")).json()
        fr = (await c.get("/api/v1/tools", headers={"Accept-Language": "fr"})).json()
        assert len(en) >= 11
        keys = {t["key"] for t in en}
        assert {"playlist.true_shuffle", "sonic.filter", "porter.text_to_playlist"} <= keys
        assert en[0]["title"] != fr[0]["title"]


@pytest.mark.asyncio
async def test_protected_route_requires_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/me")
        assert r.status_code == 401
        r_fr = await c.get("/api/v1/me", headers={"Accept-Language": "fr"})
        assert "connecter" in r_fr.json()["detail"]
