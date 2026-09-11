from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Locale


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    spotify_id: str
    display_name: str | None
    email: str | None
    avatar_url: str | None
    country: str | None
    product: str | None
    role: str


class PreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    locale: Locale
    timezone: str
    skip_guard_enabled: bool
    stream_logger_enabled: bool
    share_stats_with_friends: bool
    share_stats_globally: bool
    settings: dict[str, Any]


class PreferencesUpdate(BaseModel):
    locale: Locale | None = None
    timezone: str | None = Field(None, max_length=64)
    skip_guard_enabled: bool | None = None
    stream_logger_enabled: bool | None = None
    share_stats_with_friends: bool | None = None
    share_stats_globally: bool | None = None
    settings: dict[str, Any] | None = None


class MeOut(BaseModel):
    user: UserOut
    preferences: PreferencesOut
    spotify_linked: bool
    scopes: list[str]
