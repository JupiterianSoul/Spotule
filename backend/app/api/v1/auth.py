"""Spotify OAuth2 login / callback / logout. Sessions are opaque ids in Redis."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Locale
from app.core.config import settings
from app.core.i18n import t
from app.core.security import new_oauth_state, new_session_id
from app.db.redis import Keys, get_redis
from app.models import User, UserPreference
from app.models.enums import Locale as LocaleEnum
from app.services.spotify import SpotifyClient
from app.services.spotify.auth import build_authorize_url, exchange_code, store_tokens

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(locale: Locale, next: str = Query("/", alias="next"), show_dialog: bool = False):
    state = new_oauth_state()
    await get_redis().set(Keys.oauth_state(state), f"{locale}|{next}", ex=600)
    return RedirectResponse(build_authorize_url(state, show_dialog))


@router.get("/callback")
async def callback(
    db: DB, request: Request, code: str | None = None, state: str | None = None, error: str | None = None
):
    r = get_redis()
    stored = await r.get(Keys.oauth_state(state or ""))
    if not stored:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid oauth state")
    await r.delete(Keys.oauth_state(state))
    locale, next_path = stored.split("|", 1)
    if error or not code:
        return RedirectResponse(f"{settings.web_base_url}/{locale}?error={error or 'denied'}")

    tokens = await exchange_code(code)
    async with SpotifyClient(tokens["access_token"]) as client:
        profile = await client.me()

    user = (await db.execute(select(User).where(User.spotify_id == profile["id"]))).scalar_one_or_none()
    if user is None:
        user = User(spotify_id=profile["id"])
        db.add(user)
        await db.flush()
        db.add(UserPreference(user_id=user.id, locale=LocaleEnum(locale)))
    user.display_name = profile.get("display_name")
    user.email = profile.get("email")
    user.country = profile.get("country")
    user.product = profile.get("product")
    user.avatar_url = (profile.get("images") or [{}])[0].get("url")
    user.last_login_at = datetime.now(UTC)
    await store_tokens(db, user, tokens)
    await db.commit()

    sid = new_session_id()
    await r.set(Keys.session(sid), str(user.id), ex=settings.session_ttl_seconds)
    resp = RedirectResponse(
        f"{settings.web_base_url}/{locale}{next_path if next_path.startswith('/') else '/'}"
    )
    resp.set_cookie(
        settings.session_cookie_name,
        sid,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return resp


@router.post("/logout")
async def logout(request: Request, response: Response, user: CurrentUser, locale: Locale):
    sid = request.cookies.get(settings.session_cookie_name)
    if sid:
        await get_redis().delete(Keys.session(sid))
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True, "message": t("auth.logged_out", locale)}
