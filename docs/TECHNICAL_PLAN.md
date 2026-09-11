# SpotiMax — Step-by-step Technical Plan

Scope of this repository right now: the **core skeleton is implemented and verified** —
models + migration (28 tables), OAuth/session layer, rate-limited Spotify client, ingest
pipeline (poller + ZIP importer), analytics queries, ban-hammer engine, tool registry with 11
tools, Celery workers/beat, bilingual UI shell with 7 pages. What follows is the plan to take
it to production, phase by phase, with acceptance criteria.

---

## Phase 0 — Environment & Spotify app (½ day)

1. Create the Spotify app; add redirect URI `http://127.0.0.1:8000/api/v1/auth/callback`
   (and the production one). Note: since 2025 Spotify requires `127.0.0.1`, not `localhost`.
2. `cp .env.example .env`; generate `SECRET_KEY` and `TOKEN_ENCRYPTION_KEY`.
3. `docker compose up --build` → `/healthz` OK, `/api/docs` lists all routers.
4. Add friends' Spotify emails under *User Management* (Development mode = 25 users).
   Apply for **Extended Quota Mode** early — the review takes weeks and lifts the user cap and
   several endpoint restrictions (see §Caveats).

**Done when**: you and one friend can sign in from a phone and a PC and see distinct
`/api/v1/me` payloads.

## Phase 1 — Tracking engine: live logger (2 days)

1. Enable the beat schedule (`ingest.recently_played.fanout`, default 5 min). Tune
   `RECENTLY_PLAYED_POLL_SECONDS` for heavy listeners (50 tracks ≈ 2.5 h of music, so 5 min is
   very safe).
2. Verify `sync_cursors.cursor` advances and `uq_stream_dedupe` swallows overlaps.
3. `catalog.hydrate` fills artist genres; confirm `artists.fetched_at` is non-null for everything
   you've played.
4. Add the Web Playback SDK bridge in the dashboard tab (optional `web_sdk` stream source and
   zero-latency guard path).

