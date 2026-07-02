"""Celery worker entrypoint (M15).

Run with:  celery -A app.worker worker --loglevel=info

Importing the Celery app also imports the ingestion task definitions
(via celery_app.py), so they are registered when the worker boots.
"""

from app.infrastructure.celery.celery_app import celery_app

app = celery_app
