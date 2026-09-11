"""Tenancy root. Every user-owned row carries `user_id` and every query is scoped by it."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import FriendStatus, Locale, UserRole

if TYPE_CHECKING:
    from app.models.banhammer import BannedGenre


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    spotify_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    product: Mapped[str | None] = mapped_column(String(32))  # premium / free (skip needs premium)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.member)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    credentials: Mapped[SpotifyCredential | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    preferences: Mapped[UserPreference | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    banned_genres: Mapped[list[BannedGenre]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SpotifyCredential(TimestampMixin, Base):
    """Encrypted OAuth tokens — one row per user, never exposed through the API."""

    __tablename__ = "spotify_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text)  # space-separated granted scopes
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="credentials")


class UserPreference(TimestampMixin, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[Locale] = mapped_column(Enum(Locale, name="locale"), default=Locale.en)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    skip_guard_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    stream_logger_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    share_stats_with_friends: Mapped[bool] = mapped_column(Boolean, default=True)
    share_stats_globally: Mapped[bool] = mapped_column(Boolean, default=False)
    # Free-form: dashboard widget order, chart colour mode, notification toggles, etc.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    user: Mapped[User] = relationship(back_populates="preferences")


class FriendLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Opt-in comparison graph for the 'Global Stats' pillar."""

    __tablename__ = "friend_links"
    __table_args__ = (UniqueConstraint("user_id", "friend_user_id", name="uq_friend_pair"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    friend_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[FriendStatus] = mapped_column(
        Enum(FriendStatus, name="friend_status"), default=FriendStatus.pending
    )
