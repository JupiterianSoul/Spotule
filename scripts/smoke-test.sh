#!/usr/bin/env bash
# End-to-end check of a running Spotule deployment.
#
#   bash scripts/smoke-test.sh https://spotule-web.onrender.com
#   bash scripts/smoke-test.sh https://spotule-web.onrender.com  https://spotule-api.onrender.com
#
# Add your CRON_SECRET to also exercise the scheduler:
#   CRON_SECRET=… bash scripts/smoke-test.sh https://…
#
# Checks what can be checked without a browser. Signing in with Spotify needs a human, so the
# last section tells you what to click and what you should see.
set -uo pipefail

WEB="${1:-http://127.0.0.1:3000}"
API="${2:-$WEB}"
WEB="${WEB%/}"
API="${API%/}"

pass=0
fail=0
warn=0

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; [ -n "${2:-}" ] && printf '      %s\n' "$2"; fail=$((fail+1)); }
note() { printf '  \033[33m!\033[0m %s\n' "$1"; warn=$((warn+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# A sleeping free service answers 502/503 immediately rather than making the caller wait, so a
# long timeout alone is not enough: the first probe has to be retried until the container wakes.
get() {
  local code
  for attempt in 1 2 3 4 5; do
    code=$(curl -sS --max-time 120 -o /tmp/smoke.body -w '%{http_code}' "$@" 2>/tmp/smoke.err)
    case "$code" in
      502|503|000) sleep $((attempt * 5)) ;;
      *) printf '%s' "$code"; return ;;
    esac
  done
  printf '%s' "$code"
}

head_ "Reachability  ($WEB)"
code=$(get "$WEB/healthz")
if [ "$code" = "200" ]; then
  ok "web /healthz responded 200"
  if grep -q '"api":true' /tmp/smoke.body 2>/dev/null; then
    ok "the web service can reach the API behind it"
  else
    bad "the web service cannot reach the API" "$(head -c 200 /tmp/smoke.body)"
    echo "      Check API_INTERNAL_URL on the web service points at the API service."
  fi
else
  bad "web /healthz returned ${code:-no response}" "$(head -c 200 /tmp/smoke.err)"
fi

head_ "Dependencies the API needs (database, schema, Redis, encryption)"
sha=$(curl -sS --max-time 60 "$API/healthz" 2>/dev/null \
      | python3 -c "import json,sys;print(json.load(sys.stdin).get('commit',''))" 2>/dev/null)
if [ -n "$sha" ]; then
  ok "API is running commit $sha"
  echo "      Compare with: git rev-parse --short HEAD"
else
  note "the API did not report a commit; it predates the build marker or the host does not set one"
fi
code=$(get "$API/readyz")
if [ "$code" = "200" ]; then
  ok "database, schema, Redis and token encryption all usable"
else
  bad "the API cannot use one of its dependencies (HTTP ${code:-none})" "$(head -c 240 /tmp/smoke.body)"
  echo "      false means broken; the *_error field names the exception."
  echo "      database:false  -> DATABASE_URL wrong, or the host is unreachable"
  echo "      schema:false    -> migrations did not run against this database"
  echo "      token_encryption:false -> TOKEN_ENCRYPTION_KEY is not a valid Fernet key"
fi

head_ "API through the same origin (this is what the browser uses)"
code=$(get "$WEB/api/v1/tools")
if [ "$code" = "200" ]; then
  count=$(python3 -c "import json;print(len(json.load(open('/tmp/smoke.body'))))" 2>/dev/null || echo "?")
  ok "tool catalogue served through the proxy ($count tools)"
else
  bad "/api/v1/tools through the proxy returned ${code:-no response}"
fi

head_ "Localisation"
en=$(curl -sS --max-time 60 "$WEB/api/v1/tools" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['title'])" 2>/dev/null)
fr=$(curl -sS --max-time 60 -H 'Accept-Language: fr' "$WEB/api/v1/tools" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['title'])" 2>/dev/null)
if [ -n "$en" ] && [ -n "$fr" ] && [ "$en" != "$fr" ]; then
  ok "API responds in both languages (\"$en\" / \"$fr\")"
else
  bad "API localisation not switching" "en='$en' fr='$fr'"
fi
for loc in en fr; do
  code=$(get "$WEB/$loc")
  [ "$code" = "200" ] && ok "/$loc renders" || bad "/$loc returned ${code:-no response}"
done
code=$(curl -sS --max-time 60 -o /dev/null -w '%{http_code}' "$WEB/" 2>/dev/null)
[ "$code" = "307" ] || [ "$code" = "308" ] || [ "$code" = "200" ] \
  && ok "/ redirects to a language" || bad "/ returned $code"

head_ "Authentication"
code=$(get "$WEB/api/v1/me")
if [ "$code" = "401" ]; then
  ok "signed-out request to /me is refused (401)"
else
  bad "/me returned $code for a signed-out request; expected 401"
fi
loc=$(curl -sS --max-time 60 -o /dev/null -D- "$WEB/api/v1/auth/login" 2>/dev/null | tr -d '\r' | awk 'tolower($1)=="location:"{print $2}')
case "$loc" in
  https://accounts.spotify.com/authorize*)
    ok "login redirects to Spotify"
    case "$loc" in
      *redirect_uri=https*) ok "the redirect URI it sends is https" ;;
      *) note "the redirect URI is not https; Spotify will reject it in production" ;;
    esac ;;
  "") bad "login did not redirect anywhere" "Is SPOTIFY_CLIENT_ID set on the API?" ;;
  *)  bad "login redirected somewhere unexpected" "$loc" ;;
