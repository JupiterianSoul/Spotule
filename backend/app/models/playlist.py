"""Playlists mirrored from Spotify + Spotule-managed snapshots/backups."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BackupKind


class Playlist(TimestampMixin, Base):
    __tablename__ = "playlists"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # Spotify playlist id
    spotify_owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    public: Mapped[bool | None] = mapped_column(Boolean)
    collaborative: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(128))
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str | None] = mapped_column(Text)
    # True when Spotule created it (backup volume, blend output, split part, sonic filter…)
    managed_by_spotule: Mapped[bool] = mapped_column(Boolean, default=False)
    managed_kind: Mapped[str | None] = mapped_column(String(32))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tracks: Mapped[list[PlaylistTrack]] = relationship(
        back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistTrack.position"
    )


class UserPlaylist(Base):
    """Which of *our* users owns/follows which playlist (tenant edge)."""

    __tablename__ = "user_playlists"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    playlist_id: Mapped[str] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (Index("ix_playlist_tracks_track", "track_id"),)

    playlist_id: Mapped[str] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[str | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"))
    track_uri: Mapped[str] = mapped_column(String(64))  # keeps local files representable
    added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_by: Mapped[str | None] = mapped_column(String(64))

    playlist: Mapped[Playlist] = relationship(back_populates="tracks")


class PlaylistBackup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable snapshot of a playlist's ordered track URIs. Cheap (a few KB) so we take one
    automatically before every destructive tool run — this is the undo button."""

    __tablename__ = "playlist_backups"
    __table_args__ = (Index("ix_playlist_backups_user_kind", "user_id", "kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[BackupKind] = mapped_column(Enum(BackupKind, name="backup_kind"))
    source_playlist_id: Mapped[str | None] = mapped_column(String(32))
    source_name: Mapped[str] = mapped_column(String(512))
    week_label: Mapped[str | None] = mapped_column(String(16))  # e.g. "2026-W37"
    track_uris: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    track_count: Mapped[int] = mapped_column(Integer)
    # If the backup was also materialised as a real Spotify playlist
    materialized_playlist_id: Mapped[str | None] = mapped_column(String(32))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
