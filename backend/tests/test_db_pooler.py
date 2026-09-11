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
