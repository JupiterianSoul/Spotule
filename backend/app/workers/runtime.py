"""Helpers to run async service code inside sync Celery tasks + per-user Spotify clients."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models import SpotifyCredential, User
from app.services.spotify import SpotifyClient
from app.services.spotify.auth import get_valid_access_token

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)


async def user_client(
    db: AsyncSession, user_id: uuid.UUID, priority: bool = False
) -> tuple[User, SpotifyClient] | None:
    user = await db.get(User, user_id)
    cred = await db.get(SpotifyCredential, user_id)
    if user is None or cred is None or cred.revoked_at or not user.is_active:
        return None
    token = await get_valid_access_token(db, cred)
    return user, SpotifyClient(token, priority=priority)


async def with_user(
    user_id: str, fn: Callable[[AsyncSession, User, SpotifyClient], Awaitable[T]], priority: bool = False
) -> T | None:
    async with AsyncSessionLocal() as db:
        pair = await user_client(db, uuid.UUID(user_id), priority)
        if pair is None:
            return None
        user, client = pair
        async with client:
            return await fn(db, user, client)
