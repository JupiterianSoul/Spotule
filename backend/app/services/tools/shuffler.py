"""The True Shuffler — Fisher-Yates over the full URI array, then `replace_items`.
Spotify's client shuffle is weighted/sticky; this is a uniform permutation."""

from __future__ import annotations

import secrets
from typing import Any

from pydantic import BaseModel, Field

from app.services.tools.base import Tool, ToolContext, registry


def fisher_yates(items: list[str]) -> list[str]:
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = secrets.randbelow(i + 1)  # CSPRNG — no modulo bias
        out[i], out[j] = out[j], out[i]
    return out


def spread_artists(uris: list[str], artist_of: dict[str, str]) -> list[str]:
    """Optional post-pass: avoid the same artist back-to-back where possible."""
    out: list[str] = []
    pool = list(uris)
    while pool:
        for idx, uri in enumerate(pool):
            if not out or artist_of.get(uri) != artist_of.get(out[-1]):
                out.append(pool.pop(idx))
                break
        else:
            out.append(pool.pop(0))
    return out


@registry.register
class TrueShuffle(Tool):
    key = "playlist.true_shuffle"
    pillar = "playlists"
    destructive = True  # rewrites order → backup first

    class Params(BaseModel):
        playlist_id: str
        avoid_adjacent_artists: bool = True
        write_to_new_playlist: bool = Field(False, description="Leave the source untouched")

    async def backup_targets(self, params: Params) -> list[str]:
        return [params.playlist_id]

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        items = [i["item"] async for i in ctx.client.playlist_items(params.playlist_id) if i.get("item")]
        uris = [t["uri"] for t in items if t.get("uri")]
        shuffled = fisher_yates(uris)
        if params.avoid_adjacent_artists:
            artist_of = {t["uri"]: (t.get("artists") or [{}])[0].get("id", "") for t in items}
            shuffled = spread_artists(shuffled, artist_of)
        if params.write_to_new_playlist:
            src = await ctx.client.playlist(params.playlist_id)
            new = await ctx.client.create_playlist(ctx.user.spotify_id, f"{src['name']} (shuffled)")
            await ctx.client.add_items(new["id"], shuffled)
            return {"playlist_id": new["id"], "count": len(shuffled)}
        await ctx.client.replace_items(params.playlist_id, shuffled)
        return {"playlist_id": params.playlist_id, "count": len(shuffled)}
