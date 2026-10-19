from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "chess_master",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # one task at a time (CPU-bound Stockfish)
    task_publish_retry=False,
    broker_connection_timeout=5,
    broker_transport_options={
        "socket_connect_timeout": 5,
        "socket_timeout": 5,
        "retry_on_timeout": False,
    },
)

# Auto-discover tasks in app.tasks package
celery_app.autodiscover_tasks(["app.tasks"])

# Explicitly import task modules so Celery registers them (autodiscover
# looks for tasks.py, but we use app.tasks.analysis)
from app.tasks import analysis  # noqa: F401
