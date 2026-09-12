"""Catalogue hydration: upsert Spotify track/artist/album payloads into shared tables and keep
artist genres cached in Redis for the skip guard's hot path."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import Keys, get_redis
from app.models import Album, Artist, ArtistGenre, Genre, Track, TrackArtist
from app.services.spotify import SpotifyClient

ARTIST_CACHE_TTL = 7 * 24 * 3600


def _img(obj: dict | None) -> str | None:
    images = (obj or {}).get("images") or []
    return images[0]["url"] if images else None


def dedupe_by_id(payloads: list[dict]) -> list[dict]:
    """One entry per Spotify id, keeping the fullest payload.

    Postgres refuses an ON CONFLICT DO UPDATE whose own VALUES list names the same key twice
    ("cannot affect row a second time"), and these payloads routinely repeat: the
    recently-played feed returns one entry per *play*, so replaying a track inside a single
    poll window was enough to fail that user's entire ingestion — which is exactly what it
    did in production, silently, for hours.

    Endpoints also disagree on how much they return for the same object: a simplified track
    carries no popularity and no ISRC, while /tracks does. When an id appears more than once
    the payload with more fields wins, so mixing sources never downgrades what we store.
    """
    best: dict[str, dict] = {}
    for item in payloads:
        held = best.get(item["id"])
        if held is None or len(item) >= len(held):
            best[item["id"]] = item
    return list(best.values())


async def upsert_genres(db: AsyncSession, names: set[str]) -> dict[str, int]:
    names = {n.strip().lower() for n in names if n and n.strip()}
    if not names:
        return {}
    stmt = insert(Genre).values([{"name": n} for n in names]).on_conflict_do_nothing()
    await db.execute(stmt)
    rows = await db.execute(select(Genre.id, Genre.name).where(Genre.name.in_(names)))
    return {name: gid for gid, name in rows.all()}


async def upsert_artists(db: AsyncSession, payloads: list[dict]) -> None:
    """Full artist objects (with genres) from /artists."""
    # /artists answers with a null in place of any id it does not recognise.
    payloads = dedupe_by_id([a for a in payloads if a and a.get("id")])
    if not payloads:
        return
    now = datetime.now(UTC)
    genre_ids = await upsert_genres(db, {g for a in payloads for g in a.get("genres", [])})
    rows = [
        {
            "id": a["id"],
            "name": a["name"],
            "image_url": _img(a),
            "popularity": a.get("popularity"),
            "followers": (a.get("followers") or {}).get("total"),
            "fetched_at": now,
        }
        for a in payloads
    ]
    stmt = insert(Artist).values(rows)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[Artist.id],
            set_={
                "name": stmt.excluded.name,
                "image_url": stmt.excluded.image_url,
                "popularity": stmt.excluded.popularity,
                "followers": stmt.excluded.followers,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
    )
    links = [
        {"artist_id": a["id"], "genre_id": genre_ids[g.lower()]}
        for a in payloads
        for g in a.get("genres", [])
        if g.lower() in genre_ids
    ]
    if links:
        await db.execute(insert(ArtistGenre).values(links).on_conflict_do_nothing())

    r = get_redis()
    pipe = r.pipeline()
    for a in payloads:
        pipe.set(
            Keys.artist(a["id"]),
            json.dumps({"name": a["name"], "genres": a.get("genres", [])}),
            ex=ARTIST_CACHE_TTL,
        )
    await pipe.execute()


async def upsert_tracks(db: AsyncSession, payloads: list[dict]) -> None:
    """Simplified or full track objects (from recently-played, playlist items, /tracks)."""
    payloads = dedupe_by_id(
        [t for t in payloads if t and t.get("id") and t.get("type", "track") == "track"]
    )
    if not payloads:
        return
    now = datetime.now(UTC)

    artist_rows: dict[str, dict] = {}
    album_rows: dict[str, dict] = {}
    for t in payloads:
        for a in t.get("artists", []) + (t.get("album") or {}).get("artists", []):
            if a.get("id"):
                artist_rows.setdefault(a["id"], {"id": a["id"], "name": a.get("name", "")})
        al = t.get("album")
        if al and al.get("id"):
            album_rows[al["id"]] = {
                "id": al["id"],
                "name": al.get("name", ""),
                "album_type": al.get("album_type"),
                "release_date": al.get("release_date"),
                "image_url": _img(al),
                "primary_artist_id": (al.get("artists") or [{}])[0].get("id"),
                "total_tracks": al.get("total_tracks"),
                "fetched_at": now,
            }
    if artist_rows:  # names only — genres hydrated later by `hydrate_missing_artists`
        await db.execute(insert(Artist).values(list(artist_rows.values())).on_conflict_do_nothing())
    if album_rows:
        stmt = insert(Album).values(list(album_rows.values()))
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Album.id],
                set_={
                    "name": stmt.excluded.name,
                    "image_url": stmt.excluded.image_url,
                    "release_date": stmt.excluded.release_date,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
        )

    track_rows = [
        {
            "id": t["id"],
            "name": t.get("name", ""),
            "album_id": (t.get("album") or {}).get("id"),
            "duration_ms": t.get("duration_ms"),
            "explicit": t.get("explicit"),
            "popularity": t.get("popularity"),
            "isrc": (t.get("external_ids") or {}).get("isrc"),
            "preview_url": t.get("preview_url"),
            "is_local": bool(t.get("is_local")),
            "fetched_at": now,
        }
        for t in payloads
    ]
    stmt = insert(Track).values(track_rows)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[Track.id],
            set_={
                "name": stmt.excluded.name,
                "album_id": stmt.excluded.album_id,
                "duration_ms": stmt.excluded.duration_ms,
                "popularity": stmt.excluded.popularity,
                "isrc": stmt.excluded.isrc,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
    )
    links = {
        (t["id"], a["id"]): {"track_id": t["id"], "artist_id": a["id"], "position": i}
        for t in payloads
        for i, a in enumerate(t.get("artists", []))
        if a.get("id")
    }
    if links:
        await db.execute(insert(TrackArtist).values(list(links.values())).on_conflict_do_nothing())


async def hydrate_missing_artists(db: AsyncSession, client: SpotifyClient, limit: int = 500) -> int:
    """Fetch full artist objects (genres) for artists we only know by name."""
    rows = await db.execute(select(Artist.id).where(Artist.fetched_at.is_(None)).limit(limit))
    ids = [r[0] for r in rows.all()]
    if ids:
        await upsert_artists(db, await client.artists(ids))
    return len(ids)


async def artist_genres_cached(artist_ids: list[str]) -> dict[str, list[str]]:
    """Hot path for the skip guard: Redis first, never touches Spotify."""
    r = get_redis()
    values = await r.mget([Keys.artist(a) for a in artist_ids])
    return {aid: json.loads(v)["genres"] for aid, v in zip(artist_ids, values, strict=True) if v}
