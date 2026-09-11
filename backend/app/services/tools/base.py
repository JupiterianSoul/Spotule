"""Tool registry — the extension point for the 100+ micro-features.

A tool is a small class with metadata + an async `run`. Registering it:
  • exposes it at GET /api/v1/tools (the UI builds its catalogue from this),
  • lets POST /api/v1/tools/{key}/run enqueue it as a Celery task with a ToolRun audit row,
  • gives it a free pre-run playlist backup when `destructive=True`.

Adding a micro-feature = one file in services/tools/ + two strings in each locale file.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.spotify import SpotifyClient


@dataclass
class ToolContext:
    db: AsyncSession
    client: SpotifyClient
    user: User
    run_id: str
    report_progress: Any = field(default=lambda pct, msg=None: None)


class ToolSpec(BaseModel):
    key: str
    pillar: str  # "playlists" | "library" | "bulk" | "sonic" | "porter" | "backup"
    destructive: bool = False
    needs_premium: bool = False
    async_run: bool = True  # enqueue to Celery vs run inline (< 2 s)
    params_schema: dict[str, Any] = {}


class Tool(abc.ABC):
    key: ClassVar[str]
    pillar: ClassVar[str]
    destructive: ClassVar[bool] = False
    needs_premium: ClassVar[bool] = False
    async_run: ClassVar[bool] = True
    Params: ClassVar[type[BaseModel]] = BaseModel

    @classmethod
    def spec(cls) -> ToolSpec:
        return ToolSpec(
            key=cls.key,
            pillar=cls.pillar,
            destructive=cls.destructive,
            needs_premium=cls.needs_premium,
            async_run=cls.async_run,
            params_schema=cls.Params.model_json_schema(),
        )

    @abc.abstractmethod
    async def run(self, ctx: ToolContext, params: BaseModel) -> dict[str, Any]: ...

    async def backup_targets(self, params: BaseModel) -> list[str]:
        """Playlist ids to snapshot before running (destructive tools override)."""
        return []


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, type[Tool]] = {}

    def register(self, tool_cls: type[Tool]) -> type[Tool]:
        if tool_cls.key in self._tools:
            raise ValueError(f"duplicate tool key {tool_cls.key}")
        self._tools[tool_cls.key] = tool_cls
        return tool_cls

    def get(self, key: str) -> type[Tool]:
        return self._tools[key]

    def specs(self) -> list[ToolSpec]:
        return [t.spec() for t in sorted(self._tools.values(), key=lambda t: (t.pillar, t.key))]

    def __contains__(self, key: str) -> bool:
        return key in self._tools


registry = ToolRegistry()
