"""Thin, typed, rate-limited Spotify Web API client.

Every method is a plain coroutine returning parsed JSON. Pagination helpers yield items so
callers (purger, blender, importer hydration) never load a 10k-track playlist in one go.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services.spotify.rate_limiter import SpotifyRateLimiter


class SpotifyAPIError(Exception):
    def __init__(self, status: int, message: str, retry_after: float | None = None):
        super().__init__(f"Spotify {status}: {message}")
        self.status = status
        self.retry_after = retry_after


class SpotifyTransientError(SpotifyAPIError):
    """5xx / network — safe to retry."""


def chunked(seq: Iterable[Any], size: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for item in seq:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


class SpotifyClient:
    def __init__(
        self, access_token: str, limiter: SpotifyRateLimiter | None = None, priority: bool = False
    ) -> None:
        self._token = access_token
        self._limiter = limiter or SpotifyRateLimiter()
        self._priority = priority
        self._http = httpx.AsyncClient(
            base_url=settings.spotify_api_base,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> SpotifyClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ── core ─────────────────────────────────────────────────────────────────
    @retry(
        retry=retry_if_exception_type(SpotifyTransientError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, max=8),
        reraise=True,
    )
    async def _request(self, method: str, path: str, **kw: Any) -> Any:
        await self._limiter.acquire(priority=self._priority)
        resp = await self._http.request(method, path, **kw)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "5"))
            await self._limiter.throttle(retry_after)
            raise SpotifyTransientError(429, "rate limited", retry_after)
        if resp.status_code >= 500:
            raise SpotifyTransientError(resp.status_code, resp.text[:200])
        if resp.status_code == 204 or not resp.content:
            return None
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("error", {}).get("message", resp.text[:200])
            except ValueError:
                msg = resp.text[:200]
            raise SpotifyAPIError(resp.status_code, msg)
        return resp.json()

    async def get(self, path: str, **params: Any) -> Any:
        return await self._request("GET", path, params={k: v for k, v in params.items() if v is not None})

    async def post(self, path: str, json: Any = None, **params: Any) -> Any:
        return await self._request("POST", path, json=json, params=params or None)

    async def put(self, path: str, json: Any = None, **params: Any) -> Any:
        return await self._request("PUT", path, json=json, params=params or None)

    async def delete(self, path: str, json: Any = None, **params: Any) -> Any:
        return await self._request("DELETE", path, json=json, params=params or None)

    async def paginate(self, path: str, limit: int = 50, **params: Any) -> AsyncIterator[dict]:
        """Follow `next` links, yielding items."""
        page = await self.get(path, limit=limit, **params)
        while page:
            for item in page.get("items", []):
                yield item
            nxt = page.get("next")
            if not nxt:
                break
            page = await self._request("GET", nxt.replace(settings.spotify_api_base, ""))

    # ── identity ─────────────────────────────────────────────────────────────
    async def me(self) -> dict:
        return await self.get("/me")

    # ── tracking engine ──────────────────────────────────────────────────────
    async def recently_played(self, after_ms: int | None = None, limit: int = 50) -> dict:
        return await self.get("/me/player/recently-played", limit=limit, after=after_ms)

    async def top_items(self, kind: str, time_range: str = "medium_term", limit: int = 50) -> dict:
        return await self.get(f"/me/top/{kind}", time_range=time_range, limit=limit)

    # ── playback / skip guard ────────────────────────────────────────────────
    async def player_state(self) -> dict | None:
        return await self.get("/me/player", additional_types="track,episode")

    async def skip_next(self, device_id: str | None = None) -> None:
        await self.post("/me/player/next", device_id=device_id)

    # ── catalogue hydration (batched: 50 tracks / 50 artists / 20 albums) ────
    async def tracks(self, ids: list[str]) -> list[dict]:
        out: list[dict] = []
        for batch in chunked(ids, 50):
            data = await self.get("/tracks", ids=",".join(batch))
            out.extend(t for t in data.get("tracks", []) if t)
        return out

    async def artists(self, ids: list[str]) -> list[dict]:
        out: list[dict] = []
        for batch in chunked(ids, 50):
            data = await self.get("/artists", ids=",".join(batch))
            out.extend(a for a in data.get("artists", []) if a)
        return out

    async def audio_features(self, ids: list[str]) -> list[dict]:
        """NOTE: returns 403 for Spotify apps created after 2024-11-27. See
        services/tools/sonic_filter.py for the provider fallback chain."""
        out: list[dict] = []
        for batch in chunked(ids, 100):
            data = await self.get("/audio-features", ids=",".join(batch))
            out.extend(f for f in data.get("audio_features", []) if f)
        return out

    async def search(self, q: str, types: str = "track", limit: int = 5, market: str | None = None) -> dict:
        return await self.get("/search", q=q, type=types, limit=limit, market=market)

    # ── library ──────────────────────────────────────────────────────────────
    def saved_tracks(self) -> AsyncIterator[dict]:
        return self.paginate("/me/tracks", limit=50)

    async def remove_saved_tracks(self, ids: list[str]) -> None:
        for batch in chunked(ids, 50):
            await self.delete("/me/tracks", json={"ids": batch})

    # ── playlists ────────────────────────────────────────────────────────────
    def my_playlists(self) -> AsyncIterator[dict]:
        return self.paginate("/me/playlists", limit=50)

    async def playlist(self, playlist_id: str) -> dict:
        return await self.get(f"/playlists/{playlist_id}")

    def playlist_items(self, playlist_id: str) -> AsyncIterator[dict]:
        return self.paginate(
            f"/playlists/{playlist_id}/items",
            limit=50,
            fields="next,items(added_at,added_by.id,is_local,item(id,uri,name,duration_ms,"
            "explicit,popularity,external_ids,album(id,name,images,release_date,album_type,"
            "artists(id,name)),artists(id,name)))",
        )

    async def create_playlist(
        self, user_spotify_id: str, name: str, description: str = "", public: bool = False
    ) -> dict:
        return await self.post(
            f"/users/{user_spotify_id}/playlists",
            json={"name": name, "description": description, "public": public},
        )

    async def add_items(self, playlist_id: str, uris: list[str]) -> None:
        for batch in chunked(uris, 100):
            await self.post(f"/playlists/{playlist_id}/items", json={"uris": batch})

    async def replace_items(self, playlist_id: str, uris: list[str]) -> None:
        first, rest = uris[:100], uris[100:]
        await self.put(f"/playlists/{playlist_id}/items", json={"uris": first})
        if rest:
            await self.add_items(playlist_id, rest)

    async def remove_items(self, playlist_id: str, uris: list[str], snapshot_id: str | None = None) -> None:
        for batch in chunked(uris, 100):
            body: dict[str, Any] = {"items": [{"uri": u} for u in batch]}
            if snapshot_id:
                body["snapshot_id"] = snapshot_id
            await self.delete(f"/playlists/{playlist_id}/items", json=body)

    async def change_playlist_details(self, playlist_id: str, **details: Any) -> None:
        await self.put(f"/playlists/{playlist_id}", json=details)

    async def unfollow_playlist(self, playlist_id: str) -> None:
        """Spotify has no 'delete playlist'; unfollowing your own playlist removes it."""
        await self.delete(f"/playlists/{playlist_id}/followers")

    # ── following ────────────────────────────────────────────────────────────
    async def followed_artists(self) -> AsyncIterator[dict]:
        after: str | None = None
        while True:
            data = await self.get("/me/following", type="artist", limit=50, after=after)
            block = data.get("artists", {})
            for item in block.get("items", []):
                yield item
            after = (block.get("cursors") or {}).get("after")
            if not after:
                break

    async def unfollow_artists(self, ids: list[str]) -> None:
        for batch in chunked(ids, 50):
            await self.delete("/me/following", json={"ids": batch}, type="artist")
