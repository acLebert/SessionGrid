"""SessionGrid — Celery Application Configuration"""

from celery import Celery
from config import get_settings

settings = get_settings()

celery_app = Celery(
    "sessiongrid",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # One task at a time (heavy processing)
    task_soft_time_limit=600,      # 10 minute soft limit
    task_time_limit=900,           # 15 minute hard limit
    result_expires=86400,          # Results expire after 24 hours
)
