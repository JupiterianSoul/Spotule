#!/usr/bin/env bash
# Generates every secret the hosted (Render + Supabase + Upstash) deployment needs and prints
# them as a fill-in-the-blanks checklist. Nothing is written to disk or sent anywhere.
#
#   bash scripts/render-secrets.sh                 # generate secrets only
#   bash scripts/render-secrets.sh <supabase-url> <upstash-url>
#
# Passing the two connection strings also converts them into the exact values Spotule expects.
set -euo pipefail

py() { command -v python3 >/dev/null 2>&1 && python3 "$@"; }

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to generate a Fernet key." >&2
  exit 1
fi

SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
CRON_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
TOKEN_ENCRYPTION_KEY="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"

SUPABASE_URL="${1:-}"
UPSTASH_URL="${2:-}"

DATABASE_URL="postgresql+asyncpg://…   <- paste your Supabase connection string, scheme replaced"
DATABASE_URL_SYNC="postgresql+psycopg://…  <- same string, different scheme"

if [ -n "$SUPABASE_URL" ]; then
  # Supabase hands you postgresql://… ; SQLAlchemy needs an explicit driver in the scheme.
  BASE="${SUPABASE_URL#postgresql://}"
  BASE="${BASE#postgres://}"
  BASE="${BASE%%\?*}"
  DATABASE_URL="postgresql+asyncpg://${BASE}"
  DATABASE_URL_SYNC="postgresql+psycopg://${BASE}"
fi

cat <<BANNER

──────────────────────────────────────────────────────────────────────────────
 Spotule — hosted deployment secrets
 Generated locally. Nothing here has been saved or transmitted.
──────────────────────────────────────────────────────────────────────────────

BANNER

echo "Set these on the spotule-api service:"
echo
printf '  %-22s %s\n' "SECRET_KEY" "$SECRET_KEY"
printf '  %-22s %s\n' "TOKEN_ENCRYPTION_KEY" "$TOKEN_ENCRYPTION_KEY"
printf '  %-22s %s\n' "CRON_SECRET" "$CRON_SECRET"
printf '  %-22s %s\n' "DATABASE_URL" "$DATABASE_URL"
printf '  %-22s %s\n' "DATABASE_URL_SYNC" "$DATABASE_URL_SYNC"
printf '  %-22s %s\n' "REDIS_URL" "${UPSTASH_URL:-rediss://…   <- paste your Upstash URL}"
printf '  %-22s %s\n' "SPOTIFY_CLIENT_ID" "<from the Spotify dashboard>"
printf '  %-22s %s\n' "SPOTIFY_CLIENT_SECRET" "<from the Spotify dashboard>"
echo
echo "  Once spotule-web has a URL, set all three to it:"
printf '  %-22s %s\n' "WEB_BASE_URL" "https://<spotule-web>.onrender.com"
printf '  %-22s %s\n' "API_BASE_URL" "https://<spotule-web>.onrender.com"
printf '  %-22s %s\n' "SPOTIFY_REDIRECT_URI" "https://<spotule-web>.onrender.com/api/v1/auth/callback"
echo
echo "Set this on the spotule-web service:"
echo
printf '  %-22s %s\n' "API_INTERNAL_URL" "https://<spotule-api>.onrender.com"
echo
echo "Add these as GitHub repository secrets (Settings > Secrets and variables > Actions):"
echo
printf '  %-22s %s\n' "SPOTULE_URL" "https://<spotule-api>.onrender.com"
printf '  %-22s %s\n' "SPOTULE_CRON_SECRET" "$CRON_SECRET"
echo
echo "And register this exact Redirect URI in the Spotify dashboard:"
echo
echo "  https://<spotule-web>.onrender.com/api/v1/auth/callback"
echo
cat <<'WARNING'
──────────────────────────────────────────────────────────────────────────────
 Save TOKEN_ENCRYPTION_KEY somewhere outside the server, now.
 It encrypts every stored Spotify token. Lose it and all of them become
 undecryptable, and everyone has to reconnect their account.
──────────────────────────────────────────────────────────────────────────────
WARNING
