"""OAuth2 Authorization Code flow + transparent refresh with per-user token isolation."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import SPOTIFY_SCOPES, settings
from app.core.security import decrypt_token, encrypt_token
from app.models import SpotifyCredential, User


def build_authorize_url(state: str, show_dialog: bool = False) -> str:
    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": " ".join(SPOTIFY_SCOPES),
        "state": state,
        "show_dialog": "true" if show_dialog else "false",
    }
    return f"{settings.spotify_accounts_base}/authorize?{urlencode(params)}"


def _basic_auth_header() -> dict[str, str]:
    raw = f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.spotify_accounts_base}/api/token",
            headers=_basic_auth_header(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.spotify_accounts_base}/api/token",
            headers=_basic_auth_header(),
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        resp.raise_for_status()
        return resp.json()


async def store_tokens(db: AsyncSession, user: User, payload: dict) -> SpotifyCredential:
    expires_at = datetime.now(UTC) + timedelta(seconds=int(payload.get("expires_in", 3600)))
    cred = await db.get(SpotifyCredential, user.id)
    if cred is None:
        cred = SpotifyCredential(
            user_id=user.id,
            access_token_enc=encrypt_token(payload["access_token"]),
            refresh_token_enc=encrypt_token(payload["refresh_token"]),
            scopes=payload.get("scope", " ".join(SPOTIFY_SCOPES)),
            expires_at=expires_at,
        )
        db.add(cred)
    else:
        cred.access_token_enc = encrypt_token(payload["access_token"])
        if payload.get("refresh_token"):  # Spotify only rotates it sometimes
            cred.refresh_token_enc = encrypt_token(payload["refresh_token"])
        cred.scopes = payload.get("scope", cred.scopes)
        cred.expires_at = expires_at
        cred.revoked_at = None
    return cred


async def get_valid_access_token(db: AsyncSession, cred: SpotifyCredential) -> str:
    """Return a usable access token, refreshing (and persisting) if it expires in < 2 min."""
    if cred.expires_at - datetime.now(UTC) > timedelta(minutes=2):
        return decrypt_token(cred.access_token_enc)
    payload = await refresh_access_token(decrypt_token(cred.refresh_token_enc))
    cred.access_token_enc = encrypt_token(payload["access_token"])
    if payload.get("refresh_token"):
        cred.refresh_token_enc = encrypt_token(payload["refresh_token"])
    cred.expires_at = datetime.now(UTC) + timedelta(seconds=int(payload.get("expires_in", 3600)))
    await db.commit()
    return payload["access_token"]
