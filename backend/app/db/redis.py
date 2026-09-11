"""Redis: sessions, OAuth state, Spotify rate-limit buckets, hot caches, skip-guard state.

Key namespaces (all prefixed so a single Redis can be shared safely):
  session:<sid>                 → user_id                      (TTL = session ttl)
  oauth:state:<state>           → locale|redirect              (TTL 10 min)
  spotify:ratelimit:<bucket>    → token bucket counters
  spotify:retry_after           → epoch until which the app is throttled (429 Retry-After)
  cache:artist:<id>             → JSON artist (genres) (TTL 7d)
  cache:stats:<user>:<hash>     → JSON computed stats (TTL 10 min)
  guard:<user>:current          → last observed track id + progress (skip guard)
  guard:active                  → set of user ids with guard enabled & recent playback
"""

from __future__ import annotations

from functools import lru_cache

import redis
import redis.asyncio as aioredis

from app.core.config import settings


@lru_cache
def get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@lru_cache
def get_sync_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


class Keys:
    @staticmethod
    def session(sid: str) -> str:
        return f"session:{sid}"

    @staticmethod
    def oauth_state(state: str) -> str:
        return f"oauth:state:{state}"

    @staticmethod
    def artist(artist_id: str) -> str:
        return f"cache:artist:{artist_id}"

    @staticmethod
    def stats(user_id: str, digest: str) -> str:
        return f"cache:stats:{user_id}:{digest}"

    @staticmethod
    def guard_current(user_id: str) -> str:
        return f"guard:{user_id}:current"

    GUARD_ACTIVE = "guard:active"
    RETRY_AFTER = "spotify:retry_after"
