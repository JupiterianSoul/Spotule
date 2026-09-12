"""Token-at-rest encryption and opaque session handling.

Design:
- Spotify access/refresh tokens are encrypted with Fernet (AES-128-CBC + HMAC) before they
  touch Postgres. Losing the DB alone does not leak tokens.
- Browser sessions are opaque random IDs stored in Redis (`session:<id>` → user_id), sent as
  an HttpOnly, SameSite=Lax cookie. Nothing user-controlled is trusted client-side.
"""

from __future__ import annotations

import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@lru_cache
def _fernet() -> Fernet:
    key = settings.token_encryption_key
    if not key or key == "change-me":
        if settings.is_prod:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be set in production")
        # Deterministic dev-only key so restarts keep tokens readable.
        key = Fernet.generate_key().decode() if not settings.secret_key else _derive_dev_key()
    return Fernet(key)


def _derive_dev_key() -> str:
    import base64
    import hashlib

    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode()


def encrypt_token(raw: str) -> str:
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_token(enc: str) -> str:
    try:
        return _fernet().decrypt(enc.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover
        raise RuntimeError("Stored Spotify token cannot be decrypted (key rotated?)") from exc


def new_session_id() -> str:
    return secrets.token_urlsafe(48)


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def redact(message: str, limit: int = 400) -> str:
    """Strip anything secret out of an exception message.

    Connection errors quote the DSN, so the raw text can carry a password. This replaces every
    known secret (and the user/host from each URL) before the message is shown anywhere public.
    """
    from sqlalchemy.engine import make_url

    from app.core.config import settings

    hide: set[str] = set()
    for url in (settings.database_url, settings.database_url_sync, settings.redis_url):
        try:
            parsed = make_url(url)
            hide.update(str(p) for p in (parsed.password, parsed.username, parsed.host) if p)
        except Exception:  # noqa: BLE001 — a malformed URL is exactly when we still need this
            pass
    hide.update(
        v
        for v in (
            settings.spotify_client_secret,
            settings.token_encryption_key,
            settings.secret_key,
            settings.cron_secret,
        )
        if v
    )
    out = message
    for secret in sorted(hide, key=len, reverse=True):
        if len(secret) > 2:
            out = out.replace(secret, "***")
    return out[:limit]
