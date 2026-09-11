"""Upload the Spotify data-export ZIP; parsing happens in a worker."""

from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles  # noqa: F401  (declared in Dockerfile extras; used below)
from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, Locale
from app.core.config import settings
from app.core.i18n import t
from app.models import ImportJob
from app.workers.tasks import imports as tasks

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("", status_code=202)
async def upload(user: CurrentUser, db: DB, locale: Locale, file: UploadFile):
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, t("imports.zip_only", locale))
    dest_dir = Path(settings.import_upload_dir) / str(user.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4()}.zip"
    size = 0
    limit = settings.import_max_upload_mb * 1024 * 1024
    async with aiofiles.open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                await out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, t("imports.too_large", locale))
            await out.write(chunk)
    job = ImportJob(
        user_id=user.id, filename=file.filename or "export.zip", storage_key=str(dest), size_bytes=size
    )
    db.add(job)
    await db.commit()
    tasks.run_import_task.delay(str(job.id))
    return {"job_id": str(job.id), "status": job.status.value}


@router.get("")
async def list_jobs(user: CurrentUser, db: DB):
    rows = (
        (
            await db.execute(
                select(ImportJob).where(ImportJob.user_id == user.id).order_by(ImportJob.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_job(j) for j in rows]


@router.get("/{job_id}")
async def job_status(user: CurrentUser, db: DB, job_id: uuid.UUID):
    j = await db.get(ImportJob, job_id)
    if j is None or j.user_id != user.id:
        raise HTTPException(404)
    return _job(j)


def _job(j: ImportJob) -> dict:
    return {
        "id": str(j.id),
        "filename": j.filename,
        "status": j.status.value,
        "files_total": j.files_total,
        "files_done": j.files_done,
        "rows_total": j.rows_total,
        "rows_inserted": j.rows_inserted,
        "rows_skipped_duplicate": j.rows_skipped_duplicate,
        "rows_skipped_invalid": j.rows_skipped_invalid,
        "earliest": j.earliest_played_at,
        "latest": j.latest_played_at,
        "error": j.error,
        "created_at": j.created_at,
        "finished_at": j.finished_at,
    }
