"""FastAPI dependencies: session cookie → User, locale negotiation, per-user Spotify client."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.i18n import negotiate_locale, t
from app.db.redis import Keys, get_redis
from app.db.session import get_db
from app.models import SpotifyCredential, User, UserPreference
from app.services.spotify import SpotifyClient
from app.services.spotify.auth import get_valid_access_token

DB = Annotated[AsyncSession, Depends(get_db)]


async def get_locale(
    request: Request,
    accept_language: Annotated[str | None, Header()] = None,
) -> str:
    return negotiate_locale(accept_language, request.query_params.get("lang"))


Locale = Annotated[str, Depends(get_locale)]


async def get_current_user(
    db: DB,
    locale: Locale,
    session_cookie: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> User:
    if not session_cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("errors.not_authenticated", locale))
    user_id = await get_redis().get(Keys.session(session_cookie))
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("errors.session_expired", locale))
    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("errors.not_authenticated", locale))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_user_locale(user: CurrentUser, db: DB, locale: Locale) -> str:
    pref = await db.get(UserPreference, user.id)
    return pref.locale.value if pref else locale


UserLocale = Annotated[str, Depends(get_user_locale)]


async def get_spotify_client(user: CurrentUser, db: DB, locale: Locale) -> AsyncIterator[SpotifyClient]:
    cred = await db.get(SpotifyCredential, user.id)
    if cred is None or cred.revoked_at:
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("errors.spotify_not_linked", locale))
    token = await get_valid_access_token(db, cred)
    async with SpotifyClient(token) as client:
        yield client


Spotify = Annotated[SpotifyClient, Depends(get_spotify_client)]


async def require_admin(user: CurrentUser, locale: Locale) -> User:
    if user.role.value != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("errors.forbidden", locale))
    return user
