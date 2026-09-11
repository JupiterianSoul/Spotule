"""The lifetime stream ledger — append-only, per user.

Two ingestion paths write here:
  1. `api_poll`   — background worker fetching /me/player/recently-played (max 50 items,
                    only plays > 30s). Runs every N minutes per user, cursor-based.
  2. `json_import`— the official "Extended streaming history" ZIP (millions of rows with
                    ms_played, platform, reason_start/end, shuffle, skipped...).

Dedupe: `(user_id, played_at, spotify_track_uri)` is unique. The importer additionally
runs a ±90 s fuzzy check against api_poll rows because the two sources disagree slightly
on timestamps (the JSON export timestamps the END of the play; the API the START).

Denormalised name columns keep imported rows queryable even before the catalogue row is
hydrated (podcast episodes, removed tracks, local files have no Spotify track id).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.catalog import Track
from app.models.enums import StreamSource, SyncKind


class Stream(Base):
    __tablename__ = "streams"
    __table_args__ = (
        UniqueConstraint("user_id", "played_at", "spotify_track_uri", name="uq_stream_dedupe"),
        Index("ix_streams_user_played", "user_id", "played_at"),
        Index("ix_streams_user_track", "user_id", "track_id"),
        Index("ix_streams_user_source", "user_id", "source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[str | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    spotify_track_uri: Mapped[str | None] = mapped_column(String(64))
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ms_played: Mapped[int | None] = mapped_column(Integer)  # null for api_poll (unknown)
    source: Mapped[StreamSource] = mapped_column(Enum(StreamSource, name="stream_source"), nullable=False)

    # Denormalised for imports / podcasts / deleted content
    track_name: Mapped[str | None] = mapped_column(String(512))
    artist_name: Mapped[str | None] = mapped_column(String(512))
    album_name: Mapped[str | None] = mapped_column(String(512))

    # Context (playlist / album / artist radio) — powers "where do I listen from"
    context_uri: Mapped[str | None] = mapped_column(String(128))
    context_type: Mapped[str | None] = mapped_column(String(32))

    # Extended-history-only signals
    platform: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(2))
    reason_start: Mapped[str | None] = mapped_column(String(32))
    reason_end: Mapped[str | None] = mapped_column(String(32))
    shuffle: Mapped[bool | None] = mapped_column(Boolean)
    skipped: Mapped[bool | None] = mapped_column(Boolean)
    offline: Mapped[bool | None] = mapped_column(Boolean)
    incognito: Mapped[bool | None] = mapped_column(Boolean)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    track: Mapped[Track | None] = relationship(lazy="selectin")


class StreamHourlyRollup(Base):
    """Pre-aggregated listening clock buckets (per user, per UTC hour). Rebuilt incrementally
    by the ingest worker; the API converts to the user's timezone at read time."""

    __tablename__ = "stream_hourly_rollups"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    streams: Mapped[int] = mapped_column(Integer, default=0)
    ms_played: Mapped[int] = mapped_column(BigInteger, default=0)
    unique_tracks: Mapped[int] = mapped_column(Integer, default=0)


class SyncCursor(Base):
    """Per-user, per-kind incremental sync state so workers never refetch what they have."""

    __tablename__ = "sync_cursors"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[SyncKind] = mapped_column(Enum(SyncKind, name="sync_kind"), primary_key=True)
    cursor: Mapped[str | None] = mapped_column(Text)  # e.g. `after` ms timestamp
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_errors: Mapped[int] = mapped_column(SmallInteger, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
