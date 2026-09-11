# Spotule — honest status

What actually works, what is half-built, and what has never run against real Spotify
credentials. Kept separate from the feature matrix so it stays blunt.

Last updated alongside the commit that added the friends feature and the tools batch.

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
- **Web Playback SDK bridge.** The backend endpoint exists; the browser-side listener that
  would give the skip guard near-zero latency does not.
- **Artist and track drill-down pages.** Listed in the matrix, not built.
- About twenty-five tools in the matrix still marked 📝, mostly URL scrapers for the Audio
  Porter, cover-art upload and the weekly e-mail report (which needs an SMTP provider).

## Never run against real Spotify

Everything that calls the Spotify Web API has been written against the documented shapes and
exercised with stub data, but no request has been made with a real token. Expect the first live
run to surface small mismatches. The most likely places, in rough order:

1. Field shapes in playlist item responses, where Spotify's `fields=` masks are fussy.
2. The audio-features fallback chain, since Spotify returns 403 for apps created after
   2024-11-27 and the alternate provider's response shape is assumed, not observed.
3. Discover Weekly and Release Radar access, which is restricted for new apps. The name-based
   resolver and the shadow-capture fallback are both written for this, but which path actually
   runs depends on your app's quota mode.
4. Rate-limit behaviour under a real multi-user load.

None of these are structural. They are the kind of thing a first live run finds and a small
fix resolves.

## Known non-issues

- The `docker compose` files and Dockerfiles have not been built, because this project was
  developed in a sandbox with the Docker CLI but no daemon. Dependency completeness was checked
  by comparing every import against the manifest instead, which caught one package that was
  only present transitively.
