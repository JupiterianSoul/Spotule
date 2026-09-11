"""Anti-Genre Ban-Hammer: per-user blacklist registry, exemptions, skip & purge audit trails."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExemptionKind, JobStatus, MatchMode, PurgeTarget
from app.models.user import User


class BannedGenre(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A genre rule. `pattern` is matched against each artist genre (lower-cased).
    `contains` mode with pattern "rap" bans "rap", "trap", "cloud rap", "rap francais"…
    """

    __tablename__ = "banned_genres"
    __table_args__ = (UniqueConstraint("user_id", "pattern", "match_mode", name="uq_banned_rule"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pattern: Mapped[str] = mapped_column(String(128))
    match_mode: Mapped[MatchMode] = mapped_column(
        Enum(MatchMode, name="match_mode"), default=MatchMode.contains
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Where the rule applies
    apply_skip_guard: Mapped[bool] = mapped_column(Boolean, default=True)
    apply_library_purge: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="banned_genres")


class BannedArtist(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Explicit artist bans (independent of genre)."""

    __tablename__ = "banned_artists"
    __table_args__ = (UniqueConstraint("user_id", "artist_id", name="uq_banned_artist"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    artist_id: Mapped[str] = mapped_column(String(32))
    artist_name: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BlacklistExemption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Allow-list overrides: 'ban hip hop, but keep this one artist/track'."""

    __tablename__ = "blacklist_exemptions"
    __table_args__ = (UniqueConstraint("user_id", "kind", "spotify_id", name="uq_exemption"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ExemptionKind] = mapped_column(Enum(ExemptionKind, name="exemption_kind"))
    spotify_id: Mapped[str] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(String(512))


class SkipEvent(Base):
    """Audit trail of the real-time skip guard. `latency_ms` = skip cmd sent − track detected."""

    __tablename__ = "skip_events"
    __table_args__ = (Index("ix_skip_events_user_time", "user_id", "detected_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    track_id: Mapped[str | None] = mapped_column(String(32))
    track_name: Mapped[str | None] = mapped_column(String(512))
    artist_id: Mapped[str | None] = mapped_column(String(32))
    matched_rule: Mapped[str | None] = mapped_column(String(128))
    matched_genre: Mapped[str | None] = mapped_column(String(128))
    device_id: Mapped[str | None] = mapped_column(String(64))
    device_type: Mapped[str | None] = mapped_column(String(32))  # Smartphone / Computer…
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)


class PurgeRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of the Library Purger (dry-run or real)."""

    __tablename__ = "purge_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    target: Mapped[PurgeTarget] = mapped_column(Enum(PurgeTarget, name="purge_target"))
    target_playlist_id: Mapped[str | None] = mapped_column(String(32))
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.queued)
    scanned_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    removed_count: Mapped[int] = mapped_column(Integer, default=0)
    backup_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # pre_purge snapshot
    # [{track_id, name, artist, genre, rule}] — what was (or would be) removed
    report: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