**Done when**: 24 h of listening on Android + desktop appears in `streams` with no gaps
(compare against the Spotify app's "Recently played").

## Phase 2 — Tracking engine: lifetime importer (2 days)

1. Request "Extended streaming history" from Spotify (takes up to 30 days to arrive).
2. Upload via `/imports`; watch `import_jobs` counters. Importer is streaming (`ijson`) and
   batch-inserts 5 000 rows at a time; a 2 M-row export runs in a few minutes.
3. `catalog.hydrate` back-fills `tracks` 50 at a time from `spotify_track_uri`, then
   `relink_imported_streams` attaches `track_id`. Budget: 1 M rows ≈ 60 k unique tracks ≈
   1 200 calls ≈ 7 min at 3 req/s.
4. Rebuild hourly rollups for the imported range (call `refresh_hourly_rollups(since=earliest)`
   at the end of the import task).
5. Handle the overlap window between import and poller: the importer's timestamps mark the END
   of a play; the poller's mark the START. Add the ±90 s fuzzy dedupe pass described in
   `models/stream.py` (SQL: delete api_poll rows whose (track_uri, played_at ± duration) match an
   imported row).

**Done when**: lifetime minutes on the dashboard match the yearly totals in Spotify Wrapped ±2 %.

## Phase 3 — Deep metric dashboards (3 days)

1. Wire the remaining widgets: album grid, genre treemap (recharts), streak counter, "first
   listened" timeline, per-artist drill-down page (`/stats/artist/[id]`).
2. Materialise `top_*` for `lifetime` into a nightly `user_top_cache` table if p95 > 300 ms on
   tenants with > 5 M rows (query plan today: index-only scan on `ix_streams_user_played` + hash
   joins; fine to ~5 M rows).
3. Milestones: extend `THRESHOLDS`, add `listening_streak_days`, push a toast on new rows
   (`milestones.notified = false`).
4. Friends: `friend_links` accept/decline endpoints + UI; leaderboard already respects share flags.

**Done when**: every widget renders in en and fr within 500 ms cached / 2 s cold on a
mid-range Android phone (Lighthouse mobile ≥ 90).

## Phase 4 — Ban-Hammer (3 days)

1. **Registry UI** is live; add artist search (Spotify `/search`) for `banned_artists` and
   exemptions, and a "preview matches in my library" button that runs a dry-run purge.
2. **Purger**: extend to `all_owned_playlists`; add a restore button that calls `backup.restore`
   with the `purge_runs.backup_id`.
3. **Skip guard**: enable, then measure `skip_events.latency_ms`. Expect 150–300 ms on the
   skip command; detection latency is bounded by the adaptive poll (≈250 ms at track
   transitions, ≤ `SKIP_GUARD_HEARTBEAT_SECONDS` for manual skips into a banned track).
   Tune heartbeat per user (2–4 s) against the rate budget: N users × (1/heartbeat) req/s must
   stay under the bucket (default 3 req/s ⇒ ~10 concurrent guarded users at 4 s; raise the
   budget once in Extended Quota).
4. Add the **Web Playback SDK** listener in the dashboard tab → `POST /banhammer/guard/event`
   for sub-100 ms detection when the user listens in the browser.
5. Optional: genre inference for artists Spotify leaves genre-less (~30 % of long tail) via
   MusicBrainz tags or a small classifier over audio features; store as `genres` with a
   `source` column (migration 0002).

**Done when**: playing a banned-genre track on the phone is skipped before the vocals start,
and `skip_events` shows `success=true` with latency < 500 ms.

## Phase 5 — Tools & automations (ongoing, ~1 day per 5 micro-features)

The registry makes each feature a single file. Priority order:

1. Backups: wire `automation_jobs` for Discover Weekly (Mon 06:00) / Release Radar (Fri 06:00);
   discover the playlist IDs by scanning the user's followed playlists for
   `owner.id == "spotify"` and names matching localised titles.
2. Bulk commander UI: multi-select playlist table with search, then `bulk.*` tools.
3. Blender/Splitter/Shuffler are complete; add drag-to-order for blend sources.
4. Sonic filters: add ReccoBeats env toggle + CSV importer for `audio_features`.
5. Audio Porter: URL scrapers (Apple Music JSON-LD, YouTube Music via `ytmusicapi`) feeding the
   existing matcher; ISRC-first matching when the source exposes it.
6. Fill the remaining rows of `docs/FEATURE_MATRIX.md`.

## Phase 6 — Hardening & deployment (2 days)

1. Production compose / Fly.io / Railway: API + 2 workers (one pinned to `realtime`) + beat;
   managed Postgres + Redis; `COOKIE_SECURE=true`, HTTPS, `CORS_ORIGINS` = web origin.
2. Alembic in CI (`alembic upgrade head` against a throwaway DB), pytest, ruff, `pnpm typecheck`,
   `pnpm lint`, `pnpm build`.
3. Observability: structlog JSON → Loki/Datadog; Celery Flower; Sentry on both apps.
4. Backups: nightly `pg_dump`; `playlist_backups` is already the user-facing undo.
5. GDPR: `DELETE /me` cascades; add a data export (`streams` → CSV) endpoint.

---

## Spotify Web API caveats you must design around (as of 2025–2026)

| Constraint | Impact | Mitigation in SpotiMax |
|---|---|---|
| **Development mode: 25 users, name+email allow-list** | Friends must be added manually | Apply for Extended Quota; UI copy explains it |
| **No playback webhooks** | "Instant" skip = polling | Adaptive poll + Web SDK bridge (`skip_guard.py`) |
| **`/me/player/next` needs Premium** | Free accounts can't be guarded | `product` check; UI disables toggle |
| **`/me/player/recently-played`: last 50, >30 s plays only** | Short plays and >50/interval lost | ≤5 min polling + ZIP importer for the past |
| **Nov 27 2024: `/audio-features`, `/audio-analysis`, `/recommendations`, `/related-artists` return 403 for new apps** | Sonic filters can't use Spotify | `AudioFeatureProvider` chain (ReccoBeats, CSV import) |
| **Nov 27 2024: Spotify-owned algorithmic/editorial playlists (Discover Weekly, Release Radar…) not readable by new dev-mode apps** | Backups by API may 403/404 | `backup.playlist` falls back to *shadow capture* from the user's own stream `context_uri` |
| **Per-app rolling 30 s rate limit; 429 + Retry-After** | Multi-user fan-out can throttle everyone | Redis token bucket + global back-off + batching + genre cache |
| **Playlist items use `/playlists/{id}/items` (`/tracks` deprecated)** | Old snippets break | Client already uses `/items` |
| **Redirect URIs must use `127.0.0.1` (not `localhost`) and HTTPS in prod** | OAuth fails silently | `.env.example` uses `127.0.0.1` |

## Testing strategy

* Unit: pure modules (`banhammer/registry.py`, shuffler, porter parser, importer normaliser,
  i18n) — implemented, 19 tests green.
* Integration: API smoke against Postgres+Redis (implemented); add fixtures that seed 10 k
  streams and assert analytics numbers.
* Contract: record Spotify responses with `respx` and replay them in `SpotifyClient` tests
  (rate-limit 429 path, pagination, `fields=` masks).
* E2E: Playwright against `docker compose` — sign in with a test account, toggle language,
  ban a genre, run a dry-run purge.
