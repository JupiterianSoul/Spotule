from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExemptionKind, MatchMode, PurgeTarget


class BannedGenreIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=128)
    match_mode: MatchMode = MatchMode.contains
    apply_skip_guard: bool = True
    apply_library_purge: bool = True
    note: str | None = None


class BannedGenreOut(BannedGenreIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool
    created_at: datetime


class BannedArtistIn(BaseModel):
    artist_id: str
    artist_name: str


class ExemptionIn(BaseModel):
    kind: ExemptionKind
    spotify_id: str
    label: str | None = None


class PurgeRequest(BaseModel):
    target: PurgeTarget
    target_playlist_id: str | None = None
    dry_run: bool = True


class SkipEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    track_name: str | None
    matched_genre: str | None
    matched_rule: str | None
    device_type: str | None
    detected_at: datetime
    latency_ms: int | None
    success: bool


class GuardEventIn(BaseModel):
    """Web Playback SDK bridge: the dashboard tab forwards `player_state_changed`."""

    state: dict
