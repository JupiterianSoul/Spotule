"""Celery driver for tool runs. The semantics live in `services/tools/runner.py`, which the
cron endpoints use too, so a worker-based and a worker-free deployment behave identically."""

from __future__ import annotations

import uuid

from app.db.session import AsyncSessionLocal
from app.models import ToolRun
from app.services.tools.runner import execute_tool_run
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async, with_user


@celery_app.task(name="tools.run", time_limit=3600)
def run_tool_task(run_id: str) -> None:
    async def _owner() -> str | None:
        async with AsyncSessionLocal() as db:
            run = await db.get(ToolRun, uuid.UUID(run_id))
            return str(run.user_id) if run else None

    async def _run(db, user, client):
        run = await db.get(ToolRun, uuid.UUID(run_id))
        if run is not None:
            await execute_tool_run(db, client, user, run)

    owner_id = run_async(_owner())
    if owner_id:
        run_async(with_user(owner_id, _run))
