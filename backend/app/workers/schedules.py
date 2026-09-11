"""Celery beat schedule — the heartbeat of every background pillar."""

from celery.schedules import crontab

from app.core.config import settings

BEAT_SCHEDULE = {
    # Pillar 2 — Lifetime Stream Logger: fan out one task per active user.
    "ingest.recently_played.fanout": {
        "task": "ingest.recently_played.fanout",
        "schedule": float(settings.recently_played_poll_seconds),
    },
    # Catalogue back-fill (artist genres, imported track hydration).
    "catalog.hydrate": {"task": "catalog.hydrate", "schedule": 120.0},
    # Pillar 3 — Skip guard roster refresh (who is playing → who gets polled).
    "guard.refresh_roster": {"task": "guard.refresh_roster", "schedule": 30.0},
    # Milestones after ingest.
    "analytics.milestones.fanout": {"task": "analytics.milestones.fanout", "schedule": 900.0},
    # Pillar 4 — User automations (cron expressions evaluated every minute).
    "automations.tick": {"task": "automations.tick", "schedule": crontab(minute="*")},
}
