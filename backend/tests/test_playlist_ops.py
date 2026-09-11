from app.services.tools.bulk import render_name
from app.services.tools.library import month_bounds
from app.services.tools.playlist_ops import is_unavailable, set_operation, sort_items
from app.services.tools.sonic_filter import MOOD_PRESETS, SonicFilter

A, B, C = "spotify:track:a", "spotify:track:b", "spotify:track:c"


def test_set_operations_preserve_order_of_a():
    assert set_operation([A, B, C], [B], "subtract") == [A, C]
    assert set_operation([A, B, C], [C, B], "intersect") == [B, C]
    assert set_operation([A, B], [B, C], "union") == [A, B, C]


def test_sort_by_each_key_is_stable_and_handles_missing_fields():
    items = [
        {
            "added_at": "2024-02-01",
            "item": {
                "name": "b",
                "duration_ms": 200,
                "popularity": 5,
                "artists": [{"name": "Zed"}],
                "album": {"name": "Y", "release_date": "1999-01-01"},
            },
        },
        {"added_at": "2024-01-01", "item": {"name": "A", "duration_ms": 100, "artists": [], "album": {}}},
        {
            "added_at": "2024-03-01",
            "item": {
                "name": "c",
                "duration_ms": 300,
                "popularity": 50,
                "artists": [{"name": "Ann"}],
                "album": {"release_date": "2020"},
            },
        },
    ]
    assert [i["item"]["name"] for i in sort_items(items, "added_at")] == ["A", "b", "c"]
    assert [i["item"]["name"] for i in sort_items(items, "name")] == ["A", "b", "c"]  # case-insensitive
    assert [i["item"]["name"] for i in sort_items(items, "artist")] == ["A", "c", "b"]  # missing sorts first
    assert [i["item"]["name"] for i in sort_items(items, "duration", descending=True)] == ["c", "b", "A"]
    assert [i["item"]["name"] for i in sort_items(items, "release_year")] == ["A", "b", "c"]
    assert [i["item"]["name"] for i in sort_items(items, "popularity", descending=True)] == ["c", "b", "A"]


def test_unavailable_detection():
    assert is_unavailable(None)
    assert is_unavailable({"id": None, "uri": "spotify:local:x"})
    assert is_unavailable({"id": "x", "is_playable": False})
    assert not is_unavailable({"id": "x"})
    assert not is_unavailable({"id": "x", "is_playable": True})


def test_rename_template_fields_and_unknowns():
    out = render_name("{name} · {index}/{count}", "Mix", 2, 9)
    assert out == "Mix · 2/9"
    assert render_name("{name} {nope}", "Mix", 1, 1) == "Mix {nope}"
    assert len(render_name("x" * 500, "n", 1, 1)) == 100


def test_month_bounds_including_december():
    s, e = month_bounds(2025, 12)
    assert (s.year, s.month, s.day) == (2025, 12, 1) and (e.year, e.month) == (2026, 1)


def test_mood_presets_are_valid_sonic_filter_params():
    for mood, ranges in MOOD_PRESETS.items():
        SonicFilter.Params(name=mood, **ranges)  # raises on a bad field or range
