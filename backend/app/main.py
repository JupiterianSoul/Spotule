from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.redis import get_redis

log = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await get_redis().ping()
    log.info("spotimax.api.start", env=settings.app_env)
    yield
    await get_redis().aclose()


app = FastAPI(
    title="SpotiMax API",
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


@app.get("/healthz", include_in_schema=False)
async def healthz(request: Request):
    return {"ok": True, "env": settings.app_env}
