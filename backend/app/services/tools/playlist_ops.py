"""Playlist compactor operations: reverse, sort, copy, set operations, pruning.

Each tool reads the full item list once, computes the new order as a pure function (tested
without Spotify), and writes it back in one `replace_items`. Destructive ones snapshot first.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.tools.base import Tool, ToolContext, registry

SortKey = Literal["added_at", "name", "artist", "album", "duration", "release_year", "popularity"]


def _release_year(track: dict) -> int:
    date = ((track.get("album") or {}).get("release_date") or "")[:4]
    return int(date) if date.isdigit() else 0


def sort_items(items: list[dict], key: SortKey, descending: bool = False) -> list[dict]:
    """Stable sort of playlist items (each `{added_at, item}`) by a musical attribute."""

    def k(entry: dict):
        tr = entry.get("item") or {}
        if key == "added_at":
            return entry.get("added_at") or ""
        if key == "name":
            return (tr.get("name") or "").lower()
        if key == "artist":
            return ((tr.get("artists") or [{}])[0].get("name") or "").lower()
        if key == "album":
            return ((tr.get("album") or {}).get("name") or "").lower()
        if key == "duration":
            return tr.get("duration_ms") or 0
        if key == "release_year":
            return _release_year(tr)
        return tr.get("popularity") or 0

    return sorted(items, key=k, reverse=descending)


def set_operation(a: list[str], b: list[str], op: Literal["subtract", "intersect", "union"]) -> list[str]:
    """Order-preserving set operations on URI lists (order of `a` wins)."""
    sb = set(b)
    if op == "subtract":
        return [u for u in a if u not in sb]
    if op == "intersect":
        return [u for u in a if u in sb]
    seen: set[str] = set()
    return [u for u in [*a, *b] if not (u in seen or seen.add(u))]


def is_unavailable(track: dict) -> bool:
    """Greyed-out in the client: no id (removed), or is_playable explicitly false."""
    if not track or not track.get("id"):
        return True
    return track.get("is_playable") is False


async def _items(ctx: ToolContext, playlist_id: str) -> list[dict]:
    return [i async for i in ctx.client.playlist_items(playlist_id) if i.get("item")]


def _uris(items: list[dict]) -> list[str]:
    return [i["item"]["uri"] for i in items if i["item"].get("uri")]


@registry.register
class ReversePlaylist(Tool):
    key = "playlist.reverse"
    pillar = "playlists"
    destructive = True

    class Params(BaseModel):
        playlist_id: str

    async def backup_targets(self, params: Params) -> list[str]:
        return [params.playlist_id]

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        uris = _uris(await _items(ctx, params.playlist_id))
        await ctx.client.replace_items(params.playlist_id, list(reversed(uris)))
        return {"playlist_id": params.playlist_id, "count": len(uris)}


@registry.register
class SortPlaylist(Tool):
    key = "playlist.sort"
    pillar = "playlists"
    destructive = True

    class Params(BaseModel):
        playlist_id: str
        by: SortKey = "added_at"
        descending: bool = False

    async def backup_targets(self, params: Params) -> list[str]:
        return [params.playlist_id]

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        items = sort_items(await _items(ctx, params.playlist_id), params.by, params.descending)
        await ctx.client.replace_items(params.playlist_id, _uris(items))
        return {"playlist_id": params.playlist_id, "count": len(items), "by": params.by}


@registry.register
class CopyPlaylist(Tool):
    key = "playlist.copy"
    pillar = "playlists"

    class Params(BaseModel):
        playlist_id: str
        name: str | None = Field(None, description="Defaults to '<original> (copy)'")
        public: bool = False

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        src = await ctx.client.playlist(params.playlist_id)
        uris = _uris(await _items(ctx, params.playlist_id))
        new = await ctx.client.create_playlist(
            ctx.user.spotify_id,
            params.name or f"{src['name']} (copy)",
            src.get("description") or "",
            params.public,
        )
        await ctx.client.add_items(new["id"], uris)
        return {"playlist_id": new["id"], "count": len(uris)}


@registry.register
class PlaylistSetOps(Tool):
    key = "playlist.set_ops"
    pillar = "playlists"

    class Params(BaseModel):
        playlist_a: str
        playlist_b: str
        operation: Literal["subtract", "intersect", "union"] = "subtract"
        name: str

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        a = _uris(await _items(ctx, params.playlist_a))
        b = _uris(await _items(ctx, params.playlist_b))
        result = set_operation(a, b, params.operation)
        new = await ctx.client.create_playlist(
            ctx.user.spotify_id, params.name, f"{params.operation} · Spotule"
        )
        await ctx.client.add_items(new["id"], result)
        return {"playlist_id": new["id"], "count": len(result), "a": len(a), "b": len(b)}


@registry.register
class PruneUnavailable(Tool):
    key = "playlist.prune_unavailable"
    pillar = "playlists"
    destructive = True

    class Params(BaseModel):
        playlist_id: str

    async def backup_targets(self, params: Params) -> list[str]:
        return [params.playlist_id]

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        raw = [i async for i in ctx.client.playlist_items(params.playlist_id)]
        keep = [i["item"]["uri"] for i in raw if i.get("item") and not is_unavailable(i["item"])]
        removed = len(raw) - len(keep)
        if removed:
            await ctx.client.replace_items(params.playlist_id, keep)
        return {"playlist_id": params.playlist_id, "removed": removed, "kept": len(keep)}


@registry.register
class SubtractLiked(Tool):
    key = "playlist.subtract_liked"
    pillar = "playlists"
    destructive = True

    class Params(BaseModel):
        playlist_id: str

    async def backup_targets(self, params: Params) -> list[str]:
        return [params.playlist_id]

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        uris = _uris(await _items(ctx, params.playlist_id))
        liked = [i["track"]["uri"] async for i in ctx.client.saved_tracks() if i.get("track")]
        keep = set_operation(uris, liked, "subtract")
        if len(keep) != len(uris):
            await ctx.client.replace_items(params.playlist_id, keep)
        return {"playlist_id": params.playlist_id, "removed": len(uris) - len(keep), "kept": len(keep)}


@registry.register
class ExportPlaylist(Tool):
    key = "playlist.export"
    pillar = "playlists"
    async_run = False

    class Params(BaseModel):
        playlist_id: str

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        """Returns rows the UI can turn into CSV; no Spotify writes."""
        rows = [
            {
                "uri": i["item"].get("uri"),
                "name": i["item"].get("name"),
                "artists": ", ".join(a.get("name", "") for a in i["item"].get("artists", [])),
                "album": (i["item"].get("album") or {}).get("name"),
                "duration_ms": i["item"].get("duration_ms"),
                "added_at": i.get("added_at"),
                "isrc": (i["item"].get("external_ids") or {}).get("isrc"),
            }
            for i in await _items(ctx, params.playlist_id)
        ]
        return {"rows": rows, "count": len(rows)}
