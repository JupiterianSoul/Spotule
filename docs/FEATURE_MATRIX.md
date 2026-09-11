# Spotule — Feature Matrix (100+ micro-features)

Status legend: ✅ implemented and covered by tests or a live check · 🧩 scaffolded (model/registry/route exists, logic to fill) · 📝 planned (one file in `services/tools/` + 2 locale strings)

Rows marked 🧩 or 📝 are not working features. The honest summary is in
[`docs/STATUS.md`](STATUS.md), which lists what is finished, what is half-built, and what is
untested because it needs real Spotify credentials.

Every tool row lives in `backend/app/services/tools/` and is exposed automatically through
`GET /api/v1/tools` → Tools page. Every stats row is a query in `services/analytics/`.

## Pillar 1 — Architecture, multi-tenancy, L10N

| # | Feature | Where | Status |
|---|---|---|---|
| 1 | Spotify OAuth2 sign-in (authorization code, server-side state) | `api/v1/auth.py`, `services/spotify/auth.py` | ✅ |
| 2 | Per-user encrypted token storage (Fernet) | `core/security.py`, `models/user.py` | ✅ |
| 3 | Transparent token refresh | `services/spotify/auth.py::get_valid_access_token` | ✅ |
| 4 | Opaque HttpOnly sessions in Redis | `api/deps.py`, `db/redis.py` | ✅ |
| 5 | Tenant isolation (`user_id` on every table, cascade delete) | `models/*` | ✅ |
| 6 | GDPR delete account | `DELETE /api/v1/me` | ✅ |
| 7 | en/fr UI catalogue with ICU plurals, typed keys | `frontend/messages`, `global.d.ts` | ✅ |
| 8 | `/[locale]/` routing + Accept-Language detection | `src/proxy.ts`, `i18n/routing.ts` | ✅ |
| 9 | Locale switcher that persists to server | `LocaleSwitcher.tsx`, `PATCH /me/preferences` | ✅ |
| 10 | Localised API errors & tool catalogue | `core/i18n.py`, `locales/*.json` | ✅ |
| 11 | Locale-aware numbers & dates | `useFormatter`, `i18n/request.ts` formats | ✅ |
| 12 | Spotify dark theme tokens (Tailwind v4 `@theme`) | `globals.css` | ✅ |
| 13 | Responsive shell: sidebar (≥ md) + bottom tab bar (mobile, safe-area) | `Sidebar.tsx`, `MobileNav.tsx` | ✅ |
| 14 | Installable PWA manifest | `public/manifest.webmanifest` | ✅ |
| 15 | Timezone preference | `user_preferences.timezone`, Settings page | ✅ |
| 16 | Role-based admin (user cap, quota view) | `models/user.py::UserRole`, `deps.require_admin` | 🧩 |
| 17 | Structured JSON logging | `core/logging.py` | ✅ |
| 18 | Docker compose full stack | `docker-compose.yml` | ✅ |
| 19 | Alembic migrations (autogen, up/down verified) | `alembic/` | ✅ |
| 20 | CI-ready checks (pytest, ruff, tsc, eslint, next build) | `Makefile`, `pyproject.toml` | ✅ |

## Pillar 2 — Stats.fm-style tracking engine

