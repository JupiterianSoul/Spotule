"""Async engine for the API, sync engine for Celery workers and Alembic.

Hosted Postgres (Supabase, Neon, and anything else fronted by PgBouncer) needs care with
asyncpg. In transaction pooling mode a connection is handed to a different client between
statements, so server-side prepared statements either vanish or collide by name. The symptoms
are intermittent `InvalidSQLStatementNameError` or `DuplicatePreparedStatementError` under
load, which is a miserable thing to debug in production.

`_pooler_connect_args` disables the prepared-statement cache and gives every statement a
unique name when the URL looks like a pooled endpoint. Detection can be forced either way with
`DB_POOLER_MODE` (`auto` by default, or `on` / `off`).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

# Hostname fragments and ports used by the common managed poolers.
POOLER_HINTS = ("pooler.supabase.com", "pgbouncer", "-pooler.", ":6543")


def looks_pooled(url: str, mode: str = "auto") -> bool:
    """True when the database URL points at a transaction pooler."""
    if mode == "on":
        return True
    if mode == "off":
        return False
    lowered = url.lower()
    return any(hint in lowered for hint in POOLER_HINTS)


def _pooler_connect_args() -> dict[str, Any]:
    return {
        # asyncpg: never cache prepared statements, the pooler may move us to another backend.
        "statement_cache_size": 0,
        # Unique names stop two clients sharing a backend from colliding.
        "prepared_statement_name_func": lambda: f"__sp_{uuid.uuid4().hex}",
    }


def build_async_engine():
    pooled = looks_pooled(settings.database_url, settings.db_pooler_mode)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if pooled:
        # The external pooler already multiplexes; a second pool on top adds idle
        # connections that count against a free tier's small connection budget.
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = _pooler_connect_args()
    else:
        kwargs["pool_size"] = 10
    return create_async_engine(settings.database_url, **kwargs)


def build_sync_engine():
    # psycopg (used by Alembic and the Celery workers) is unaffected by the prepared-statement
    # problem, but still should not hold a pool open behind an external pooler.
    pooled = looks_pooled(settings.database_url_sync, settings.db_pooler_mode)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if pooled:
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = 5
    return create_engine(settings.database_url_sync, **kwargs)


async_engine = build_async_engine()
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

sync_engine = build_sync_engine()
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False, class_=Session)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
