"""Central settings. Every value can be overridden via environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SPOTIFY_SCOPES: tuple[str, ...] = (
    # Identity
    "user-read-email",
    "user-read-private",
    # Tracking engine
    "user-read-recently-played",
    "user-top-read",
    # Skip guard (playback)
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-modify-playback-state",
    # Library & playlists (purger, compactor, blender, backups)
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    # Bulk commander (unfollow)
    "user-follow-read",
    "user-follow-modify",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "development"
    api_base_url: str = "http://127.0.0.1:8000"
    web_base_url: str = "http://127.0.0.1:3000"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:3000"])

    # Spotify
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/v1/auth/callback"
    spotify_api_base: str = "https://api.spotify.com/v1"
    spotify_accounts_base: str = "https://accounts.spotify.com"

    # Security
    secret_key: str = "change-me"
    token_encryption_key: str = ""
    session_cookie_name: str = "spotule_session"
    # Shared secret for the scheduler endpoints (/api/v1/cron/*). Empty disables them entirely.
    cron_secret: str = ""
    session_ttl_seconds: int = 60 * 60 * 24 * 30
    cookie_secure: bool = False

    # Stores
    database_url: str = "postgresql+asyncpg://spotule:spotule@localhost:5432/spotule"
    database_url_sync: str = "postgresql+psycopg://spotule:spotule@localhost:5432/spotule"
    # "auto" detects Supabase/PgBouncer style URLs; force with "on" or "off".
    db_pooler_mode: str = "auto"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Workers
    recently_played_poll_seconds: int = 300
    skip_guard_heartbeat_seconds: int = 4
    skip_guard_max_active_users: int = 25
    import_upload_dir: str = "./uploads"
    import_max_upload_mb: int = 512

    # Localization
    default_locale: str = "en"
    supported_locales: tuple[str, ...] = ("en", "fr")

    # Values pasted into a hosting dashboard often arrive with a stray leading or trailing
    # space, which makes SQLAlchemy reject the URL outright with a parse error that names no
    # cause. Whitespace is never meaningful in any of these, so drop it.
    @field_validator(
        "database_url",
        "database_url_sync",
        "redis_url",
        "celery_broker_url",
        "celery_result_backend",
        "spotify_client_id",
        "spotify_client_secret",
        "spotify_redirect_uri",
        "web_base_url",
        "api_base_url",
        "secret_key",
        "token_encryption_key",
        "cron_secret",
        mode="before",
    )
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
