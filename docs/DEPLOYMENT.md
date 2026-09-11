# Spotule — Deployment

## The one constraint that decides everything

Spotule's background work splits in two, and only the second half is expensive to host.

| | What it does | What it needs |
|---|---|---|
| **Periodic** | Logs new plays from `/me/player/recently-played`, hydrates the catalogue, awards milestones, fires weekly backups | A nudge every few minutes. Any scheduler can send it. |
| **Continuous** | The real-time skip guard: watches playback every few seconds and skips banned genres | A process that never sleeps |

The periodic half is what builds your lifetime history, and it is the reason the app exists.
It used to require a Celery worker, which is a paid instance type nearly everywhere. It no
longer does: every periodic job is exposed at `POST /api/v1/cron/run`, so a free external
scheduler can drive the whole tracking engine. `.github/workflows/scheduler.yml` does exactly
that using GitHub Actions, which is free.

The skip guard is the only feature that genuinely needs an always-on process. On a free host
you lose it and keep everything else.

## Answers to the obvious questions

**Render** — yes, this works, and `render.yaml` in the repo is a starting blueprint. Two free
web services (api and web), no worker, periodic jobs driven by the GitHub Actions scheduler.
Caveats: free web services sleep when idle, so a visit after a quiet spell takes a minute to
load, and free instance-hours are a shared monthly budget, so let the web service sleep and
point the scheduler at the API service directly. Treat Render's own free Postgres as temporary
and use Supabase or Neon instead.

**Supabase** — yes, as the database, which is exactly what it is good at. Its free Postgres does
not expire, and Spotule talks plain Postgres so it needs no Supabase-specific code. Use the
connection string as `DATABASE_URL` / `DATABASE_URL_SYNC`. It is not an app host, so it does not
replace Render. Note free projects pause after about a week of no queries; the five-minute
scheduler sweep keeps yours awake.

**Cloudflare** — not for the backend. Workers run JavaScript and WebAssembly, and Spotule's API
is Python with SQLAlchemy, asyncpg and Celery. Porting it to Workers means rewriting the entire
backend, and D1 is SQLite rather than Postgres. Cloudflare is still worth using for the free
things it is excellent at: DNS, TLS and CDN in front of whatever hosts the app, and Cron
Triggers as a free alternative to the GitHub Actions scheduler.

**GitHub Pages** — no, and not fixable. It serves static files only: no server to hold
`SPOTIFY_CLIENT_SECRET` during the token exchange, no database, no scheduler. Putting the UI
there and the API elsewhere would also make the session cookie cross-site, which Safari blocks
outright, so login would fail for some people with no visible error.

## Free option A — Oracle Cloud Always Free (recommended, keeps every feature)

Oracle's Always Free tier includes a VM that does not expire and does not sleep, which is
enough to run the entire stack exactly as `docker compose` defines it, skip guard included.
It is the only free option that loses no functionality. Account signup asks for a card to verify
identity; Always Free resources are not charged. Capacity for the ARM instance shape can be hard
to get in busy regions, so try a different region if the console refuses.

1. Create the VM (Ampere ARM, Ubuntu), and open ports 80 and 443 in the security list.
2. Get a free hostname from [DuckDNS](https://duckdns.org) pointing at the VM's IP, e.g.
   `spotule.duckdns.org`. HTTPS is mandatory because Spotify rejects plain-HTTP redirect URIs.
3. Register `https://spotule.duckdns.org/api/v1/auth/callback` in the Spotify dashboard.
4. Install Docker, clone the repo, then:

```bash
make setup                                   # generates .env with fresh secrets
echo "DOMAIN=spotule.duckdns.org" >> .env
make deploy                                  # Caddy fetches a TLS certificate automatically
```

Caddy gets the certificate on first boot. Everything is served from one origin, so the session
cookie stays first-party. Postgres, Redis and the API are on the internal Docker network and are
not reachable from the internet.

Any other VM works identically: Google Cloud's always-free `e2-micro`, a spare Raspberry Pi at
home behind a tunnel, or a €4/month VPS if you would rather not fight Oracle's capacity limits.

## Free option B — Render + Supabase + Upstash + GitHub Actions

No VM, no card, but you lose the skip guard and accept cold starts.
**A full click-by-click walkthrough lives in [HOSTED_SETUP.md](HOSTED_SETUP.md);** the summary
below is the shape of it.

1. **Postgres**: create a free Supabase (or Neon) project. Copy the connection string twice:
   - `DATABASE_URL` → change the scheme to `postgresql+asyncpg://`
   - `DATABASE_URL_SYNC` → change the scheme to `postgresql+psycopg://`
2. **Redis**: create a free Upstash database and copy its `rediss://` URL into `REDIS_URL`.
3. **App**: point Render at this repo. The blueprint creates `spotule-api` and `spotule-web` and
   prompts for the secrets. Generate `TOKEN_ENCRYPTION_KEY` yourself and keep a copy:

   ```bash
   python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
   python -c "import secrets;print(secrets.token_urlsafe(32))"   # CRON_SECRET
   ```

4. After the first deploy, set `API_INTERNAL_URL` on `spotule-web` to the API's public URL, and
   set `WEB_BASE_URL`, `API_BASE_URL` and `SPOTIFY_REDIRECT_URI` on `spotule-api` to the web
   service's public URL (the redirect URI gets `/api/v1/auth/callback` appended). Register that
   same redirect URI in the Spotify dashboard.
5. **Scheduler**: add two repository secrets under Settings → Secrets and variables → Actions:
   `SPOTULE_URL` (the API service's URL) and `SPOTULE_CRON_SECRET` (matching `CRON_SECRET`).
   The workflow then sweeps every five minutes. Run it once by hand from the Actions tab to
   confirm it returns HTTP 200.

### Running without a worker, in detail

| Endpoint | Job |
|---|---|
| `POST /api/v1/cron/run` | All of the below in one call. Point your scheduler here. |
| `POST /api/v1/cron/ingest` | Log new plays for every user with the logger enabled |
| `POST /api/v1/cron/catalog` | Hydrate artist genres and imported tracks, relink imported streams |
| `POST /api/v1/cron/milestones` | Award newly reached milestones |
| `POST /api/v1/cron/automations` | Fire due per-user automations and run each tool inline |

All of them require `Authorization: Bearer $CRON_SECRET`, compared in constant time. If
`CRON_SECRET` is unset the whole router answers 503, so an unconfigured deployment cannot leak
them. Each sweep isolates failures per user, so one revoked token never aborts the batch.

Five minutes is comfortable. Spotify returns your last 50 plays, which is several hours of
listening, so even a badly delayed run loses nothing.

## Production checklist

- [ ] Redirect URI registered in the Spotify dashboard, matching `SPOTIFY_REDIRECT_URI` exactly
- [ ] `TOKEN_ENCRYPTION_KEY` backed up somewhere outside the server. Lose it and every stored Spotify token becomes undecryptable, and everyone must re-link their account
- [ ] `COOKIE_SECURE=true` and the site served over HTTPS
- [ ] `alembic upgrade head` applied
- [ ] Either a worker is running, or the scheduler is hitting `/api/v1/cron/run` and returning 200
- [ ] A database backup you have actually tested restoring
