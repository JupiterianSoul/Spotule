from __future__ import annotations

import uuid

from app.db.session import SyncSessionLocal
from app.models import ImportJob
from app.services.ingest.json_importer import run_import
from app.workers.celery_app import celery_app


@celery_app.task(name="imports.run", acks_late=True, time_limit=6 * 3600)
def run_import_task(job_id: str) -> None:
    with SyncSessionLocal() as db:
        job = db.get(ImportJob, uuid.UUID(job_id))
        if job is None:
            return
        run_import(db, job)
    # Hydration + relink happen on the next `catalog.hydrate` beat.
