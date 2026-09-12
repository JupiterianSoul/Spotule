# Spotule — honest status

What actually works, what is half-built, and what has never run against real Spotify
credentials. Kept separate from the feature matrix so it stays blunt.

Last updated after the first live deployment: Render + Supabase + Upstash, signed in with a
real Spotify account, sweeps driven by GitHub Actions.

## Verified working

Covered by automated tests, or exercised against live local servers.

- Sign-in plumbing: OAuth redirect to Spotify, encrypted token storage, opaque Redis sessions,
  localised API errors. The redirect and the 401 path are checked by the smoke test; the full
  round trip needs a real Spotify account (see below).
- The same-origin API proxy, including cookies, redirects, streamed bodies and a 120 MB upload.
- Lifetime tracking engine: the recently-played poller, the extended-history ZIP importer,
  catalogue hydration and relinking. Unit-tested on real export payloads.
- Analytics queries: overview, top tracks/artists/albums/genres, listening clock, milestones.
- Ban-hammer rule evaluation, including contains/exact/regex modes and exemptions.
- Twenty-five playlist and library tools: true shuffle, blender, splitter, sort, reverse, copy,
  set operations, prune, subtract-liked, export, bulk delete/unfollow/rename/visibility/
  describe/dedupe, sonic filter and mood presets, monthly best-of and forgotten favourites from
  the ledger, Liked Songs mirror, backups and restore. Pure logic is tested; the Spotify calls
  are not (see below).
- Friends: search, request, accept, decline, remove, with the crossed-request case, covered by
  an integration test running two real users through the API with real sessions.
- Automations page with an inline editor for the schedule and an optional playlist id.
- New-milestone badge on the dashboard, cleared server-side once shown.
- Scheduler endpoints and the GitHub Actions workflow that drives them.
- Bilingual UI: 190 keys per language, parity-checked in CI, both locales render.
- Database schema: 28 tables, migration applies and rolls back cleanly with no model drift.

## Not finished

- **Skip guard on free hosting.** Works in principle and the code is complete, but it needs a
  process that never sleeps, so it cannot run on the Render free tier. The toggle stays off.
  Note this is the one pillar the cron-based scheduler cannot substitute for.
- **Web Playback SDK bridge.** The backend endpoint exists; the browser-side listener that
  would give the skip guard near-zero latency does not.
- **Artist and track drill-down pages.** Listed in the matrix, not built.
- About twenty-five tools in the matrix still marked 📝, mostly URL scrapers for the Audio
  Porter, cover-art upload and the weekly e-mail report (which needs an SMTP provider).

## Live behaviour, confirmed against real Spotify

The deployment is up and signed in with a real account. What the live runs settled:

- **Play logging works.** `/me/player/recently-played` is polled every five minutes and plays
  are stored. Getting there took four bugs, each hiding the next: sweep stages sharing one
  failure path, an error handler that crashed inside itself reading an expired ORM attribute
  after its own rollback, an upsert that Postgres refused because the feed returns one entry
  per *play* so a repeat put the same id in `VALUES` twice, and `rowcount` returning -1 on
  psycopg for multi-row inserts.
- **`GET /artists` is refused: 403 Forbidden.** Six well-formed ids, limit fifty, on the token
  that ingests that same account's plays in the same sweep; the ids check out as real artists
  against Spotify's public oEmbed. This is a restriction on the *application*, not the account
  or the request — nothing in this codebase lifts it. See below for what does.
- **Genres arrive anyway.** `/me/top/artists` and `/me/following` return full artist objects
  with genres and are user-data endpoints, which this app is allowed. 177 artists hydrated on
  the first fallback run. It covers what you listen to and follow — the set the Ban-Hammer
  needs — and not the rest of the catalogue.

## Needs Extended Quota Mode

Spotify grants development-mode apps a reduced surface. These stay limited until the app is
approved, and no amount of code changes that:

- Artist genres for anything outside your own top artists and follows (`GET /artists`).
- Audio features, and therefore the sonic filters and mood presets, for apps created after
  2024-11-27. The alternate provider chain exists but its response shape is assumed.
- Discover Weekly and Release Radar, which are not readable for new apps. The name-based
  resolver and shadow-capture fallback are written for this; which path runs depends on quota.
- More than 25 users, which is the development-mode cap.

## Still unexercised against real Spotify

Written against the documented shapes and tested with stub data, but not yet run live:

- The twenty-five playlist and library tools. Pure logic is tested; the Spotify calls are not.
  Playlist item responses are the likeliest mismatch, where `fields=` masks are fussy.
- The extended-history ZIP importer against a real export (tested on real export payloads, but
  never end to end through the live deployment).
- Rate-limit behaviour under real multi-user load.

## Known non-issues

- The `docker compose` files have not been built locally, because this project was developed
  in a sandbox with the Docker CLI but no daemon. The Dockerfiles themselves are no longer
  unverified: Render builds both of them on every deploy.
- `streams_inserted: 0` on a sweep is normal. The cursor only asks for plays newer than the
  last one stored, so a run with nothing new to fetch is a working run, not a broken one.
- `artists_source: "listening (cached)"` is also normal. Top artists and follows are re-read
  every six hours, not every five minutes.