| # | Feature | Where | Status |
|---|---|---|---|
| 21 | Background lifetime stream logger (cursor-based, dedupe) | `services/ingest/recently_played.py`, `workers/tasks/ingest.py` | ✅ |
| 22 | Per-user logger on/off | `user_preferences.stream_logger_enabled` | ✅ |
| 23 | Extended streaming history ZIP importer (streaming, millions of rows) | `services/ingest/json_importer.py` | ✅ |
| 24 | Account-data (1-year) JSON format support | same, `_normalise` | ✅ |
| 25 | Import progress UI + counters | `/imports` page, `import_jobs` | ✅ |
| 26 | Catalogue hydration & relinking of imported rows | `services/catalog.py`, `catalog.hydrate` task | ✅ |
| 27 | Shared catalogue cache (tracks/artists/albums/genres) | `models/catalog.py` | ✅ |
| 28 | Overview tiles (minutes, streams, unique tracks/artists, skips) | `analytics/top.py::overview` | ✅ |
| 29 | Top tracks (custom timeframes) | `analytics/top.py` | ✅ |
| 30 | Top artists | `analytics/top.py` | ✅ |
| 31 | Top albums | `analytics/top.py` | ✅ |
| 32 | Top genres (weighted per artist) | `analytics/top.py::top_genres` | ✅ |
| 33 | Timeframes 4w / 6m / 1y / lifetime / custom dates | `analytics/timeframes.py`, `TimeframePicker` | ✅ |
| 34 | Listening clock 7×24 heatmap (user timezone) | `analytics/clock.py`, `ListeningClock.tsx` | ✅ |
| 35 | Peak hour / peak weekday | `analytics/clock.py` | ✅ |
| 36 | Hourly rollups for O(1) clocks | `models/stream.py::StreamHourlyRollup` | ✅ |
| 37 | Milestones: total minutes / streams thresholds | `analytics/milestones.py` | ✅ |
| 38 | Milestones: artist ×N, unique artists/tracks | `analytics/milestones.py` | ✅ |
| 39 | New-milestone badge on the dashboard, cleared once seen | `POST /stats/milestones/seen`, dashboard chip | ✅ |
| 40 | Listening streak (consecutive days) | `MilestoneKind.listening_streak_days` | 🧩 |
| 41 | Friends leaderboard query (opt-in) | `analytics/leaderboard.py` | ✅ |
| 42 | Global leaderboard (opt-in) | same | ✅ |
| 43 | Friend requests: search by name or Spotify username, send, accept, decline, remove; crossed requests auto-accept | `api/v1/friends.py`, `/friends` page | ✅ |
| 44 | Stats cache (Redis, 10 min) | `api/v1/stats.py::_cached` | ✅ |
| 45 | "Where I listen from" (context: playlist/album/radio) | `streams.context_uri` | 🧩 |
| 46 | Platform split (android/ios/desktop/web) | `streams.platform` | 🧩 |
| 47 | Skip rate & reason_end analysis | `streams.skipped/reason_end` | 🧩 |
| 48 | Shuffle vs deliberate plays | `streams.shuffle` | 🧩 |
| 49 | Offline listening share | `streams.offline` | 🧩 |
| 50 | Country-of-listening map | `streams.country` | 🧩 |
| 51 | Artist drill-down page (first listen, trend, top tracks) | `/stats/artist/[id]` | 📝 |
| 52 | Track drill-down | `/stats/track/[id]` | 📝 |
| 53 | Year-in-review / "Wrapped any day" | analytics composition | 📝 |
| 54 | Discovery rate (new artists per month) | analytics query | 📝 |
| 55 | Decade / release-year distribution | `albums.release_date` | 📝 |
| 56 | Explicit-content share | `tracks.explicit` | 📝 |
| 57 | Popularity profile (mainstream score) | `tracks.popularity` | 📝 |
| 58 | Stream export to CSV | `/me/export` | 📝 |
| 59 | Web Playback SDK live logging (`web_sdk` source) | `StreamSource.web_sdk` | 🧩 |
| 60 | Compare two friends head-to-head | leaderboard variant | 📝 |

## Pillar 3 — Anti-genre Ban-Hammer

| # | Feature | Where | Status |
|---|---|---|---|
| 61 | Global blacklist registry (contains / exact / regex) | `models/banhammer.py`, `/ban-hammer` page | ✅ |
| 62 | Per-rule scope flags (skip guard / purge) | `banned_genres.apply_*` | ✅ |
| 63 | Artist bans | `banned_artists`, `POST /banhammer/artists` | ✅ |
| 64 | Exemptions (artist / album / track) | `blacklist_exemptions` | ✅ |
| 65 | Pure, unit-tested evaluator | `services/banhammer/registry.py` | ✅ |
| 66 | Library purger — dry run with report | `services/banhammer/purger.py` | ✅ |
| 67 | Library purger — Liked Songs removal | same | ✅ |
| 68 | Library purger — single playlist | same | ✅ |
| 69 | Library purger — all owned playlists | `PurgeTarget.all_owned_playlists` | 🧩 |
| 70 | Automatic pre-purge backup (undo) | `PlaylistBackup(kind=pre_purge)` | ✅ |
| 71 | Real-time skip guard (adaptive poll, < 500 ms skip) | `services/banhammer/skip_guard.py` | ✅ |
| 72 | Self-rescheduling guard ticks on `realtime` queue | `workers/tasks/banhammer.py` | ✅ |
| 73 | Guard roster (enabled ∧ premium, capped) | same | ✅ |
| 74 | Skip audit trail with latency | `skip_events`, UI list | ✅ |
| 75 | Web Playback SDK bridge (zero-latency path) | `POST /banhammer/guard/event` | ✅ (endpoint) / 📝 (client SDK) |
| 76 | Premium gating | `product == "premium"` checks | ✅ |
| 77 | Redis genre cache (no Spotify on hot path) | `services/catalog.py::artist_genres_cached` | ✅ |
| 78 | Scheduled auto-purge | `AutomationKind.auto_purge` | 🧩 |
| 79 | Genre inference for genre-less artists (MusicBrainz / model) | migration 0002 | 📝 |
| 80 | "Preview matches in my library" before banning | dry-run purge reuse | 📝 |
| 81 | Ban by keyword in track title | new `MatchMode`/kind | 📝 |
| 82 | Quiet hours / device allow-list for the guard | `preferences.settings` | 📝 |

