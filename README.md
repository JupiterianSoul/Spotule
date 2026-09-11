# Spotule

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

Open <http://127.0.0.1:3000/en> (or `/fr`).

### Who can sign in

Spotule itself has no allow-list, no invite codes and no user cap: anyone who completes the
Spotify OAuth flow gets an account and their own isolated library. The limit comes from Spotify,
and every third-party Spotify app lives under it.

| Spotify app mode | Who can log in | How you get there |
|---|---|---|
| **Development** (every new app starts here) | Up to 25 people, each added by name + email under **User Management** in the Spotify dashboard | Automatic |
| **Extended Quota** | Anyone with a Spotify account, no allow-list | Apply from the dashboard; Spotify reviews it, and approval is not guaranteed |

So "log in and you're in" is exactly what the code does. Until Spotify approves an Extended Quota
request, their gate keeps it to 25 named people. Nothing on this side can change that.

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

## Deploying to a real domain

Spotule cannot run on GitHub Pages: it needs a server for the OAuth secret, Postgres, Redis and
a worker running 24/7 so listening history keeps recording while the site is closed. The shortest
path to a public URL is a small VPS:

```bash
make setup && echo "DOMAIN=spotule.example.com" >> .env
make deploy     # Caddy fetches a TLS certificate automatically
```

Everything is served from one origin, which keeps the session cookie first-party and working in
every browser. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full topology, managed-platform
alternatives and the production checklist.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — folder structure, request/worker flows, multi-tenancy, rate limiting, i18n
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — every table, why it exists, key indexes
- [`docs/TECHNICAL_PLAN.md`](docs/TECHNICAL_PLAN.md) — step-by-step build plan, milestones, Spotify API caveats
- [`docs/FEATURE_MATRIX.md`](docs/FEATURE_MATRIX.md) — the 100+ micro-features and where each lives in the code
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — putting Spotule on a public domain

## Repository layout

```
spotule/
├── backend/            FastAPI app, SQLAlchemy models, Celery workers, Alembic migrations
├── frontend/           Next.js app (app/[locale]/…), messages/{en,fr}.json
├── docs/               Architecture, data model, plan, feature matrix
├── infra/              Caddyfile (TLS reverse proxy)
├── docker-compose.yml  Full local stack
├── docker-compose.prod.yml  Production overlay (TLS, no exposed internals)
├── Makefile            Common commands
└── .env.example        All configuration knobs
```
