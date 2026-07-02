"""Celery ingestion tasks (M15, ADR-015) — the async replacement for the
in-process ``IngestionWorker``.

Each task **reuses the existing use case** for its stage (no
reimplementation of M2/M3/M4/M7 logic):

    parse_task → DocumentParsingUseCase.parse_document  (M2 PyMuPDF extract
                 + M3 layout parse / OCR / chunk — unified in one use case
                 in this codebase, so the "extract" and "parse" stages of
                 the roadmap are a single Celery task here)
    embed_task → EmbeddingUseCase.embed_document         (M4 embed + Qdrant)
    kg_task    → ExtractionUseCase.run_for_document        (M7 NER + relations
                 + Neo4j population)

The chain (`parse_task → embed_task → kg_task`) is dispatched by
``CeleryQueueService``. Each task:
  - restores the Correlation-ID propagated from the upload request so its
    logs join the same trace (Engineering Bible §16),
  - marks the job in-progress at start (the use case sets the completion
    status),
  - forwards the payload dict to the next task in the chain,
  - retries up to 3× with exponential backoff (60 → 120 → 240 s, Engineering
    Bible §23), and on final failure sets ``jobs.status = FAILED`` with
    ``error_details {task, message}``.

No state is held in worker memory — all state lives in PostgreSQL / Redis
(Engineering Bible §28); the payload carries only ids.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from app.domain.document.constants import JobStatus
from app.infrastructure.celery.celery_app import celery_app
from app.infrastructure.di.container import container
from app.infrastructure.logging.logger import correlation_id_ctx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE_SEC = 60  # 60 → 120 → 240


def _restore_correlation(payload: Dict[str, Any]) -> None:
    correlation_id_ctx.set(payload.get("correlation_id", "-"))


def _handle_failure(task, task_name: str, job_id: str, exc: Exception) -> None:
    """Retry with exponential backoff; on the final attempt mark the job
    FAILED with structured error_details and re-raise."""
    retries = task.request.retries
    if retries < _MAX_RETRIES:
        countdown = _BACKOFF_BASE_SEC * (2**retries)
        logger.warning(
            "Ingestion task failed — retrying",
            extra={
                "task": task_name,
                "job_id": job_id,
                "attempt": retries + 1,
                "retry_in_sec": countdown,
                "error": str(exc),
            },
        )
        raise task.retry(exc=exc, countdown=countdown, max_retries=_MAX_RETRIES)

    logger.error(
        "Ingestion task exhausted retries — marking job FAILED",
        extra={"task": task_name, "job_id": job_id, "error": str(exc)},
    )
    container.get_job_repository().update_status(
        job_id, JobStatus.FAILED, error_message=f"[{task_name}] {exc}"
    )
    raise exc


@celery_app.task(bind=True, name="ingestion.parse", max_retries=_MAX_RETRIES)
def parse_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    _restore_correlation(payload)
    document_id, job_id = payload["document_id"], payload["job_id"]
    try:
        container.get_job_repository().update_status(job_id, JobStatus.EXTRACTING)
        logger.info(
            "parse_task started",
            extra={"task": "parse_task", "document_id": document_id, "job_id": job_id},
        )
        chunks = container.get_parsing_use_case().parse_document(document_id, job_id)
        payload["chunk_count"] = len(chunks) if chunks else 0
        return payload
    except Exception as exc:  # noqa: BLE001 — retried/handled by _handle_failure
        _handle_failure(self, "parse_task", job_id, exc)
        return payload  # unreachable (helper re-raises); keeps type-checkers happy


@celery_app.task(bind=True, name="ingestion.embed", max_retries=_MAX_RETRIES)
def embed_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    _restore_correlation(payload)
    document_id, job_id = payload["document_id"], payload["job_id"]
    if not payload.get("chunk_count"):
        logger.info(
            "embed_task skipped — no chunks produced",
            extra={"task": "embed_task", "job_id": job_id},
        )
        return payload
    try:
        container.get_job_repository().update_status(job_id, JobStatus.EMBEDDING)
        container.get_embedding_use_case().embed_document(document_id, job_id)
        return payload
    except Exception as exc:  # noqa: BLE001
        _handle_failure(self, "embed_task", job_id, exc)
        return payload


@celery_app.task(bind=True, name="ingestion.kg", max_retries=_MAX_RETRIES)
def kg_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    _restore_correlation(payload)
    document_id, job_id = payload["document_id"], payload["job_id"]
    if not payload.get("chunk_count"):
        return payload
    try:
        container.get_job_repository().update_status(job_id, JobStatus.KG_EXTRACTING)
        asyncio.run(
            container.get_extraction_use_case().run_for_document(document_id, job_id)
        )
        return payload
    except Exception as exc:  # noqa: BLE001
        _handle_failure(self, "kg_task", job_id, exc)
        return payload
