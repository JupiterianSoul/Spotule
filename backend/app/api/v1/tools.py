"""Generic tool runner: catalogue + enqueue + poll."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Locale
from app.core.i18n import t
from app.models import ToolRun
from app.schemas.common import JobRef
from app.services.tools import registry
from app.workers.tasks import tools as tasks

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def catalogue(locale: Locale):
    return [
        {
            **spec.model_dump(),
            "title": t(("tools", spec.key, "title"), locale),
            "description": t(("tools", spec.key, "description"), locale),
        }
        for spec in registry.specs()
    ]


@router.post("/{key}/run", response_model=JobRef, status_code=202)
async def run_tool(user: CurrentUser, db: DB, locale: Locale, key: str, params: dict):
    if key not in registry:
        raise HTTPException(404, t("tools.unknown", locale))
    tool_cls = registry.get(key)
    if tool_cls.needs_premium and user.product != "premium":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, t("banhammer.premium_required", locale))
    try:
        parsed = tool_cls.Params.model_validate(params)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors()) from exc
    run = ToolRun(user_id=user.id, tool_key=key, params=parsed.model_dump(mode="json"))
    db.add(run)
    await db.commit()
    task = tasks.run_tool_task.delay(str(run.id))
    run.celery_task_id = task.id
    await db.commit()
    return JobRef(run_id=str(run.id), status=run.status.value, tool_key=key)


@router.get("/runs", response_model=list[JobRef])
async def runs(user: CurrentUser, db: DB, limit: int = 30):
    rows = (
        (
            await db.execute(
                select(ToolRun)
                .where(ToolRun.user_id == user.id)
                .order_by(ToolRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        JobRef(
            run_id=str(r.id),
            status=r.status.value,
            tool_key=r.tool_key,
            progress=r.progress,
            result=r.result,
            error=r.error,
        )
        for r in rows
    ]


@router.get("/runs/{run_id}", response_model=JobRef)
async def run_status(user: CurrentUser, db: DB, run_id: uuid.UUID):
    r = await db.get(ToolRun, run_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404)
    return JobRef(
        run_id=str(r.id),
        status=r.status.value,
        tool_key=r.tool_key,
        progress=r.progress,
        result=r.result,
        error=r.error,
    )
