"""
Celery application configuration with Beat schedule.
Per architecture.md §2.2: scan every 5min, integrity every 2min, monitor every 1min.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "drive_vimeo_sync",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "worker.tasks.scanner",
        "worker.tasks.integrity",
        "worker.tasks.uploader",
        "worker.tasks.monitor",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    worker_concurrency=settings.celery_concurrency,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Beat schedule — periodic tasks
celery_app.conf.beat_schedule = {
    "scanner": {
        "task": "tasks.scan_drive",
        "schedule": crontab(minute=f"*/{settings.scanner_interval_minutes}"),
    },
    "integrity_check": {
        "task": "tasks.check_integrity",
        "schedule": crontab(minute=f"*/{settings.integrity_check_interval_minutes}"),
    },
    "vimeo_monitor": {
        "task": "tasks.monitor_vimeo",
        "schedule": crontab(minute=f"*/{settings.vimeo_monitor_interval_minutes}"),
    },
}
