"""Bulk Commander — mass delete / unfollow / describe. Every destructive run snapshots first."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.services.tools.base import Tool, ToolContext, registry


@registry.register
class BulkDeletePlaylists(Tool):
    key = "bulk.delete_playlists"
    pillar = "bulk"
    destructive = True

    class Params(BaseModel):
        playlist_ids: list[str] = Field(min_length=1, max_length=500)

    async def backup_targets(self, params: Params) -> list[str]:
        return params.playlist_ids

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        done: list[str] = []
        for i, pid in enumerate(params.playlist_ids):
            await ctx.client.unfollow_playlist(pid)
            done.append(pid)
            ctx.report_progress(int(100 * (i + 1) / len(params.playlist_ids)))
        return {"deleted": done}


@registry.register
class BulkUnfollowArtists(Tool):
    key = "bulk.unfollow_artists"
    pillar = "bulk"
    destructive = True

    class Params(BaseModel):
        artist_ids: list[str] = Field(min_length=1, max_length=5000)

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        await ctx.client.unfollow_artists(params.artist_ids)
        return {"unfollowed": len(params.artist_ids)}


@registry.register
class BulkDescriptionUpdate(Tool):
    key = "bulk.update_descriptions"
    pillar = "bulk"

    class Params(BaseModel):
        playlist_ids: list[str] = Field(min_length=1, max_length=500)
        template: str = Field(..., description="Supports {name}, {count}, {date}")

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        from datetime import UTC, datetime

        for pid in params.playlist_ids:
            pl = await ctx.client.playlist(pid)
            desc = params.template.format(
                name=pl["name"], count=pl["tracks"]["total"], date=datetime.now(UTC).date().isoformat()
            )
            await ctx.client.change_playlist_details(pid, description=desc[:300])
        return {"updated": len(params.playlist_ids)}


@registry.register
class BulkDedupePlaylist(Tool):
    key = "bulk.dedupe_playlist"
    pillar = "bulk"
    destructive = True

    class Params(BaseModel):
        playlist_id: str
        match_by_isrc: bool = True  # catches the same recording on different releases

    async def backup_targets(self, params: Params) -> list[str]:
        return [params.playlist_id]

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        seen: set[str] = set()
        keep: list[str] = []
        removed = 0
        async for i in ctx.client.playlist_items(params.playlist_id):
            t = i.get("item") or {}
            if not t.get("uri"):
                continue
            key = (t.get("external_ids") or {}).get("isrc") if params.match_by_isrc else None
            key = key or t["uri"]
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            keep.append(t["uri"])
        if removed:
            await ctx.client.replace_items(params.playlist_id, keep)
        return {"removed": removed, "kept": len(keep)}


def render_name(template: str, name: str, index: int, count: int) -> str:
    """Template fields: {name} {index} {count} {date}. Unknown fields are left as-is."""
    from datetime import UTC, datetime

    class _Safe(dict):
        def __missing__(self, key):  # keep "{unknown}" literal instead of raising
            return "{" + key + "}"

    return template.format_map(
        _Safe(name=name, index=index, count=count, date=datetime.now(UTC).date().isoformat())
    )[:100]


@registry.register
class BulkRename(Tool):
    key = "bulk.rename"
    pillar = "bulk"

    class Params(BaseModel):
        playlist_ids: list[str] = Field(min_length=1, max_length=500)
        template: str = Field(..., description="e.g. '{name} · archived {date}' or 'Mix {index}'")

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        renamed: list[dict[str, str]] = []
        for i, pid in enumerate(params.playlist_ids, start=1):
            pl = await ctx.client.playlist(pid)
            new_name = render_name(params.template, pl["name"], i, len(params.playlist_ids))
            await ctx.client.change_playlist_details(pid, name=new_name)
            renamed.append({"id": pid, "from": pl["name"], "to": new_name})
            ctx.report_progress(int(100 * i / len(params.playlist_ids)))
        return {"renamed": renamed}


@registry.register
class BulkSetVisibility(Tool):
    key = "bulk.set_visibility"
    pillar = "bulk"

    class Params(BaseModel):
        playlist_ids: list[str] = Field(min_length=1, max_length=500)
        public: bool

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        for i, pid in enumerate(params.playlist_ids, start=1):
            await ctx.client.change_playlist_details(pid, public=params.public)
            ctx.report_progress(int(100 * i / len(params.playlist_ids)))
        return {"updated": len(params.playlist_ids), "public": params.public}
