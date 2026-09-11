"""Import every model so `Base.metadata` is complete for Alembic and relationship resolution."""

from app.db.base import Base
from app.models.automation import AutomationJob, ToolRun
from app.models.banhammer import BannedArtist, BannedGenre, BlacklistExemption, PurgeRun, SkipEvent
from app.models.catalog import Album, Artist, ArtistGenre, AudioFeatures, Genre, Track, TrackArtist
from app.models.import_job import ImportJob
from app.models.milestone import Milestone
from app.models.playlist import Playlist, PlaylistBackup, PlaylistTrack, UserPlaylist
from app.models.stream import Stream, StreamHourlyRollup, SyncCursor
from app.models.user import FriendLink, SpotifyCredential, User, UserPreference

__all__ = [
    "Base",
    "User",
    "SpotifyCredential",
    "UserPreference",
    "FriendLink",
    "Genre",
    "Artist",
    "ArtistGenre",
    "Album",
    "Track",
    "TrackArtist",
    "AudioFeatures",
    "Stream",
    "StreamHourlyRollup",
    "SyncCursor",
    "Playlist",
    "UserPlaylist",
    "PlaylistTrack",
    "PlaylistBackup",
    "BannedGenre",
    "BannedArtist",
    "BlacklistExemption",
    "SkipEvent",
    "PurgeRun",
    "AutomationJob",
    "ToolRun",
    "ImportJob",
    "Milestone",
]
