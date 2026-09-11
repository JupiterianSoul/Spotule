# SpotiMax — Architecture

## 1. Project folder structure

```
spotimax/
├── .env.example                      # every config knob, documented
├── docker-compose.yml                # postgres · redis · api · worker · beat · web
├── Makefile
├── docs/                             # this folder
│
├── backend/
│   ├── pyproject.toml                # deps, ruff, pytest
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py                    # reads settings.database_url_sync, imports app.models
│   │   └── versions/0001_initial_schema.py
│   ├── app/
│   │   ├── main.py                   # FastAPI factory, CORS, lifespan (Redis ping)
│   │   ├── core/
│   │   │   ├── config.py             # pydantic-settings + SPOTIFY_SCOPES
│   │   │   ├── security.py           # Fernet token encryption, opaque session ids
│   │   │   ├── i18n.py               # backend catalogue (API errors, worker text), Accept-Language negotiation
│   │   │   └── logging.py            # structlog JSON
│   │   ├── db/
│   │   │   ├── base.py               # DeclarativeBase, naming conventions, mixins
│   │   │   ├── session.py            # async engine (API) + sync engine (workers/alembic)
│   │   │   └── redis.py              # key namespaces
│   │   ├── models/                   # ── SQLAlchemy 2.0 typed models ──
│   │   │   ├── enums.py
│   │   │   ├── user.py               # users, spotify_credentials, user_preferences, friend_links
│   │   │   ├── catalog.py            # artists, albums, tracks, genres, audio_features (shared cache)
│   │   │   ├── stream.py             # streams (ledger), stream_hourly_rollups, sync_cursors
│   │   │   ├── playlist.py           # playlists, user_playlists, playlist_tracks, playlist_backups
│   │   │   ├── banhammer.py          # banned_genres, banned_artists, blacklist_exemptions, skip_events, purge_runs
│   │   │   ├── automation.py         # automation_jobs, tool_runs
│   │   │   ├── import_job.py         # import_jobs
│   │   │   └── milestone.py          # milestones
│   │   ├── schemas/                  # Pydantic request/response DTOs
│   │   ├── api/
│   │   │   ├── deps.py               # CurrentUser, Locale, Spotify client deps
│   │   │   ├── router.py             # /api/v1 aggregator
│   │   │   └── v1/
│   │   │       ├── auth.py           # /auth/login · /auth/callback · /auth/logout
│   │   │       ├── me.py             # /me · /me/preferences · DELETE /me (GDPR)
│   │   │       ├── stats.py          # /stats/overview · /top/{kind} · /clock · /milestones · /leaderboard
│   │   │       ├── banhammer.py      # /banhammer/genres · /purge · /guard/toggle · /guard/event · /guard/events
│   │   │       ├── playlists.py      # /playlists · /playlists/backups
│   │   │       ├── imports.py        # POST /imports (ZIP) · GET /imports/{id}
│   │   │       ├── tools.py          # GET /tools (catalogue) · POST /tools/{key}/run · GET /tools/runs/{id}
│   │   │       └── automations.py    # CRUD on recurring jobs
│   │   ├── services/                 # ── pure business logic, no HTTP ──
│   │   │   ├── spotify/
│   │   │   │   ├── client.py         # typed, paginated, retrying Web API client
│   │   │   │   ├── auth.py           # OAuth code exchange + transparent refresh
│   │   │   │   └── rate_limiter.py   # Redis Lua token bucket shared by API + workers
│   │   │   ├── catalog.py            # upsert tracks/artists/albums/genres, Redis genre cache
│   │   │   ├── ingest/
│   │   │   │   ├── recently_played.py# cursor-based incremental logger + hourly rollups
│   │   │   │   └── json_importer.py  # streaming ZIP → streams (ijson, 5k-row batches)
│   │   │   ├── analytics/
│   │   │   │   ├── timeframes.py     # 4w / 6m / 1y / lifetime / custom
│   │   │   │   ├── top.py            # top tracks/artists/albums/genres + overview
│   │   │   │   ├── clock.py          # 7×24 heatmap in user's timezone
│   │   │   │   ├── milestones.py     # threshold detection
│   │   │   │   └── leaderboard.py    # friends / global opt-in comparison
│   │   │   ├── banhammer/
│   │   │   │   ├── registry.py       # Blacklist / Rule / Verdict (pure, unit-tested)
│   │   │   │   ├── skip_guard.py     # adaptive poll tick + skip command
│   │   │   │   └── purger.py         # scan/remove with pre-purge backup
│   │   │   └── tools/                # ── extension point for the 100+ micro-features ──
│   │   │       ├── base.py           # Tool ABC + ToolRegistry
│   │   │       ├── shuffler.py       # playlist.true_shuffle
│   │   │       ├── blender.py        # playlist.blend · playlist.split
│   │   │       ├── bulk.py           # bulk.delete_playlists · unfollow_artists · update_descriptions · dedupe_playlist
│   │   │       ├── sonic_filter.py   # sonic.filter + AudioFeatureProvider chain
│   │   │       ├── backups.py        # backup.playlist · backup.restore
│   │   │       └── porter.py         # porter.text_to_playlist
│   │   ├── workers/
│   │   │   ├── celery_app.py         # queues: realtime, default
│   │   │   ├── schedules.py          # beat schedule
│   │   │   ├── runtime.py            # run_async, per-user client factory
│   │   │   └── tasks/
│   │   │       ├── ingest.py         # recently_played fan-out, catalog.hydrate, milestones
│   │   │       ├── banhammer.py      # guard roster + self-rescheduling ticks, purge
│   │   │       ├── imports.py        # ZIP import
│   │   │       ├── tools.py          # generic tool executor (backup → run → audit)
│   │   │       └── automations.py    # cron evaluation → tool runs
│   │   └── locales/{en,fr}.json      # backend strings
│   └── tests/                        # registry, tools, importer, i18n, API smoke
│
└── frontend/
    ├── package.json · next.config.mjs · tsconfig.json · postcss.config.mjs · eslint.config.mjs
    ├── Dockerfile                    # multi-stage, standalone output
    ├── messages/{en,fr}.json         # UI catalogue (190 keys, parity-checked)
    ├── public/manifest.webmanifest   # installable on Android
    └── src/
        ├── proxy.ts                  # next-intl locale middleware (Next 16 name)
        ├── global.d.ts               # typed message keys
        ├── i18n/{routing,request,navigation}.ts
        ├── app/
        │   ├── globals.css           # Tailwind v4 @theme — Spotify dark tokens
        │   ├── layout.tsx · page.tsx # pass-through + "/" → "/en"
        │   └── [locale]/
        │       ├── layout.tsx        # <html lang> · NextIntlClientProvider · QueryProvider
        │       ├── page.tsx          # landing / sign-in
        │       └── (dashboard)/
        │           ├── layout.tsx    # Sidebar (md+) · MobileNav (bottom tabs) · AuthGate
        │           ├── dashboard/ · stats/ · ban-hammer/ · tools/ · imports/ · automations/ · settings/
        ├── components/
        │   ├── layout/               # Sidebar, MobileNav, TopBar, LocaleSwitcher, AuthGate
        │   ├── ui/                   # Page, Toggle, Skeleton
        │   └── widgets/              # StatTile, TopList, ListeningClock, MilestoneList, TimeframePicker
        ├── features/tools/ToolRunner.tsx   # JSON-schema-driven form for any registered tool
        └── lib/                      # api.ts (fetch wrapper), hooks.ts, types.ts, utils.ts
```

