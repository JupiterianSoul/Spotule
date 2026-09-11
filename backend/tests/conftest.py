import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://spotule:spotule@localhost:5432/spotule")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg://spotule:spotule@localhost:5432/spotule")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/9")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest


@pytest.fixture(autouse=True)
async def _dispose_async_engine():
    """pytest-asyncio gives each test its own event loop; pooled asyncpg connections created
    on one loop cannot be reused on the next. Drop the pool after every test."""
    yield
    from app.db.redis import get_redis
    from app.db.session import async_engine

    await async_engine.dispose()
    # The Redis client is lru_cached and its pool is loop-bound too; close and forget it.
    try:
        await get_redis().aclose()
    finally:
        get_redis.cache_clear()
