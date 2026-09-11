"""App-wide Spotify rate limiting.

Spotify enforces a rolling ~30 s window *per application* (not per user), and answers
429 with a `Retry-After` header. Two layers:

1. Token bucket in Redis shared by API + all workers (`spotify:ratelimit:app`), so N users
   polling in parallel cannot collectively exceed the budget.
2. Global back-off: any 429 stores `spotify:retry_after`; every caller checks it first.

Budget defaults are conservative (Development-mode apps get a smaller quota than Extended).
"""

from __future__ import annotations

import asyncio
import time

import redis.asyncio as aioredis

from app.db.redis import Keys, get_redis

# ~ 3 req/s sustained with bursts, well under Spotify's typical dev-mode ceiling.
BUCKET_CAPACITY = 60
REFILL_PER_SECOND = 3.0
_BUCKET_KEY = "spotify:ratelimit:app"

# Atomic token-bucket in Lua (no race between API workers).
_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1]) or capacity
local ts = tonumber(data[2]) or now
tokens = math.min(capacity, tokens + (now - ts) * refill)
local allowed = 0
if tokens >= 1 then tokens = tokens - 1; allowed = 1 end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 120)
return allowed
"""


class SpotifyRateLimiter:
    def __init__(self, r: aioredis.Redis | None = None) -> None:
        self._r = r or get_redis()
        self._script = self._r.register_script(_LUA)

    async def acquire(self, priority: bool = False) -> None:
        """Block until a request slot is available. `priority` (skip guard) bypasses the
        bucket but still honours a global Retry-After."""
        while True:
            retry_after = await self._r.get(Keys.RETRY_AFTER)
            if retry_after and float(retry_after) > time.time():
                await asyncio.sleep(min(float(retry_after) - time.time(), 5.0))
                continue
            if priority:
                return
            allowed = await self._script(
                keys=[_BUCKET_KEY], args=[BUCKET_CAPACITY, REFILL_PER_SECOND, time.time()]
            )
            if int(allowed) == 1:
                return
            await asyncio.sleep(1.0 / REFILL_PER_SECOND)

    async def throttle(self, seconds: float) -> None:
        await self._r.set(Keys.RETRY_AFTER, str(time.time() + seconds), ex=int(seconds) + 5)
