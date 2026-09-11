from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models import AutomationJob
from app.models.enums import AutomationKind

router = APIRouter(prefix="/automations", tags=["automations"])


class AutomationIn(BaseModel):
    kind: AutomationKind
    cron: str = "0 6 * * 1"
    enabled: bool = True
    config: dict = {}


@router.get("")
async def list_automations(user: CurrentUser, db: DB):
    rows = (await db.execute(select(AutomationJob).where(AutomationJob.user_id == user.id))).scalars().all()
    return [
        {
            "id": str(a.id),
            "kind": a.kind.value,
            "cron": a.cron,
            "enabled": a.enabled,
            "config": a.config,
            "last_run_at": a.last_run_at,
            "next_run_at": a.next_run_at,
        }
        for a in rows
    ]


@router.post("", status_code=201)
async def create(user: CurrentUser, db: DB, body: AutomationIn):
    job = AutomationJob(user_id=user.id, **body.model_dump())
    db.add(job)
    await db.commit()
    return {"id": str(job.id)}


@router.patch("/{job_id}")
async def update(user: CurrentUser, db: DB, job_id: uuid.UUID, body: AutomationIn):
    job = await db.get(AutomationJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404)
    for k, v in body.model_dump().items():
        setattr(job, k, v)
    await db.commit()
    return {"ok": True}


@router.delete("/{job_id}", status_code=204)
async def delete(user: CurrentUser, db: DB, job_id: uuid.UUID):
    job = await db.get(AutomationJob, job_id)
    if job and job.user_id == user.id:
        await db.delete(job)
        await db.commit()
