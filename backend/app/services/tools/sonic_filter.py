"""Smart Sonic Filters — BPM / Energy / Valence / Acousticness → new playlist.

⚠ Spotify restricted /audio-features and /audio-analysis on 2024-11-27 for apps created after
that date (403). `AudioFeatureProvider` abstracts the source so the feature keeps working:
  1. SpotifyProvider      — only if the app is grandfathered/extended-quota.
  2. ReccoBeatsProvider   — free API keyed by Spotify track id (drop-in field names).
  3. UserImportProvider   — CSV upload (e.g. from Exportify) stored in `audio_features`.
Resolved values are cached in `audio_features` with their `source`.
"""

from __future__ import annotations

import abc
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AudioFeatures
from app.models.enums import AudioFeatureSource
from app.services.spotify import SpotifyAPIError, SpotifyClient
from app.services.tools.base import Tool, ToolContext, registry

FIELDS = (
    "tempo",
    "energy",
    "valence",
    "danceability",
    "acousticness",
    "instrumentalness",
    "liveness",
    "speechiness",
    "loudness",
    "key",
    "mode",
    "time_signature",
)


class AudioFeatureProvider(abc.ABC):
    source: AudioFeatureSource

    @abc.abstractmethod
    async def fetch(self, track_ids: list[str]) -> dict[str, dict]: ...


class SpotifyProvider(AudioFeatureProvider):
    source = AudioFeatureSource.spotify

    def __init__(self, client: SpotifyClient) -> None:
        self.client = client

    async def fetch(self, track_ids: list[str]) -> dict[str, dict]:
        try:
            rows = await self.client.audio_features(track_ids)
        except SpotifyAPIError as exc:
            if exc.status == 403:
                return {}  # restricted app → let the next provider try
            raise
        return {r["id"]: {f: r.get(f) for f in FIELDS} for r in rows}


class ReccoBeatsProvider(AudioFeatureProvider):
    source = AudioFeatureSource.reccobeats
    BASE = "https://api.reccobeats.com/v1"

    async def fetch(self, track_ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=15) as http:
            for i in range(0, len(track_ids), 40):
                batch = track_ids[i : i + 40]
                resp = await http.get(f"{self.BASE}/audio-features", params={"ids": ",".join(batch)})
                if resp.status_code != 200:
                    continue
                for r in resp.json().get("content", []):
                    sid = (r.get("href") or "").rsplit("/", 1)[-1] or r.get("id")
                    if sid:
                        out[sid] = {f: r.get(f) for f in FIELDS}
        return out


async def resolve_features(
    db: AsyncSession, client: SpotifyClient, track_ids: list[str]
) -> dict[str, AudioFeatures]:
    rows = (await db.execute(select(AudioFeatures).where(AudioFeatures.track_id.in_(track_ids)))).scalars()
    have = {r.track_id: r for r in rows}
    missing = [t for t in track_ids if t not in have]
    for provider in (SpotifyProvider(client), ReccoBeatsProvider()):
        if not missing:
            break
        found = await provider.fetch(missing)
        if found:
            values = [
                {"track_id": tid, "source": provider.source, "fetched_at": datetime.now(UTC), **f}
                for tid, f in found.items()
            ]
            await db.execute(insert(AudioFeatures).values(values).on_conflict_do_nothing())
            await db.commit()
            missing = [t for t in missing if t not in found]
    rows = (await db.execute(select(AudioFeatures).where(AudioFeatures.track_id.in_(track_ids)))).scalars()
    return {r.track_id: r for r in rows}


@registry.register
class SonicFilter(Tool):
    key = "sonic.filter"
    pillar = "sonic"

    class Params(BaseModel):
        source_playlist_id: str | None = Field(None, description="None = Liked Songs")
        name: str
        bpm_min: float | None = None
        bpm_max: float | None = None
        energy_min: float | None = Field(None, ge=0, le=1)
        energy_max: float | None = Field(None, ge=0, le=1)
        valence_min: float | None = Field(None, ge=0, le=1)
        valence_max: float | None = Field(None, ge=0, le=1)
        acousticness_min: float | None = Field(None, ge=0, le=1)
        acousticness_max: float | None = Field(None, ge=0, le=1)
        danceability_min: float | None = Field(None, ge=0, le=1)
        danceability_max: float | None = Field(None, ge=0, le=1)

    @staticmethod
    def _in(v: float | None, lo: float | None, hi: float | None) -> bool:
        if v is None:
            return False
        return (lo is None or v >= lo) and (hi is None or v <= hi)

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        if params.source_playlist_id:
            items = [
                i["item"] async for i in ctx.client.playlist_items(params.source_playlist_id) if i.get("item")
            ]
        else:
            items = [i["track"] async for i in ctx.client.saved_tracks() if i.get("track")]
        ids = [t["id"] for t in items if t.get("id")]
        feats = await resolve_features(ctx.db, ctx.client, ids)
        keep = [
            t["uri"]
            for t in items
            if t.get("id") in feats
            and self._in(feats[t["id"]].tempo, params.bpm_min, params.bpm_max)
            and self._in(feats[t["id"]].energy, params.energy_min, params.energy_max)
            and self._in(feats[t["id"]].valence, params.valence_min, params.valence_max)
            and self._in(feats[t["id"]].acousticness, params.acousticness_min, params.acousticness_max)
            and self._in(feats[t["id"]].danceability, params.danceability_min, params.danceability_max)
        ]
        new = await ctx.client.create_playlist(ctx.user.spotify_id, params.name, "Sonic filter · SpotiMax")
        await ctx.client.add_items(new["id"], keep)
        return {
            "playlist_id": new["id"],
            "matched": len(keep),
            "scanned": len(ids),
            "without_features": len(ids) - len(feats),
        }
