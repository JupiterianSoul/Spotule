"""Shared enums (persisted as native Postgres ENUM types)."""

from enum import StrEnum


class Locale(StrEnum):
    en = "en"
    fr = "fr"


class UserRole(StrEnum):
    member = "member"
    admin = "admin"


class StreamSource(StrEnum):
    api_poll = "api_poll"  # /me/player/recently-played background worker
    json_import = "json_import"  # official "Extended streaming history" ZIP
    web_sdk = "web_sdk"  # Web Playback SDK events from the dashboard tab
    skip_guard = "skip_guard"  # observed by the skip-guard poller (partial plays)


class MatchMode(StrEnum):
    exact = "exact"
    contains = "contains"
    regex = "regex"


class ExemptionKind(StrEnum):
    artist = "artist"
    track = "track"
    album = "album"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class PurgeTarget(StrEnum):
    liked_songs = "liked_songs"
    playlist = "playlist"
    all_owned_playlists = "all_owned_playlists"


class BackupKind(StrEnum):
    discover_weekly = "discover_weekly"
    release_radar = "release_radar"
    daily_mix = "daily_mix"
    manual = "manual"
    pre_purge = "pre_purge"  # safety snapshot taken before a destructive tool runs
    pre_bulk = "pre_bulk"


class AutomationKind(StrEnum):
    backup_discover_weekly = "backup_discover_weekly"
    backup_release_radar = "backup_release_radar"
    weekly_report = "weekly_report"
    liked_songs_snapshot = "liked_songs_snapshot"
    auto_purge = "auto_purge"
    playlist_archive_monthly = "playlist_archive_monthly"
    sync_playlists = "sync_playlists"


class MilestoneKind(StrEnum):
    total_minutes = "total_minutes"
    total_streams = "total_streams"
    artist_streams = "artist_streams"
    track_streams = "track_streams"
    album_streams = "album_streams"
    unique_artists = "unique_artists"
    unique_tracks = "unique_tracks"
    listening_streak_days = "listening_streak_days"


class AudioFeatureSource(StrEnum):
    spotify = "spotify"
    reccobeats = "reccobeats"
    acousticbrainz = "acousticbrainz"
    user_import = "user_import"


class SyncKind(StrEnum):
    recently_played = "recently_played"
    liked_songs = "liked_songs"
    playlists = "playlists"
    followed_artists = "followed_artists"
    top_items = "top_items"


class FriendStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    blocked = "blocked"