## 2. Multi-tenancy & security

* **Tenant root = `users.id` (UUID).** Every user-owned table carries `user_id` with
  `ON DELETE CASCADE`; every service function and API query is scoped by the authenticated user.
  `DELETE /api/v1/me` erases a tenant completely (GDPR).
* **Tokens never leave the server.** `spotify_credentials` stores Fernet-encrypted access and
  refresh tokens (`TOKEN_ENCRYPTION_KEY`); the browser only ever holds an opaque session id.
* **Sessions**: `session:<id> → user_id` in Redis, delivered as `HttpOnly; SameSite=Lax`
  cookie; 30-day sliding TTL. No JWT to leak or to forge.
* **OAuth**: authorization-code flow with server-side `state` in Redis (10 min TTL).
  Scopes are the minimum for all pillars (see `core/config.py`).
* **Shared catalogue is not tenant data** (`artists`, `tracks`, `genres`, `audio_features`) —
  a Spotify track is the same for everyone; sharing it slashes API calls.
* **Friends & leaderboards** only read from users whose `user_preferences.share_*` flags are on.

## 3. Request & worker flows

```
Browser (Next.js, /fr/dashboard)
   │  fetch(credentials: include, Accept-Language: fr)
   ▼
FastAPI ── deps.get_current_user ── Redis session ── Postgres user
   │
   ├─ /stats/* ─────────── analytics.* ── Postgres (streams ⋈ catalogue) ── Redis cache 10 min
   ├─ /banhammer/purge ─── PurgeRun row ── Celery(default) ── purger ── Spotify API
   ├─ /tools/{key}/run ─── ToolRun row ─── Celery(default) ── ToolRegistry ── Spotify API
   └─ /imports ─────────── ImportJob row ─ Celery(default) ── ijson ZIP stream ── COPY-sized inserts

Celery beat
   ├─ every RECENTLY_PLAYED_POLL_SECONDS: ingest.recently_played.fanout → 1 task / user
   ├─ every 30 s: guard.refresh_roster → starts/stops self-rescheduling guard.tick per user (realtime queue)
   ├─ every 2 min: catalog.hydrate (artist genres, imported-track metadata, relink)
   ├─ every 15 min: analytics.milestones.fanout
   └─ every minute: automations.tick (per-user cron → tool runs)
```

