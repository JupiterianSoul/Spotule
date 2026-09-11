"""Scheduled automations (backups, reports…) and generic tool-run audit."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AutomationKind, JobStatus


class AutomationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's recurring automation definition (Celery beat reads enabled rows)."""

    __tablename__ = "automation_jobs"
    __table_args__ = (Index("ix_automation_jobs_user_kind", "user_id", "kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[AutomationKind] = mapped_column(Enum(AutomationKind, name="automation_kind"))
    cron: Mapped[str] = mapped_column(String(64), default="0 6 * * 1")  # Monday 06:00 UTC
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audit + progress row for any tool execution (shuffler, blender, bulk delete, porter…)
    and for automation firings. Every tool writes one; the UI polls it for progress."""

    __tablename__ = "tool_runs"
    __table_args__ = (Index("ix_tool_runs_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    automation_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_jobs.id", ondelete="SET NULL")
    )
    tool_key: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "playlist.true_shuffle"
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", create_type=False), default=JobStatus.queued
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    backup_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
