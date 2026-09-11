"""Resolving Spotify's own algorithmic playlists by name.

A scheduled backup passes only a `kind`, so this matcher is what stands between the user
enabling "back up Discover Weekly every Monday" and the job failing every week.
"""

import pytest

from app.models.enums import BackupKind
from app.services.tools.backups import matches_kind, week_label


@pytest.mark.parametrize(
    "name,kind",
    [
        ("Discover Weekly", BackupKind.discover_weekly),
        ("discover weekly", BackupKind.discover_weekly),
        ("  Discover Weekly  ", BackupKind.discover_weekly),
        ("Découvertes de la semaine", BackupKind.discover_weekly),
        ("Release Radar", BackupKind.release_radar),
        ("Radar des sorties", BackupKind.release_radar),
    ],
)
def test_matches_spotify_owned_playlists_in_either_language(name, kind):
    assert matches_kind(name, "spotify", kind) is True


def test_requires_spotify_ownership():
    # A user's own playlist called "Discover Weekly" must never be mistaken for the real one,
    # because the backup would otherwise overwrite the wrong history.
    assert matches_kind("Discover Weekly", "someuser", BackupKind.discover_weekly) is False


def test_does_not_cross_match_kinds():
    assert matches_kind("Release Radar", "spotify", BackupKind.discover_weekly) is False
    assert matches_kind("Discover Weekly", "spotify", BackupKind.release_radar) is False


def test_partial_names_do_not_match():
    assert matches_kind("My Discover Weekly Archive", "spotify", BackupKind.discover_weekly) is False


def test_manual_kind_has_no_auto_resolution():
    assert matches_kind("Anything", "spotify", BackupKind.manual) is False


def test_week_label_format():
    from datetime import UTC, datetime

    assert week_label(datetime(2026, 9, 11, tzinfo=UTC)) == "2026-W37"
    assert week_label(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-W01"
