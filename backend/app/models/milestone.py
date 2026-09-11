"""Achievements computed by the analytics worker after each ingest batch."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MilestoneKind


class Milestone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "milestones"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "threshold", "entity_id", name="uq_milestone_once"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[MilestoneKind] = mapped_column(Enum(MilestoneKind, name="milestone_kind"))
    threshold: Mapped[int] = mapped_column(BigInteger)  # 10_000 minutes, 500 plays…
    entity_id: Mapped[str] = mapped_column(String(32), default="")  # artist/track id or ""
    entity_name: Mapped[str | None] = mapped_column(String(512))
    achieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value_at_achievement: Mapped[int] = mapped_column(BigInteger)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
