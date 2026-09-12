"""Raw JSON Importer — streams Spotify's "Extended streaming history" ZIP into `streams`.

Format (one object per play, files named Streaming_History_Audio_YYYY-YYYY_N.json):
  {"ts":"2023-04-11T20:14:03Z","platform":"android","ms_played":214000,"conn_country":"FR",
   "master_metadata_track_name":"…","master_metadata_album_artist_name":"…",
   "master_metadata_album_album_name":"…","spotify_track_uri":"spotify:track:…",
   "episode_name":null,"spotify_episode_uri":null,"reason_start":"trackdone",
   "reason_end":"trackdone","shuffle":false,"skipped":false,"offline":false,"incognito_mode":false}

Streaming parse (ijson) + COPY-sized batches keep memory flat for multi-million-row exports.
Also accepts the small "Account data" StreamingHistory_music_N.json format (endTime, artistName,
trackName, msPlayed) as a fallback.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import ijson
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.counts import inserted_count
from app.models import ImportJob, Stream
from app.models.enums import JobStatus, StreamSource

BATCH = 5_000
MIN_MS_PLAYED = 0  # keep everything; analytics decides what counts as a "stream" (default ≥30s)


def _entry_items(zip_path: Path, name: str) -> Iterator[dict]:
    with zipfile.ZipFile(zip_path) as zf, zf.open(name) as fh:
        yield from ijson.items(fh, "item")


def _iter_zip_entries(zip_path: Path) -> Iterator[tuple[str, Iterator[dict]]]:
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(
            n
            for n in zf.namelist()
            if n.endswith(".json") and ("Streaming_History" in n or "StreamingHistory" in n)
        )
    for name in names:
        yield name, _entry_items(zip_path, name)


def _normalise(raw: dict) -> dict | None:
    if "ts" in raw:  # extended format
        uri = raw.get("spotify_track_uri") or raw.get("spotify_episode_uri")
        name = raw.get("master_metadata_track_name") or raw.get("episode_name")
        if not name and not uri:
            return None
        played_at = datetime.fromisoformat(raw["ts"].replace("Z", "+00:00"))
        return {
            "spotify_track_uri": uri,
            # FK is attached later by `relink_imported_streams` once the catalogue row exists
            "track_id": None,
            "played_at": played_at,
            "ms_played": raw.get("ms_played"),
            "track_name": name,
            "artist_name": raw.get("master_metadata_album_artist_name") or raw.get("episode_show_name"),
            "album_name": raw.get("master_metadata_album_album_name"),
            "platform": (raw.get("platform") or "")[:64] or None,
            "country": raw.get("conn_country"),
            "reason_start": raw.get("reason_start"),
            "reason_end": raw.get("reason_end"),
            "shuffle": raw.get("shuffle"),
            "skipped": raw.get("skipped"),
            "offline": raw.get("offline"),
            "incognito": raw.get("incognito_mode"),
        }
    if "endTime" in raw:  # account-data (1 year) format, minute precision, no URI
        played_at = datetime.strptime(raw["endTime"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        return {
            "spotify_track_uri": None,
            "track_id": None,
            "played_at": played_at,
            "ms_played": raw.get("msPlayed"),
            "track_name": raw.get("trackName"),
            "artist_name": raw.get("artistName"),
            "album_name": None,
        }
    return None


def run_import(db: Session, job: ImportJob) -> None:
    job.status = JobStatus.running
    job.started_at = datetime.now(UTC)
    db.commit()

    zip_path = Path(job.storage_key)
    batch: list[dict] = []
    earliest: datetime | None = None
    latest: datetime | None = None
    unresolved: set[str] = set()

    def flush() -> None:
        nonlocal batch
        if not batch:
            return
        added = inserted_count(
            db.execute(insert(Stream).values(batch).on_conflict_do_nothing().returning(Stream.id))
        )
        job.rows_inserted += added
        job.rows_skipped_duplicate += len(batch) - added
        db.commit()
        batch = []

    try:
        with zipfile.ZipFile(zip_path) as zf:
            job.files_total = sum(1 for n in zf.namelist() if n.endswith(".json"))
        for _name, items in _iter_zip_entries(zip_path):
            for raw in items:
                job.rows_total += 1
                row = _normalise(raw)
                if row is None:
                    job.rows_skipped_invalid += 1
                    continue
                row["user_id"] = job.user_id
                row["source"] = StreamSource.json_import
                earliest = row["played_at"] if earliest is None else min(earliest, row["played_at"])
                latest = row["played_at"] if latest is None else max(latest, row["played_at"])
                if row["spotify_track_uri"] and row["spotify_track_uri"].startswith("spotify:track:"):
                    unresolved.add(row["spotify_track_uri"])
                batch.append(row)
                if len(batch) >= BATCH:
                    flush()
            job.files_done += 1
            db.commit()
        flush()

        # Imported rows carry only the URI; the catalogue worker hydrates `tracks` in
        # batches of 50 and `relink_imported_streams` attaches the FK afterwards.
        job.unresolved_track_uris = len(unresolved)
        job.earliest_played_at, job.latest_played_at = earliest, latest
        job.status = JobStatus.succeeded
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.failed
        job.error = str(exc)[:1000]
        raise
    finally:
        job.finished_at = datetime.now(UTC)
        db.commit()


def relink_imported_streams(db: Session, user_id) -> int:
    """After catalogue hydration, attach `track_id` to imported rows matched by URI."""
    from app.models import Track

    stmt = (
        Stream.__table__.update()
        .where(
            Stream.user_id == user_id,
            Stream.track_id.is_(None),
            Stream.spotify_track_uri.isnot(None),
            func.split_part(Stream.spotify_track_uri, ":", 3).in_(select(Track.id)),
        )
        .values(track_id=func.split_part(Stream.spotify_track_uri, ":", 3))
    )
    return db.execute(stmt).rowcount or 0
