from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

TimeframePreset = Literal["4w", "6m", "1y", "lifetime", "custom"]


class Timeframe(BaseModel):
    preset: TimeframePreset = "4w"
    start: datetime | None = None
    end: datetime | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int | None = None
    limit: int
    offset: int


class OK(BaseModel):
    ok: bool = True
    message: str | None = None


class JobRef(BaseModel):
    run_id: str
    status: str
    tool_key: str | None = None
    progress: int = 0
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
