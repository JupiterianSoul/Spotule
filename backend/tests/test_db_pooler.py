"""Detection of pooled (PgBouncer-style) database URLs.

Getting this wrong is a production-only failure: asyncpg's prepared statements break under
transaction pooling with intermittent errors that never appear against a direct connection.
"""

import pytest

from app.db.session import looks_pooled

SUPABASE_POOLER = "postgresql+asyncpg://postgres.abcdef:pw@aws-0-eu-west-3.pooler.supabase.com:6543/postgres"
SUPABASE_DIRECT = "postgresql+asyncpg://postgres:pw@db.abcdef.supabase.co:5432/postgres"
NEON_POOLER = "postgresql+asyncpg://u:pw@ep-cool-name-123-pooler.eu-central-1.aws.neon.tech/db"
LOCAL = "postgresql+asyncpg://spotule:spotule@localhost:5432/spotule"


@pytest.mark.parametrize("url", [SUPABASE_POOLER, NEON_POOLER, "postgres://x:y@host:6543/db"])
def test_detects_pooled_urls(url):
    assert looks_pooled(url) is True


@pytest.mark.parametrize("url", [SUPABASE_DIRECT, LOCAL])
def test_leaves_direct_connections_alone(url):
    assert looks_pooled(url) is False


def test_mode_overrides_detection():
    assert looks_pooled(LOCAL, "on") is True
    assert looks_pooled(SUPABASE_POOLER, "off") is False
    assert looks_pooled(SUPABASE_POOLER, "auto") is True


def test_alembic_accepts_percent_encoded_passwords():
    """Regression: alembic writes the URL into a configparser ini, where "%" begins an
    interpolation token. A percent-encoded password aborted every migration on deploy."""
    from alembic.config import Config

    url = "postgresql+psycopg://u:Galp%21Sll2sp%21@h.pooler.supabase.com:5432/postgres"
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    # configparser unescapes on read, so the engine still receives the original string.
    assert cfg.get_main_option("sqlalchemy.url") == url


def test_settings_strip_whitespace_from_pasted_values(monkeypatch):
    """A stray space from a dashboard paste made SQLAlchemy reject the URL with a parse
    error naming no cause."""
    from app.core.config import Settings

    monkeypatch.setenv("DATABASE_URL_SYNC", "  postgresql+psycopg://u:p@h:5432/db\n")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", " secret ")
    s = Settings()
    assert s.database_url_sync == "postgresql+psycopg://u:p@h:5432/db"
    assert s.spotify_client_secret == "secret"
