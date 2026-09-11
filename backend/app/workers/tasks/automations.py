"""Per-user cron automations → tool runs."""

from __future__ import annotations

from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select

from app.db.session import SyncSessionLocal
from app.models import AutomationJob, ToolRun
from app.models.enums import AutomationKind, BackupKind
from app.workers.celery_app import celery_app
from app.workers.tasks.tools import run_tool_task

# Which tool each automation kind runs and with what params.
KIND_TO_TOOL: dict[AutomationKind, tuple[str, dict]] = {
    AutomationKind.backup_discover_weekly: ("backup.playlist", {"kind": BackupKind.discover_weekly.value}),
    AutomationKind.backup_release_radar: ("backup.playlist", {"kind": BackupKind.release_radar.value}),
    AutomationKind.liked_songs_snapshot: ("backup.playlist", {"kind": BackupKind.manual.value}),
}


@celery_app.task(name="automations.tick")
def automations_tick() -> int:
    now = datetime.now(UTC)
    fired = 0
    with SyncSessionLocal() as db:
        jobs = db.execute(select(AutomationJob).where(AutomationJob.enabled.is_(True))).scalars().all()
        for job in jobs:
            base = job.last_run_at or job.created_at
            if not croniter.is_valid(job.cron):
                continue
            due = croniter(job.cron, base).get_next(datetime)
            job.next_run_at = due
            if due > now:
                continue
            mapping = KIND_TO_TOOL.get(job.kind)
            if mapping:
                tool_key, defaults = mapping
                run = ToolRun(
                    user_id=job.user_id,
                    automation_job_id=job.id,
                    tool_key=tool_key,
                    params={**defaults, **job.config},
                )
                db.add(run)
                db.flush()
                run_tool_task.delay(str(run.id))
                fired += 1
            job.last_run_at = now
        db.commit()
    return fired