## Pillar 4 — Playlist compactor, utilities, automations

| # | Feature | Tool key | Status |
|---|---|---|---|
| 83 | True Shuffler (Fisher–Yates, CSPRNG) | `playlist.true_shuffle` | ✅ |
| 84 | Artist-spread post-pass | same, `avoid_adjacent_artists` | ✅ |
| 85 | Shuffle to a new playlist (non-destructive) | same, `write_to_new_playlist` | ✅ |
| 86 | Blender — merge up to 10, interleave/append, dedupe | `playlist.blend` | ✅ |
| 87 | Splitter — slice into volumes | `playlist.split` | ✅ |
| 88 | Bulk delete playlists (with backup) | `bulk.delete_playlists` | ✅ |
| 89 | Bulk unfollow artists | `bulk.unfollow_artists` | ✅ |
| 90 | Batch description templating | `bulk.update_descriptions` | ✅ |
| 91 | Deduplicator (ISRC-aware) | `bulk.dedupe_playlist` | ✅ |
| 92 | Smart Sonic Filter (BPM/energy/valence/acousticness/danceability) | `sonic.filter` | ✅ |
| 93 | Audio feature provider chain (Spotify → ReccoBeats → import) | `sonic_filter.py` | ✅ |
| 94 | Playlist backup (any playlist, weekly label, materialise) | `backup.playlist` | ✅ |
| 94b | Liked Songs snapshot | `backup.liked_songs` | ✅ |
| 94c | Resolve Discover Weekly / Release Radar by name, in either language, so a schedule needs no playlist id | `backups.py::resolve_playlist_id` | ✅ |
| 95 | Shadow capture fallback for Discover Weekly / Release Radar | same | ✅ |
| 96 | Restore backup (in place or new) | `backup.restore` | ✅ |
| 97 | Automatic pre-run backups for destructive tools | `workers/tasks/tools.py` | ✅ |
| 98 | Audio Porter — "Artist - Title" text → playlist | `porter.text_to_playlist` | ✅ |
| 99 | Weekly Discover Weekly automation | `AutomationKind.backup_discover_weekly` | ✅ |
| 100 | Weekly Release Radar automation | `AutomationKind.backup_release_radar` | ✅ |
| 101 | Liked Songs snapshot automation | `AutomationKind.liked_songs_snapshot` | ✅ |
| 102 | Per-user cron scheduler | `workers/tasks/automations.py` | ✅ |
| 103 | Tool run audit + progress polling | `tool_runs`, `/tools/runs` | ✅ |
| 104 | JSON-schema-driven tool forms | `features/tools/ToolRunner.tsx` | ✅ |
| 105 | Audio Porter — Apple Music URL scraper | `porter.apple_url` | 📝 |
| 106 | Audio Porter — YouTube Music URL | `porter.ytmusic_url` | 📝 |
| 107 | Bulk make public/private | `bulk.set_visibility` | ✅ |
| 108 | Bulk rename with template ({name} {index} {count} {date}) | `bulk.rename` | ✅ |
| 109 | Bulk cover art upload | `bulk.cover_art` | 📝 |
| 110 | Sort playlist by date added, name, artist, album, duration, release year, popularity | `playlist.sort` | ✅ |
| 111 | Reverse playlist | `playlist.reverse` | ✅ |
| 112 | Remove unavailable/greyed-out tracks | `playlist.prune_unavailable` | ✅ |
| 113 | Remove tracks already in Liked Songs | `playlist.subtract_liked` | ✅ |
| 114 | Playlist set operations (A − B, A ∩ B, A ∪ B) | `playlist.set_ops` | ✅ |
| 115 | Copy playlist (fork) | `playlist.copy` | ✅ |
| 116 | Liked Songs → playlist mirror (newest or oldest first, updates in place) | `library.liked_to_playlist` | ✅ |
| 117 | Monthly "Best of" from stream ledger | `library.monthly_best_of` | ✅ |
| 118 | "Forgotten favourites" (≥N plays, silent for M months) | `library.forgotten` | ✅ |
| 119 | Compactor: cap playlist to N, archive overflow | `playlist.compact` | 📝 |
| 120 | Weekly listening report e-mail (localised) | `AutomationKind.weekly_report` | 📝 |
| 121 | Mood playlists (happy, sad, focus, party, chill, workout) | `sonic.mood_preset` | ✅ |
| 122 | Tempo ladder for running (BPM ramp) | `sonic.bpm_ladder` | 📝 |
| 123 | Snapshot diff viewer (what changed in Discover Weekly) | `playlist_backups` | 📝 |
| 124 | Export playlist rows (uri, name, artists, album, duration, added, ISRC) | `playlist.export` | ✅ |
| 125 | Import CSV/M3U → playlist | `porter.csv` | 📝 |
