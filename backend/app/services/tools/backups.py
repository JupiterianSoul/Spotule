"""Automated Backups — snapshot Discover Weekly / Release Radar / Liked Songs / any playlist.

⚠ Since 2024-11-27, Development-mode apps cannot read Spotify-owned algorithmic playlists
(Discover Weekly, Release Radar, Daily Mix…) via /playlists/{id}. Strategy:
  1. Try the API (works for Extended-Quota apps).
  2. Fallback "shadow capture": the stream logger records `context_uri`; every play whose
     context is the Discover Weekly URI is attributed to that week's snapshot. By Sunday night
     the user has heard the list ⇒ we have most of it, legitimately, from their own history.

Scheduled runs pass only a `kind`, because nobody wants to look up a playlist id to enable a
weekly backup. `resolve_playlist_id` finds it by scanning the user's own playlists for the
Spotify-owned one whose name matches, in any of the languages Spotify localises it into.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select

from app.models import PlaylistBackup, Stream
from app.models.enums import BackupKind
from app.services.spotify import SpotifyAPIError, SpotifyClient
from app.services.tools.base import Tool, ToolContext, registry

SPOTIFY_OWNER_ID = "spotify"

# Spotify renames these per account language. Lower-cased, accent-sensitive as Spotify spells them.
KIND_NAMES: dict[BackupKind, tuple[str, ...]] = {
    BackupKind.discover_weekly: (
        "discover weekly",
        "découvertes de la semaine",
        "descubrimiento semanal",
        "mix der woche",
        "scoperte della settimana",
    ),
    BackupKind.release_radar: (
        "release radar",
        "radar des sorties",
        "radar de novedades",
        "radar de lançamentos",
    ),
}


def matches_kind(playlist_name: str, owner_id: str, kind: BackupKind) -> bool:
    """True when a playlist is Spotify's own algorithmic list for this backup kind."""
    if owner_id != SPOTIFY_OWNER_ID:
        return False
    names = KIND_NAMES.get(kind)
    if not names:
        return False
    normalised = playlist_name.strip().lower()
    return any(candidate and normalised == candidate for candidate in names)


async def resolve_playlist_id(client: SpotifyClient, kind: BackupKind) -> str | None:
    async for playlist in client.my_playlists():
        if not playlist:
            continue
        owner = (playlist.get("owner") or {}).get("id", "")
        if matches_kind(playlist.get("name", ""), owner, kind):
            return playlist["id"]
    return None


def week_label(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(UTC)
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


@registry.register
class BackupPlaylist(Tool):
    key = "backup.playlist"
    pillar = "backup"

    class Params(BaseModel):
        # Optional so a scheduled run can pass only `kind` and have the playlist found for it.
        playlist_id: str | None = None
        kind: BackupKind = BackupKind.manual
        materialize: bool = True  # also create "Discover Weekly · 2026-W37" on Spotify

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        playlist_id = params.playlist_id or await resolve_playlist_id(ctx.client, params.kind)
        if not playlist_id:
            raise ValueError(
                f"Could not find your {params.kind.value.replace('_', ' ')} playlist. Follow it in "
                "Spotify, or set playlist_id in this automation's config."
            )

        uris: list[str] = []
        name = params.kind.value.replace("_", " ").title()
        try:
            pl = await ctx.client.playlist(playlist_id)
            name = pl["name"]
            uris = [
                i["item"]["uri"]
                async for i in ctx.client.playlist_items(playlist_id)
                if i.get("item") and i["item"].get("uri")
            ]
            capture = "api"
        except SpotifyAPIError as exc:
            if exc.status not in (403, 404):
                raise
            # Shadow capture from the user's own stream ledger (this ISO week).
            iso_year, iso_week, _ = datetime.now(UTC).isocalendar()
            week_start = datetime.fromisocalendar(iso_year, iso_week, 1).replace(tzinfo=UTC)
            rows = await ctx.db.execute(
                select(Stream.spotify_track_uri)
                .where(
                    Stream.user_id == ctx.user.id,
                    Stream.context_uri == f"spotify:playlist:{playlist_id}",
                    Stream.played_at >= week_start,
                )
                .distinct()
            )
            uris = [r[0] for r in rows.all() if r[0]]
            capture = "shadow"

        return await _store_backup(ctx, params.kind, playlist_id, name, uris, params.materialize,
                                   capture)


@registry.register
class BackupLikedSongs(Tool):
    key = "backup.liked_songs"
    pillar = "backup"

    class Params(BaseModel):
        kind: BackupKind = BackupKind.manual
        materialize: bool = False  # a full Liked Songs copy is usually unwanted clutter

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        uris = [
            item["track"]["uri"]
            async for item in ctx.client.saved_tracks()
            if item.get("track") and item["track"].get("uri")
        ]
        return await _store_backup(ctx, params.kind, None, "Liked Songs", uris,
                                   params.materialize, "api")


async def _store_backup(ctx: ToolContext, kind: BackupKind, source_playlist_id: str | None,
                        name: str, uris: list[str], materialize: bool, capture: str) -> dict[str, Any]:
    label = week_label()
    backup = PlaylistBackup(
        user_id=ctx.user.id,
        kind=kind,
        source_playlist_id=source_playlist_id,
        source_name=name,
        week_label=label,
        track_uris=uris,
        track_count=len(uris),
        meta={"capture": capture},
    )
    if materialize and uris:
        new = await ctx.client.create_playlist(
            ctx.user.spotify_id, f"{name} · {label}", "Backup by Spotule"
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
        new = await ctx.client.create_playlist(
            ctx.user.spotify_id, f"{backup.source_name} (restored)"
        )
        await ctx.client.add_items(new["id"], backup.track_uris)
        return {"playlist_id": new["id"], "tracks": backup.track_count}
