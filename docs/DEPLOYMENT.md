# Spotule — Deployment

## Why GitHub Pages cannot host Spotule

GitHub Pages serves **static files only**. It has no server process, no database, no scheduler
and no way to keep a secret. Spotule needs all four:

| Spotule needs | GitHub Pages offers |
|---|---|
| A server to exchange the OAuth code for tokens using `SPOTIFY_CLIENT_SECRET` | Nothing server-side. The secret would have to ship in the JavaScript bundle, where anyone can read it and impersonate the app. |
| PostgreSQL for the lifetime stream ledger | No database |
| Redis for sessions, the rate-limit bucket and skip-guard state | No key-value store |
| A Celery worker running 24/7 so the stream logger keeps recording while nobody has the site open | No background processes |
| A scheduler for weekly backups and the skip guard | No cron |

The tracking engine is the part that suffers most: it only works because a worker polls Spotify
every few minutes *whether or not you are looking at the page*. A static host cannot do that, so
you would be back to a 50-track history, which is the exact limitation the app exists to beat.

There is a second, subtler reason. Putting the frontend on `username.github.io` and the API
somewhere else makes the session cookie **cross-site**. Safari blocks those outright and Chrome
restricts them, so login would fail for a lot of people with no visible error. Spotule avoids
this by serving the API and the UI from one origin (see below).

## Topology

Everything the browser touches is one hostname. The Next.js server proxies `/api/*` to FastAPI
over the internal network (`frontend/next.config.mjs` → `rewrites()`), so the cookie is
first-party, `SameSite=Lax` works everywhere, and there is no CORS at all.

```
                    https://spotule.example.com
                              │
                         ┌────▼────┐   TLS, automatic Let's Encrypt certificate
                         │  Caddy  │
                         └────┬────┘
                              │ :3000
                         ┌────▼────┐   pages + /api/* proxy
                         │   web   │   (Next.js)
                         └────┬────┘
                              │ http://api:8000   ← internal only, never public
                         ┌────▼────┐
                         │   api   │   (FastAPI)
                         └────┬────┘
             ┌────────────────┼────────────────┐
        ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
        │ postgres│      │  redis  │      │ worker  │  + beat (scheduler)
        └─────────┘      └─────────┘      └─────────┘
```

## Option A — one small VPS (recommended)

The app is already fully containerised, so this is the shortest path to a real URL and the
cheapest way to get an always-on worker. A 2 GB machine is plenty (Hetzner CX22, DigitalOcean,
Vultr, OVH: roughly €4–6 per month).

1. Point a DNS `A` record at the server's IP, e.g. `spotule.example.com`.
2. Install Docker, then clone the repo onto the server.
3. In the **Spotify dashboard**, add the production Redirect URI alongside the local one:
   `https://spotule.example.com/api/v1/auth/callback`
4. On the server:

```bash
make setup                                  # generates .env with fresh secrets
echo "DOMAIN=spotule.example.com" >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy requests the TLS certificate on first boot. Give it about a minute, then open the domain.

The overlay (`docker-compose.prod.yml`) publishes only ports 80 and 443. Postgres, Redis and the
API are on the internal network and cannot be reached from the internet. It also sets
`COOKIE_SECURE=true`, `APP_ENV=production` and the production redirect URI, and marks every
service `restart: unless-stopped` so the stream logger comes back after a reboot.

Useful commands:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres \
  pg_dump -U spotule spotule | gzip > backup-$(date +%F).sql.gz
```

## Option B — a managed platform (Render, Railway, Fly.io)

Workable, but read this first: **the background worker must never sleep.** Free tiers on these
platforms suspend services after a period of inactivity, and a suspended worker means the
recently-played poller stops and you silently lose listening history. Anything Spotule tracks
while asleep is gone for good, because Spotify only keeps the last 50 plays.

So budget for a paid always-on instance for the worker, whatever else you do. Realistically that
lands in the same €5–15 per month range as a VPS, for more moving parts.

If you go this route, you need five services from this one repository:

| Service | Type | Command / image | Notes |
|---|---|---|---|
| `api` | Web | `backend/Dockerfile` | Health check path `/healthz`. Keep it private if the platform allows. |
| `web` | Web | `frontend/Dockerfile` | Set `API_INTERNAL_URL` to the api service's address and leave `NEXT_PUBLIC_API_BASE_URL` empty. This is the public one. |
| `worker` | Background worker | `celery -A app.workers.celery_app:celery_app worker -Q realtime,default -l info` | Must be always-on. |
| `beat` | Background worker | `celery -A app.workers.celery_app:celery_app beat -l info` | Exactly one instance, ever. |
| `postgres` + `redis` | Managed add-ons | — | Free Postgres tiers are usually time-limited; check the current terms before relying on one. |

Set `WEB_BASE_URL`, `API_BASE_URL` and `SPOTIFY_REDIRECT_URI` to the public web hostname, and
`COOKIE_SECURE=true`. Run `alembic upgrade head` once after the first deploy.

Splitting the frontend onto Vercel and the backend elsewhere is possible but brings back the
cross-site cookie problem described above, so you would have to move the session to a token in
`localStorage` and accept the security trade-off. Not recommended.

## Production checklist

- [ ] Production Redirect URI registered on the Spotify app, matching `SPOTIFY_REDIRECT_URI` exactly
- [ ] `SECRET_KEY` and `TOKEN_ENCRYPTION_KEY` generated by `make setup`, never committed
- [ ] `TOKEN_ENCRYPTION_KEY` backed up somewhere safe — lose it and every stored Spotify token becomes undecryptable and all users must re-link
- [ ] `COOKIE_SECURE=true` and the site served over HTTPS
- [ ] `alembic upgrade head` applied
- [ ] Worker and beat both running, and beat running exactly once
- [ ] A nightly `pg_dump` going somewhere off the machine
