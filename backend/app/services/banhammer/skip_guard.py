"""Real-time skip guard.

Spotify has NO push/webhook for playback, so "instant" detection is a tight, adaptive poll:

  ┌ every heartbeat (default 4 s, tunable per user) ─────────────────────────────┐
  │ GET /me/player  ──► new track id? ──► genres from Redis (never Spotify)     │
  │                                        └► banned? ──► POST /me/player/next  │
  │ schedule next poll = min(heartbeat, time_left_on_track + 250 ms)            │
  └──────────────────────────────────────────────────────────────────────────────┘

Latency budget once a banned track is *observed*: Redis lookup (<5 ms) + skip request
(≈150-300 ms RTT) ⇒ well within 500 ms. Detection latency is bounded by the heartbeat; the
end-of-track prediction makes the *transition* poll land ~250 ms after the new track starts,
which is the common case. When the dashboard tab is open, the Web Playback SDK bridge
(`POST /api/v1/banhammer/guard/event`) reports state changes with ~0 latency instead.

Skip requires Spotify Premium (`user.product == "premium"`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.redis import Keys, get_redis
from app.models import SkipEvent
from app.services.banhammer.registry import Blacklist
from app.services.catalog import artist_genres_cached, upsert_artists
from app.services.spotify import SpotifyClient


@dataclass
class GuardTick:
    next_poll_seconds: float
    skipped: bool = False
    track_id: str | None = None


async def guard_tick(
    db: AsyncSession, client: SpotifyClient, user_id, blacklist: Blacklist, state: dict | None = None
) -> GuardTick:
    """One evaluation. `state` can be injected by the Web SDK bridge to avoid a GET."""
    r = get_redis()
    heartbeat = float(settings.skip_guard_heartbeat_seconds)
    detected_at = datetime.now(UTC)
    if state is None:
        state = await client.player_state()
    if not state or not state.get("is_playing") or not (state.get("item") or {}).get("id"):
        return GuardTick(next_poll_seconds=heartbeat * 3)  # idle → back off

    item = state["item"]
    track_id = item["id"]
    progress = int(state.get("progress_ms") or 0)
    duration = int(item.get("duration_ms") or 0)
    time_left = max(0.25, (duration - progress) / 1000 + 0.25) if duration else heartbeat
    next_poll = min(heartbeat, time_left)

    prev = await r.get(Keys.guard_current(user_id))
    if prev and json.loads(prev).get("track_id") == track_id:
        return GuardTick(next_poll_seconds=next_poll, track_id=track_id)
    await r.set(
        Keys.guard_current(user_id),
        json.dumps({"track_id": track_id, "at": detected_at.isoformat()}),
        ex=3600,
    )

    artist_ids = [a["id"] for a in item.get("artists", []) if a.get("id")]
    genres = await artist_genres_cached(artist_ids)
    missing = [a for a in artist_ids if a not in genres]
    if missing:  # cold cache — one priority fetch, then cached for 7 days
        await upsert_artists(db, await client.artists(missing))
        genres.update(await artist_genres_cached(missing))

    verdict = blacklist.evaluate(track_id, (item.get("album") or {}).get("id"), genres)
    if not verdict.banned:
        return GuardTick(next_poll_seconds=next_poll, track_id=track_id)

    device = state.get("device") or {}
    event = SkipEvent(
        user_id=user_id,
        track_id=track_id,
        track_name=item.get("name"),
        artist_id=verdict.artist_id,
        matched_rule=verdict.rule,
        matched_genre=verdict.genre,
        device_id=device.get("id"),
        device_type=device.get("type"),
        detected_at=detected_at,
    )
    try:
        await client.skip_next(device.get("id"))
        event.skipped_at = datetime.now(UTC)
        event.latency_ms = int((event.skipped_at - detected_at).total_seconds() * 1000)
        event.success = True
    except Exception as exc:  # noqa: BLE001
        event.error = str(exc)[:500]
    db.add(event)
    await db.commit()
    # After a skip the next track starts immediately: poll again fast.
    return GuardTick(next_poll_seconds=0.75, skipped=event.success, track_id=track_id)
