"""Scheduler endpoints — how Spotule runs its background work without a worker process.

Every periodic job is exposed as an authenticated POST so any external scheduler can drive it:
GitHub Actions, a Cloudflare cron trigger, `cron` on a spare machine, or an uptime pinger.
This is what makes free hosting viable (see docs/DEPLOYMENT.md).

Authentication is a single shared secret in `CRON_SECRET`, compared in constant time and sent
as `Authorization: Bearer <secret>`. If the variable is unset the whole router answers 503, so
an unconfigured deployment can never expose these publicly by accident.

Not covered here: the real-time skip guard. It polls playback every few seconds and needs a
resident process (`make worker`), so it stays off on cron-only deployments.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.deps import DB
from app.core.config import settings
from app.services import sweeps

router = APIRouter(prefix="/cron", tags=["cron"])


async def require_cron_secret(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.cron_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Scheduler endpoints are disabled: CRON_SECRET is not set.",
        )
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:]
    if not secrets.compare_digest(provided, settings.cron_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid scheduler credentials.")


Protected = Depends(require_cron_secret)


@router.post("/run", dependencies=[Protected])
async def run_all(db: DB) -> dict:
    """Everything a scheduler needs, in one call. Point your cron here every 5 minutes."""
    return await sweeps.sweep_all(db)


@router.post("/ingest", dependencies=[Protected])
async def ingest(db: DB, max_users: int = 100) -> dict:
    """Pillar 2: log new plays from /me/player/recently-played for every opted-in user."""
    return (await sweeps.sweep_recently_played(db, max_users)).as_dict()


@router.post("/catalog", dependencies=[Protected])
async def catalog(db: DB) -> dict:
    """Back-fill artist genres and imported-track metadata, then relink imported streams."""
    result = (await sweeps.sweep_catalog(db)).as_dict()
    result["streams_relinked"] = await sweeps.relink_imported_streams(db)
    return result


@router.post("/milestones", dependencies=[Protected])
async def milestones(db: DB, max_users: int = 100) -> dict:
    return (await sweeps.sweep_milestones(db, max_users)).as_dict()


@router.post("/automations", dependencies=[Protected])
async def automations(db: DB, max_jobs: int = 50) -> dict:
    """Fire due per-user automations (weekly backups) and run each tool inline."""
    return (await sweeps.sweep_automations(db, max_jobs)).as_dict()
