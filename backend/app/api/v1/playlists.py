from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Spotify
from app.models import PlaylistBackup

router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.get("")
async def my_playlists(user: CurrentUser, client: Spotify, limit: int = Query(50, le=50), offset: int = 0):
    """Live from Spotify (small payload); the mirror tables are for analytics, not browsing."""
    page = await client.get("/me/playlists", limit=limit, offset=offset)
    return {
        "total": page.get("total"),
        "items": [
            {
                "id": p["id"],
                "name": p["name"],
                "owner": p["owner"]["id"],
                "is_owner": p["owner"]["id"] == user.spotify_id,
                "public": p.get("public"),
                "collaborative": p.get("collaborative"),
                "tracks": p["tracks"]["total"],
                "image": (p.get("images") or [{}])[0].get("url"),
                "snapshot_id": p.get("snapshot_id"),
            }
            for p in page.get("items", [])
        ],
    }


@router.get("/backups")
async def backups(user: CurrentUser, db: DB, limit: int = 50):
    rows = (
        (
            await db.execute(
                select(PlaylistBackup)
                .where(PlaylistBackup.user_id == user.id)
                .order_by(PlaylistBackup.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(b.id),
            "kind": b.kind.value,
            "source_name": b.source_name,
            "week": b.week_label,
            "tracks": b.track_count,
            "materialized_playlist_id": b.materialized_playlist_id,
            "created_at": b.created_at,
        }
        for b in rows
    ]
