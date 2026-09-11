# SpotiMax

Enterprise-grade, multi-user **Spotify automation & lifetime analytics dashboard**.
A personal control center (playlist tools, genre ban-hammer, automations) fused with a
Stats.fm-style tracking engine — for you *and* your friends, each with an isolated library.

| Layer | Stack |
|---|---|
| Frontend | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS 4 · next-intl (en / fr) · TanStack Query |
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic v2 |
| Workers | Celery 5 (beat + `realtime` / `default` queues) |
| Data | PostgreSQL 16 (ledger, catalogue, tenancy) · Redis 7 (sessions, rate-limit bucket, hot caches, skip-guard state) |
| Auth | Spotify OAuth 2.0 authorization-code · Fernet-encrypted tokens at rest · HttpOnly opaque sessions |

## Quick start

Create a Spotify app at <https://developer.spotify.com/dashboard> and add this exact Redirect URI:

```
http://127.0.0.1:8000/api/v1/auth/callback
```

Then:

```bash
make setup                      # asks for your client id/secret, generates all other secrets
docker compose up --build       # postgres, redis, api (:8000), worker, beat, web (:3000)
```

Open <http://127.0.0.1:3000/en> (or `/fr`). While the Spotify app is in *Development mode*,
each friend must be added by name + email under **User Management** on the Spotify developer
dashboard (max 25 users) before they can sign in.

### Local development (no Docker)

```bash
# backend
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
alembic upgrade head && uvicorn app.main:app --reload
celery -A app.workers.celery_app:celery_app worker -B -Q realtime,default -l info   # 2nd terminal
# frontend
cd frontend && pnpm install && pnpm dev
```

Tests & lint: `make test` · `make lint`. API docs: <http://127.0.0.1:8000/api/docs>.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — folder structure, request/worker flows, multi-tenancy, rate limiting, i18n
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — every table, why it exists, key indexes
- [`docs/TECHNICAL_PLAN.md`](docs/TECHNICAL_PLAN.md) — step-by-step build plan, milestones, Spotify API caveats
- [`docs/FEATURE_MATRIX.md`](docs/FEATURE_MATRIX.md) — the 100+ micro-features and where each lives in the code

## Repository layout

```
spotimax/
├── backend/            FastAPI app, SQLAlchemy models, Celery workers, Alembic migrations
├── frontend/           Next.js app (app/[locale]/…), messages/{en,fr}.json
├── docs/               Architecture, data model, plan, feature matrix
├── docker-compose.yml  Full local stack
├── Makefile            Common commands
└── .env.example        All configuration knobs
```