esac

head_ "Scheduler"
if [ -n "${CRON_SECRET:-}" ]; then
  code=$(get -X POST "$API/api/v1/cron/run" -H "Authorization: Bearer $CRON_SECRET")
  if [ "$code" = "200" ]; then
    ok "sweep ran"
    python3 - <<'PY' 2>/dev/null || true
import json
d = json.load(open("/tmp/smoke.body"))
for name, block in d.items():
    if isinstance(block, dict):
        bits = ", ".join(f"{k}={v}" for k, v in block.items() if k != "errors")
        print(f"      {name}: {bits}")
        for e in block.get("errors", []):
            print(f"        error: {e}")
PY
  elif [ "$code" = "401" ]; then
    bad "scheduler rejected the secret" "CRON_SECRET here does not match the server's"
  elif [ "$code" = "503" ]; then
    bad "scheduler is disabled" "CRON_SECRET is not set on the API service"
  else
    bad "scheduler returned ${code:-no response}"
  fi
  code=$(get -X POST "$API/api/v1/cron/run")
  [ "$code" = "401" ] && ok "scheduler refuses unauthenticated calls" \
    || bad "scheduler returned $code without credentials; expected 401"
else
  note "CRON_SECRET not set, skipping. Re-run with: CRON_SECRET=… bash $0 $WEB"
fi

head_ "Result"
printf '  %d passed, %d failed, %d skipped\n' "$pass" "$fail" "$warn"

cat <<'MANUAL'

  What still needs a human (a browser and your Spotify account):

    1. Open the site and press Sign in with Spotify. You should land back on the
       dashboard with your name and avatar in the top right.
    2. Flip the language switch. Every label, including numbers and dates, changes.
    3. Play something on your phone, wait for one scheduler run, then reload the
       dashboard. Minutes listened and Streams should go up.
    4. Ban-Hammer: add the genre "rap", press Scan. It lists matching tracks from your
       Liked Songs without deleting anything. Nothing is removed until you press the
       second button.
    5. Tools: run True Shuffler on a small playlist you do not care about, then check
       Backups. There should be a snapshot from just before the shuffle.

  If step 1 fails, the cause is nearly always the Redirect URI: it must match what is
  registered in the Spotify dashboard exactly, including https and the full path.
MANUAL

[ "$fail" -eq 0 ] || exit 1
