from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import redact
from app.db.redis import get_redis

log = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await get_redis().ping()
    log.info("spotule.api.start", env=settings.app_env)
    yield
    await get_redis().aclose()


app = FastAPI(
    title="Spotule API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.is_prod else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


# Render exports this automatically; other hosts can set it themselves. Without it there is no
# way to tell from outside whether a push has actually reached the running container, which
# turns "is my fix live yet?" into guesswork every single deploy.
BUILD_COMMIT = (os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or "")[:7]


@app.get("/healthz", include_in_schema=False)
async def healthz(request: Request):
    return {"ok": True, "env": settings.app_env, "commit": BUILD_COMMIT}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> JSONResponse:
    """Are the dependencies actually usable?

    /healthz only proves the process is up. Every database call sits behind authentication,
    so a broken connection or an unapplied migration stays invisible until a user signs in
    and gets a 500. This exercises each dependency directly.

    Only booleans and exception class names are reported: messages can contain the host and
    user from a connection string, and this endpoint is public.
    """
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    checks: dict[str, object] = {}

    try:
        await get_redis().ping()
        checks["redis"] = True
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = False
        checks["redis_error"] = type(exc).__name__

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:  # noqa: BLE001
        checks["database"] = False
        checks["database_error"] = type(exc).__name__
        checks["database_detail"] = redact(str(exc))

    # Migrations applied? A reachable but empty database fails only once someone signs in.
    if checks.get("database"):
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1 FROM users LIMIT 1"))
            checks["schema"] = True
        except Exception as exc:  # noqa: BLE001
            checks["schema"] = False
            checks["schema_error"] = type(exc).__name__

    # Token encryption is configured correctly? A bad key fails at the end of the OAuth
    # callback, after Spotify has already redirected back, which reads as a login bug.
    try:
        from app.core.security import decrypt_token, encrypt_token

        checks["token_encryption"] = decrypt_token(encrypt_token("probe")) == "probe"
    except Exception as exc:  # noqa: BLE001
        checks["token_encryption"] = False
        checks["token_encryption_error"] = type(exc).__name__

    ok = all(v is True for k, v in checks.items() if not k.endswith("_error"))
    checks["ok"] = ok
    return JSONResponse(checks, status_code=200 if ok else 503)
