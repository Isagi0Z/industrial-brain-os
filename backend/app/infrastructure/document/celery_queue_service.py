"""Celery-backed ingestion queue (M15, ADR-015).

Dispatches the async ingestion task chain (parse → embed → kg) instead of
pushing a payload onto a Redis list for the legacy in-process worker.
Implements the same ``IQueueService`` port as ``RedisQueueService``, so
``DocumentUseCase`` — and its tests — are unchanged; only the wiring in the
DI container differs.

The Correlation-ID from the originating upload request (a contextvar set by
the logging middleware) is captured here and carried in the task payload so
every worker-side log line joins the same trace (Engineering Bible §16).
"""

from __future__ import annotations

import logging

from celery import chain

from app.domain.document.interfaces import IQueueService
from app.infrastructure.celery.tasks import embed_task, kg_task, parse_task
from app.infrastructure.logging.logger import correlation_id_ctx

logger = logging.getLogger(__name__)


class CeleryQueueService(IQueueService):
    def enqueue_ingestion_job(self, document_id: str, job_id: str) -> None:
        payload = {
            "document_id": document_id,
            "job_id": job_id,
            "correlation_id": correlation_id_ctx.get(),
        }
        chain(parse_task.s(payload), embed_task.s(), kg_task.s()).apply_async()
        logger.info(
            "Dispatched Celery ingestion chain",
            extra={"document_id": document_id, "job_id": job_id},
        )