## 4. Spotify rate-limit strategy

Spotify enforces a rolling ~30 s window **per application**. SpotiMax therefore:

1. Uses one **Redis token bucket** (`SpotifyRateLimiter`, Lua for atomicity) shared by the API
   process and every worker — 60 burst / 3 req·s⁻¹ sustained by default.
2. Honours `429 Retry-After` globally: every caller pauses until the stored deadline.
3. Batches everything: `/tracks` ×50, `/artists` ×50, playlist mutations ×100, and reads
   playlist items with a `fields=` mask.
4. Caches artist → genres in Redis for 7 days so the skip guard **never** calls Spotify on
   the hot path.
5. Polls `recently-played` with the `after` cursor (only new items, ≤ 1 call / user / interval).
6. Skip-guard ticks are `priority=True`: they bypass the bucket but still respect Retry-After,
   and the roster is capped by `SKIP_GUARD_MAX_ACTIVE_USERS`.

## 5. Real-time skip guard (why 500 ms is achievable)

Spotify offers no playback webhooks. Detection is an **adaptive poll**: every tick reads
`/me/player`; the next tick is scheduled at `min(heartbeat, time_left_on_track + 250 ms)`, so
the poll that catches a track *transition* lands ~250 ms into the new track. Genres are read
from Redis (<5 ms) and `POST /me/player/next` takes ≈150–300 ms ⇒ skip issued well under
500 ms after observation. When the dashboard tab is open, the Web Playback SDK bridge posts
`player_state_changed` to `/banhammer/guard/event` for near-zero-latency detection. Requires
Premium (Spotify's rule for playback control).

## 6. Localization (en / fr)

* **Frontend**: `next-intl` v4 with `/[locale]/…` routing (`localePrefix: "always"`), messages
  in `frontend/messages/{en,fr}.json` (190 keys each, parity checked), ICU plurals
  (`{count, plural, …}`), locale-aware numbers/dates via `useFormatter`. `global.d.ts` makes
  `t("nav.dashboard")` type-checked — a missing key fails the build.
* **Locale switch**: `LocaleSwitcher` rewrites the URL segment and, when signed in,
  `PATCH /me/preferences {locale}` so the backend (emails, milestone titles, backup names)
  follows the user.
* **Backend**: `core/i18n.py` negotiates `?lang=` → user preference → `Accept-Language`;
  `t("errors.session_expired", "fr")` for API errors; tool titles/descriptions are served
  localised from `GET /tools` so the UI catalogue needs no per-tool frontend strings.

## 7. Extending: adding a micro-feature

1. Create `backend/app/services/tools/<name>.py`, subclass `Tool`, declare `key`, `pillar`,
   `destructive`, a Pydantic `Params`, implement `run(ctx, params)`.
2. Import it in `services/tools/__init__.py`.
3. Add `tools.<key>.title/description` to `backend/app/locales/{en,fr}.json`.
4. Done — it appears in `GET /tools`, the UI's Tools page renders a form from its JSON schema,
   `POST /tools/<key>/run` enqueues it, destructive tools get an automatic backup, and every
   run is audited in `tool_runs`.
