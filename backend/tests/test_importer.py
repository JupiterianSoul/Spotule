import io
import json
import zipfile
from datetime import UTC

from app.services.ingest.json_importer import _iter_zip_entries, _normalise


def test_normalise_extended_format():
    row = _normalise(
        {
            "ts": "2023-04-11T20:14:03Z",
            "platform": "android",
            "ms_played": 214000,
            "conn_country": "FR",
            "master_metadata_track_name": "Song",
            "master_metadata_album_artist_name": "Artist",
            "master_metadata_album_album_name": "Album",
            "spotify_track_uri": "spotify:track:abc",
            "reason_start": "trackdone",
            "reason_end": "trackdone",
            "shuffle": True,
            "skipped": False,
            "offline": False,
            "incognito_mode": False,
        }
    )
    assert row["spotify_track_uri"] == "spotify:track:abc"
    assert row["track_id"] is None  # linked later, after catalogue hydration
    assert row["played_at"].tzinfo is not None and row["played_at"].year == 2023
    assert row["ms_played"] == 214000 and row["shuffle"] is True


def test_normalise_account_data_format():
    row = _normalise({"endTime": "2024-01-05 13:37", "artistName": "A", "trackName": "T", "msPlayed": 1000})
    assert row["track_name"] == "T" and row["played_at"].tzinfo == UTC


def test_normalise_rejects_empty():
    assert _normalise({"ts": "2023-04-11T20:14:03Z"}) is None
    assert _normalise({"foo": "bar"}) is None


def test_zip_streaming(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "Spotify Extended Streaming History/Streaming_History_Audio_2023_0.json",
            json.dumps(
                [
                    {
                        "ts": "2023-01-01T00:00:00Z",
                        "spotify_track_uri": "spotify:track:x",
                        "master_metadata_track_name": "X",
                        "ms_played": 40000,
                    }
                ]
            ),
        )
        zf.writestr("ReadMeFirst.pdf", b"...")
    p = tmp_path / "export.zip"
    p.write_bytes(buf.getvalue())
    entries = list(_iter_zip_entries(p))
    assert len(entries) == 1
    name, items = entries[0]
    assert [i["ms_played"] for i in items] == [40000]
