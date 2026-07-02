"""Celery application — event-driven ingestion (M15, ADR-015).

Broker and result backend are Redis (separate logical DBs from the app's
cache/session use, configurable via settings). Tasks live in
``app.infrastructure.celery.tasks`` and are imported at the bottom so the
worker (``celery -A app.worker worker``) registers them.
"""

from __future__ import annotations

from celery import Celery

from app.infrastructure.config.settings import settings

celery_app = Celery(
    "industrial_brain",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,  # re-deliver if a worker dies mid-task
    worker_prefetch_multiplier=1,
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    task_default_queue="ingestion",
    broker_connection_retry_on_startup=True,
)

# Register task definitions with the app.
from app.infrastructure.celery import tasks  # noqa: E402,F401
