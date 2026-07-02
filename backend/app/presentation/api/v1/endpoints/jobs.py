"""Job status polling endpoint (M15, ADR-015).

`GET /api/v1/jobs/{job_id}` returns the current state + progress of an
async ingestion job dispatched by the Celery pipeline. Reuses the
`JobStatusResponse` schema and `JOB_PROGRESS` map already defined for the
document status endpoint — no duplicate schema.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.application.document.services import DocumentUseCase
from app.domain.auth.models import User
from app.domain.document.constants import JOB_PROGRESS
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user
from app.presentation.api.v1.endpoints.document import JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])
logger = logging.getLogger(__name__)


def _get_use_case() -> DocumentUseCase:
    return container.get_document_use_case()


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    use_case: DocumentUseCase = Depends(_get_use_case),
) -> JobStatusResponse:
    job = use_case.get_job_by_id(job_id)
    return JobStatusResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        progress_pct=JOB_PROGRESS.get(job.status, 0),
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
