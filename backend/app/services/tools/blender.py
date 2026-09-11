"""The Blender & Splitter."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.tools.base import Tool, ToolContext, registry


@registry.register
class Blender(Tool):
    key = "playlist.blend"
    pillar = "playlists"

    class Params(BaseModel):
        source_playlist_ids: list[str] = Field(min_length=2, max_length=10)
        name: str
        dedupe: bool = True
        strategy: Literal["append", "interleave"] = "interleave"
        public: bool = False

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        lists: list[list[str]] = []
        for pid in params.source_playlist_ids:
            lists.append(
                [
                    i["item"]["uri"]
                    async for i in ctx.client.playlist_items(pid)
                    if i.get("item") and i["item"].get("uri")
                ]
            )
            ctx.report_progress(int(40 * len(lists) / len(params.source_playlist_ids)))
        merged: list[str] = []
        if params.strategy == "append":
            for lst in lists:
                merged.extend(lst)
        else:  # round-robin interleave
            longest = max(len(x) for x in lists)
            for i in range(longest):
                for lst in lists:
                    if i < len(lst):
                        merged.append(lst[i])
        if params.dedupe:
            seen: set[str] = set()
            merged = [u for u in merged if not (u in seen or seen.add(u))]
        new = await ctx.client.create_playlist(
            ctx.user.spotify_id, params.name, "Blended with SpotiMax", params.public
        )
        await ctx.client.add_items(new["id"], merged)
        return {"playlist_id": new["id"], "count": len(merged), "sources": len(lists)}


@registry.register
class Splitter(Tool):
    key = "playlist.split"
    pillar = "playlists"

    class Params(BaseModel):
        playlist_id: str
        chunk_size: int = Field(500, ge=10, le=10_000)
        name_template: str = "{name} · Vol. {n}"

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        src = await ctx.client.playlist(params.playlist_id)
        uris = [
            i["item"]["uri"]
            async for i in ctx.client.playlist_items(params.playlist_id)
            if i.get("item") and i["item"].get("uri")
        ]
        created: list[str] = []
        for n, start in enumerate(range(0, len(uris), params.chunk_size), start=1):
            name = params.name_template.format(name=src["name"], n=n)
            new = await ctx.client.create_playlist(ctx.user.spotify_id, name)
            await ctx.client.add_items(new["id"], uris[start : start + params.chunk_size])
            created.append(new["id"])
            ctx.report_progress(int(100 * (start + params.chunk_size) / max(len(uris), 1)))
        return {"created": created, "volumes": len(created), "total": len(uris)}
