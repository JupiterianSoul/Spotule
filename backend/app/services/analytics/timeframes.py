"""Custom timeframes shared by every stats endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

Preset = Literal["4w", "6m", "1y", "lifetime", "custom"]


def resolve(
    preset: Preset, start: datetime | None = None, end: datetime | None = None
) -> tuple[datetime | None, datetime]:
    now = datetime.now(UTC)
    if preset == "4w":
        return now - timedelta(weeks=4), now
    if preset == "6m":
        return now - timedelta(days=182), now
    if preset == "1y":
        return now - timedelta(days=365), now
    if preset == "custom":
        if start is None:
            raise ValueError("custom timeframe requires start")
        return start, end or now
    return None, now  # lifetime
