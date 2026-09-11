from collections import Counter

from app.services.tools.porter import parse_lines
from app.services.tools.shuffler import fisher_yates, spread_artists


def test_fisher_yates_is_permutation():
    src = [f"spotify:track:{i}" for i in range(500)]
    out = fisher_yates(src)
    assert sorted(out) == sorted(src) and out != src


def test_fisher_yates_uniformity_smoke():
    # position of element 0 over many runs should spread across all slots
    hits = Counter(fisher_yates(list(range(5))).index(0) for _ in range(3000))
    assert all(hits[i] > 400 for i in range(5))


def test_spread_artists_avoids_adjacent():
    uris = ["a1", "a2", "b1", "a3", "b2", "c1"]
    artist_of = {u: u[0] for u in uris}
    out = spread_artists(uris, artist_of)
    assert sorted(out) == sorted(uris)
    adjacent = sum(1 for x, y in zip(out, out[1:], strict=False) if artist_of[x] == artist_of[y])
    assert adjacent <= 1


def test_porter_parses_numbered_and_dash_variants():
    text = "1. Daft Punk - One More Time\n2) Justice – D.A.N.C.E.\nnot a track line\nPhoenix — 1901"
    rows = parse_lines(text)
    assert [r["artist"] for r in rows] == ["Daft Punk", "Justice", "Phoenix"]
    assert rows[1]["title"] == "D.A.N.C.E."
