"""Library tools that mine the user's own stream ledger — things Spotify itself cannot do
because it forgets everything past the last 50 plays."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.models import Stream
from app.services.analytics.top import COUNTS_AS_STREAM
from app.services.tools.base import Tool, ToolContext, registry


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=UTC)
    return start, end


@registry.register
class MonthlyBestOf(Tool):
    key = "library.monthly_best_of"
    pillar = "library"

    class Params(BaseModel):
        year: int = Field(..., ge=2006, le=2100)
        month: int = Field(..., ge=1, le=12)
        size: int = Field(50, ge=5, le=500)
        name: str | None = None

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        start, end = month_bounds(params.year, params.month)
        rows = await ctx.db.execute(
            select(Stream.track_id, func.count().label("n"))
            .where(
                Stream.user_id == ctx.user.id,
                Stream.track_id.isnot(None),
                Stream.played_at >= start,
                Stream.played_at < end,
                COUNTS_AS_STREAM,
            )
            .group_by(Stream.track_id)
            .order_by(func.count().desc())
            .limit(params.size)
        )
        uris = [f"spotify:track:{tid}" for tid, _ in rows.all()]
        name = params.name or f"Best of {start:%B %Y} · Spotule"
        new = await ctx.client.create_playlist(ctx.user.spotify_id, name, "From your Spotule history")
        await ctx.client.add_items(new["id"], uris)
        return {"playlist_id": new["id"], "count": len(uris)}


@registry.register
class ForgottenFavourites(Tool):
    key = "library.forgotten"
    pillar = "library"

    class Params(BaseModel):
        min_streams: int = Field(10, ge=2, description="Was a favourite: at least this many plays…")
        silent_months: int = Field(12, ge=1, description="…but nothing in this many months")
        size: int = Field(50, ge=5, le=500)
        name: str | None = None

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(days=30 * params.silent_months)
        rows = await ctx.db.execute(
            select(Stream.track_id, func.count().label("n"), func.max(Stream.played_at).label("last"))
            .where(Stream.user_id == ctx.user.id, Stream.track_id.isnot(None), COUNTS_AS_STREAM)
            .group_by(Stream.track_id)
            .having(func.count() >= params.min_streams, func.max(Stream.played_at) < cutoff)
            .order_by(func.count().desc())
            .limit(params.size)
        )
        uris = [f"spotify:track:{tid}" for tid, _n, _last in rows.all()]
        name = params.name or "Forgotten favourites · Spotule"
        new = await ctx.client.create_playlist(
            ctx.user.spotify_id, name, "Songs you loved and stopped playing"
        )
        await ctx.client.add_items(new["id"], uris)
        return {"playlist_id": new["id"], "count": len(uris)}


@registry.register
class LikedToPlaylist(Tool):
    key = "library.liked_to_playlist"
    pillar = "library"

    class Params(BaseModel):
        name: str = "Liked Songs (mirror)"
        target_playlist_id: str | None = Field(None, description="Update this one instead of creating")
        order: Literal["newest_first", "oldest_first"] = "newest_first"

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        uris = [i["track"]["uri"] async for i in ctx.client.saved_tracks() if i.get("track")]
        if params.order == "oldest_first":
            uris.reverse()
        if params.target_playlist_id:
            await ctx.client.replace_items(params.target_playlist_id, uris)
            return {"playlist_id": params.target_playlist_id, "count": len(uris)}
        new = await ctx.client.create_playlist(
            ctx.user.spotify_id, params.name, "Mirror of Liked Songs · Spotule"
        )
        await ctx.client.add_items(new["id"], uris)
        return {"playlist_id": new["id"], "count": len(uris)}
