"""Library Purger: scan Liked Songs / playlists, report matches, optionally remove them.
Always takes a `pre_purge` PlaylistBackup first so every purge is reversible."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlaylistBackup, PurgeRun
from app.models.enums import BackupKind, JobStatus, PurgeTarget
from app.services.banhammer.registry import Blacklist
from app.services.catalog import artist_genres_cached, upsert_artists, upsert_tracks
from app.services.spotify import SpotifyClient


async def _genres_for(db: AsyncSession, client: SpotifyClient, artist_ids: set[str]) -> dict[str, list[str]]:
    ids = list(artist_ids)
    genres = await artist_genres_cached(ids)
    missing = [a for a in ids if a not in genres]
    if missing:
        await upsert_artists(db, await client.artists(missing))
        genres.update(await artist_genres_cached(missing))
    return genres


async def run_purge(db: AsyncSession, client: SpotifyClient, run: PurgeRun, blacklist: Blacklist) -> PurgeRun:
    run.status = JobStatus.running
    run.started_at = datetime.now(UTC)
    await db.commit()
    try:
        if run.target == PurgeTarget.liked_songs:
            items = [i["track"] async for i in client.saved_tracks() if i.get("track")]
            source_name = "Liked Songs"
        else:
            items = [i["item"] async for i in client.playlist_items(run.target_playlist_id) if i.get("item")]
            source_name = (await client.playlist(run.target_playlist_id))["name"]
        items = [t for t in items if t.get("id")]
        await upsert_tracks(db, items)
        run.scanned_count = len(items)

        genres = await _genres_for(
            db, client, {a["id"] for t in items for a in t.get("artists", []) if a.get("id")}
        )
        matched: list[dict] = []
        for t in items:
            v = blacklist.evaluate(
                t["id"],
                (t.get("album") or {}).get("id"),
                {a["id"]: genres.get(a["id"], []) for a in t.get("artists", []) if a.get("id")},
                context="purge",
            )
            if v.banned:
                matched.append(
                    {
                        "track_id": t["id"],
                        "uri": t["uri"],
                        "name": t["name"],
                        "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                        "genre": v.genre,
                        "rule": v.rule,
                    }
                )
        run.matched_count = len(matched)
        run.report = matched

        if matched and not run.dry_run:
            backup = PlaylistBackup(
                user_id=run.user_id,
                kind=BackupKind.pre_purge,
                source_playlist_id=run.target_playlist_id,
                source_name=source_name,
                track_uris=[t["uri"] for t in items],
                track_count=len(items),
                meta={"purge_run_id": str(run.id)},
            )
            db.add(backup)
            await db.flush()
            run.backup_id = backup.id
            if run.target == PurgeTarget.liked_songs:
                await client.remove_saved_tracks([m["track_id"] for m in matched])
            else:
                await client.remove_items(run.target_playlist_id, [m["uri"] for m in matched])
            run.removed_count = len(matched)
        run.status = JobStatus.succeeded
    except Exception as exc:  # noqa: BLE001
        run.status = JobStatus.failed
        run.error = str(exc)[:1000]
    run.finished_at = datetime.now(UTC)
    await db.commit()
    return run
