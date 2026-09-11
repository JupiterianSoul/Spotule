# Spotule — free hosted setup (Render + Supabase + Upstash + GitHub Actions)

No VM, no card, nothing to pay. You keep the lifetime tracking engine, the analytics, the
ban-hammer library purger and every playlist tool. You give up the real-time skip guard, which
needs a process that never sleeps.

Work through this once, top to bottom. The order matters: it avoids the chicken-and-egg where
each service needs the other's URL.

---

## 1. Database — Supabase

Create a free project. When it is ready, open **Connect** and copy the **Session pooler**
connection string. It looks like:

```
postgresql://postgres.abcdefgh:YOUR-PASSWORD@aws-0-eu-west-3.pooler.supabase.com:5432/postgres
```

Take the session pooler specifically, not the direct connection and not the transaction pooler:

- The direct connection (`db.<ref>.supabase.co`) is IPv6-only on many projects, and Render does
  not reliably have IPv6 outbound.
- The transaction pooler (port 6543) breaks server-side prepared statements. Spotule detects
  pooled URLs and disables its statement cache to compensate, but session mode avoids the whole
  problem.

## 2. Redis — Upstash

Create a free Redis database in a region near your Render one. Copy the `rediss://` URL from
the connection details. Spotule uses Redis for sessions, the Spotify rate-limit bucket and
short-lived caches, so the free tier is comfortable.

## 3. Generate your secrets

From a clone of this repo:

```bash
bash scripts/render-secrets.sh "<supabase-session-pooler-url>" "<upstash-rediss-url>"
```

It prints every value you need, already converted into the right form, and writes nothing to
disk. Keep the output open in a window; you will paste from it three times.

**Save `TOKEN_ENCRYPTION_KEY` somewhere outside all of this before continuing.** It encrypts
every stored Spotify token. If it is lost, every token becomes undecryptable and everyone has to
reconnect their account.

## 4. Spotify app

At <https://developer.spotify.com/dashboard>, create an app if you have not already, and note
the Client ID and Client Secret. Leave the Redirect URI for step 6, once you know your URL.

## 5. Deploy on Render

**New → Blueprint**, point it at this repository. `render.yaml` creates two free web services,
`spotule-api` and `spotule-web`, and prompts for the environment variables marked `sync: false`.
Fill them from the script output. Leave the three URL variables blank for now.

First build takes a few minutes. `spotule-api` runs `alembic upgrade head` on every boot, so the
schema is created automatically.

## 6. Wire the two services together

Both now have public URLs. Set the cross-references:

On **spotule-web**:

| Variable | Value |
|---|---|
| `API_INTERNAL_URL` | the **spotule-api** URL |

On **spotule-api**:

| Variable | Value |
|---|---|
| `WEB_BASE_URL` | the **spotule-web** URL |
| `API_BASE_URL` | the **spotule-web** URL |
| `SPOTIFY_REDIRECT_URI` | the **spotule-web** URL + `/api/v1/auth/callback` |

The redirect URI points at the *web* service, not the API, because the browser only ever talks
to the web origin. Next proxies `/api/*` to the API server-side, which is what keeps the session
cookie first-party and therefore working in Safari.

Now add that same redirect URI in the Spotify dashboard, character for character.

Let both services redeploy.

## 7. Turn on the scheduler

Free hosts have no always-on worker, so GitHub Actions drives the periodic jobs. Under
**Settings → Secrets and variables → Actions** in this repository, add:

| Secret | Value |
|---|---|
| `SPOTULE_URL` | the **spotule-api** URL |
| `SPOTULE_CRON_SECRET` | the `CRON_SECRET` from step 3 |

Point it at the API service, not the web one. Free instance-hours are a shared monthly budget,
and keeping only one service awake stays inside it. The web service sleeps when nobody is
browsing and wakes on the next visit.

Open the **Actions** tab, pick *Spotule scheduler*, and hit **Run workflow**. A green run means
everything is connected.

## 8. Verify

```bash
curl https://<spotule-api>.onrender.com/healthz
# {"ok":true,"env":"production"}

curl https://<spotule-web>.onrender.com/healthz
# {"ok":true,"web":true,"api":true}      <- the web service can reach the API
```

Then open the web URL, switch between English and French, and sign in with Spotify. Play
something, wait for the scheduler to run, and check that the dashboard's stream count moves.

## What to expect day to day

**Cold starts.** The web service sleeps after a quiet spell, so the first visit can take up to a
minute. Subsequent navigation is normal.

**Scheduler timing.** GitHub runs the workflow roughly every five minutes, but it is best-effort
and can be delayed under load. This costs nothing: Spotify returns your last 50 plays, which is
several hours of listening.

**The 60-day rule.** On a public repository, GitHub disables scheduled workflows after 60 days
with no commits. Push anything, or press Run workflow, to re-arm them.

**Supabase pausing.** Free projects pause after about a week with no queries. The scheduler's
sweeps keep yours active.

**No skip guard.** The toggle stays off. It polls playback every few seconds and cannot run on a
service that sleeps. If you want it, `docs/DEPLOYMENT.md` describes the always-free VM route,
which keeps every feature.

## If something is wrong

| Symptom | Cause |
|---|---|
| Sign-in returns `INVALID_CLIENT: Invalid redirect URI` | The Spotify dashboard URI and `SPOTIFY_REDIRECT_URI` differ. They must match exactly, including `https://` and any trailing path. |
| Signed in, but every page bounces back to the landing page | The cookie is not sticking. Check `COOKIE_SECURE=true` and that `API_INTERNAL_URL` on the web service points at the API service. |
| Web `/healthz` reports `"api": false` | The API is asleep or misconfigured. Open the API URL directly to wake it and read its logs. |
| Scheduler run fails with 401 | `SPOTULE_CRON_SECRET` and `CRON_SECRET` do not match. |
| Scheduler run fails with 503 | `CRON_SECRET` is not set on the API service. |
| `InvalidSQLStatementNameError` in the API logs | A transaction-pooler URL slipped in. Use the session pooler, or set `DB_POOLER_MODE=on`. |
