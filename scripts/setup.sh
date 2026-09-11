#!/usr/bin/env bash
# Spotule first-run setup: creates .env with strong random secrets and asks only for the
# two values that must come from your Spotify developer app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"

gen() {  # 1 = fernet (32-byte urlsafe base64), otherwise a long random token
  if command -v python3 >/dev/null 2>&1; then
    if [ "${1:-}" = "fernet" ]; then
      python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    else
      python3 -c "import secrets;print(secrets.token_urlsafe(48))"
    fi
  elif command -v openssl >/dev/null 2>&1; then
    if [ "${1:-}" = "fernet" ]; then openssl rand -base64 32 | tr '+/' '-_'; else openssl rand -base64 48 | tr -d '\n' | tr '+/' '-_'; fi
  else
    echo "Need python3 or openssl to generate secrets." >&2; exit 1
  fi
}

if [ -f "$ENV_FILE" ]; then
  echo "✋ $ENV_FILE already exists — leaving it alone."
  echo "   Delete it first if you want to regenerate."
  exit 0
fi

echo "── Spotule setup ─────────────────────────────────────────────"
echo "Create a Spotify app at https://developer.spotify.com/dashboard"
echo "and add this Redirect URI to it (exactly):"
echo
echo "    http://127.0.0.1:8000/api/v1/auth/callback"
echo
read -r -p "Spotify Client ID     : " CLIENT_ID
read -r -s -p "Spotify Client Secret : " CLIENT_SECRET; echo
echo

cp "$ROOT/.env.example" "$ENV_FILE"
SECRET_KEY="$(gen token)"
FERNET_KEY="$(gen fernet)"

# Portable in-place edit (GNU and BSD sed disagree about -i)
replace() { sed "s|^$1=.*|$1=$2|" "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"; }
replace SPOTIFY_CLIENT_ID "$CLIENT_ID"
replace SPOTIFY_CLIENT_SECRET "$CLIENT_SECRET"
replace SECRET_KEY "$SECRET_KEY"
replace TOKEN_ENCRYPTION_KEY "$FERNET_KEY"
chmod 600 "$ENV_FILE"

echo "✅ Wrote $ENV_FILE (secrets generated, file mode 600)."
echo
echo "Next:  docker compose up --build"
echo "Then:  open http://127.0.0.1:3000/en   (or /fr)"
