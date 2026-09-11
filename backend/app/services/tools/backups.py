"""Automated Backups — snapshot Discover Weekly / Release Radar / any playlist.

⚠ Since 2024-11-27, Development-mode apps cannot read Spotify-owned algorithmic playlists
(Discover Weekly, Release Radar, Daily Mix…) via /playlists/{id}. Strategy:
  1. Try the API (works for Extended-Quota apps).
  2. Fallback "shadow capture": the stream logger records `context_uri`; every play whose
     context is the Discover Weekly URI is attributed to that week's snapshot. By Sunday night
     the user has heard the list ⇒ we have most of it, legitimately, from their own history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select

from app.models import PlaylistBackup, Stream
from app.models.enums import BackupKind
from app.services.spotify import SpotifyAPIError
from app.services.tools.base import Tool, ToolContext, registry


def week_label(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(UTC)
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


@registry.register
class BackupPlaylist(Tool):
    key = "backup.playlist"
    pillar = "backup"

    class Params(BaseModel):
        playlist_id: str
        kind: BackupKind = BackupKind.manual
        materialize: bool = True  # also create "Discover Weekly · 2026-W37" on Spotify

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        uris: list[str] = []
        name = params.kind.value.replace("_", " ").title()
        try:
            pl = await ctx.client.playlist(params.playlist_id)
            name = pl["name"]
            uris = [
                i["item"]["uri"]
                async for i in ctx.client.playlist_items(params.playlist_id)
                if i.get("item") and i["item"].get("uri")
            ]
            capture = "api"
        except SpotifyAPIError as exc:
            if exc.status not in (403, 404):
                raise
            # shadow capture from the user's own stream ledger (this ISO week)
            iso_year, iso_week, _ = datetime.now(UTC).isocalendar()
            week_start = datetime.fromisocalendar(iso_year, iso_week, 1).replace(tzinfo=UTC)
            rows = await ctx.db.execute(
                select(Stream.spotify_track_uri)
                .where(
                    Stream.user_id == ctx.user.id,
                    Stream.context_uri == f"spotify:playlist:{params.playlist_id}",
                    Stream.played_at >= week_start,
                )
                .distinct()
            )
            uris = [r[0] for r in rows.all() if r[0]]
            capture = "shadow"

        label = week_label()
        backup = PlaylistBackup(
            user_id=ctx.user.id,
            kind=params.kind,
            source_playlist_id=params.playlist_id,
            source_name=name,
            week_label=label,
            track_uris=uris,
            track_count=len(uris),
            meta={"capture": capture},
        )
        if params.materialize and uris:
            new = await ctx.client.create_playlist(
                ctx.user.spotify_id, f"{name} · {label}", "Backup by SpotiMax"
            )
            await ctx.client.add_items(new["id"], uris)
            backup.materialized_playlist_id = new["id"]
        ctx.db.add(backup)
        await ctx.db.commit()
        return {
            "backup_id": str(backup.id),
            "tracks": len(uris),
            "capture": capture,
            "playlist_id": backup.materialized_playlist_id,
        }


@registry.register
class RestoreBackup(Tool):
    key = "backup.restore"
    pillar = "backup"
    destructive = True

    class Params(BaseModel):
        backup_id: str
        target_playlist_id: str | None = None  # None → new playlist

    async def backup_targets(self, params: Params) -> list[str]:
        return [params.target_playlist_id] if params.target_playlist_id else []

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        backup = await ctx.db.get(PlaylistBackup, params.backup_id)
        if backup is None or backup.user_id != ctx.user.id:
            raise ValueError("backup not found")
        if params.target_playlist_id:
            await ctx.client.replace_items(params.target_playlist_id, backup.track_uris)
            return {"playlist_id": params.target_playlist_id, "tracks": backup.track_count}
        new = await ctx.client.create_playlist(ctx.user.spotify_id, f"{backup.source_name} (restored)")
        await ctx.client.add_items(new["id"], backup.track_uris)
        return {"playlist_id": new["id"], "tracks": backup.track_count}
