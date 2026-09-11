"""Celery application. Two queues:
realtime — skip guard ticks (short, latency-sensitive, many)
default  — ingest, imports, tools, backups, analytics
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.core.config import settings

celery_app = Celery("spotimax", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_queues=(Queue("default"), Queue("realtime")),
    task_routes={
        "guard.*": {"queue": "realtime"},
    },
    result_expires=3600,
    imports=(
        "app.workers.tasks.ingest",
        "app.workers.tasks.banhammer",
        "app.workers.tasks.imports",
        "app.workers.tasks.tools",
        "app.workers.tasks.automations",
    ),
)

from app.workers.schedules import BEAT_SCHEDULE  # noqa: E402

celery_app.conf.beat_schedule = BEAT_SCHEDULE
