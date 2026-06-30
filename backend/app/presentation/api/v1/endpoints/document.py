from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, Query
from pydantic import BaseModel

from app.infrastructure.di.container import container
from app.application.document.services import DocumentUseCase
from app.presentation.api.dependencies.auth import get_current_user
from app.domain.auth.models import User
from app.domain.document.constants import (
    DocumentStatus,
    JobStatus,
    JOB_PROGRESS,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_use_case() -> DocumentUseCase:
    return container.get_document_use_case()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DocumentVersionResponse(BaseModel):
    id: str
    version_number: int
    size_bytes: int
    created_at: datetime
    created_by: str


class DocumentMetadataResponse(BaseModel):
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256_hash: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
    is_deleted: bool
    versions: List[DocumentVersionResponse] = []
    metadata: Optional[DocumentMetadataResponse] = None
    job_status: Optional[JobStatus] = None


class PaginatedDocumentResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


class JobStatusResponse(BaseModel):
    job_id: str
    document_id: str
    status: JobStatus
    progress_pct: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_document_response(
    doc, job_status: Optional[JobStatus] = None
) -> DocumentResponse:
    doc_dict = doc.__dict__.copy()
    if doc.metadata:
        doc_dict["metadata"] = DocumentMetadataResponse(**doc.metadata.__dict__)
    doc_dict["versions"] = [DocumentVersionResponse(**v.__dict__) for v in doc.versions]
    doc_dict["job_status"] = job_status
    doc_dict.pop("classifications", None)
    return DocumentResponse(**doc_dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    """Upload a document. Accepted formats: PDF, DOCX, XLSX, PNG, JPEG (max 100 MB)."""
    file_data = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unknown_file"

    doc = use_case.upload_document(
        filename=filename,
        mime_type=mime_type,
        file_data=file_data,
        user_id=current_user.id,
    )
    return _build_document_response(doc, job_status=JobStatus.QUEUED)


@router.get("/", response_model=PaginatedDocumentResponse)
def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    """List documents with their latest processing job status."""
    pairs, total = use_case.list_documents_with_job_status(skip, limit, status)
    response_docs = [_build_document_response(doc, js) for doc, js in pairs]
    return PaginatedDocumentResponse(documents=response_docs, total=total)


@router.get("/{document_id}/status", response_model=JobStatusResponse)
def get_document_status(
    document_id: str,
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    """Return the current processing job status for a document."""
    job = use_case.get_document_status(document_id)
    return JobStatusResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        progress_pct=JOB_PROGRESS.get(job.status, 0),
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/{document_id}/retry", response_model=JobStatusResponse)
def retry_document(
    document_id: str,
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    """Re-queue a failed document for processing."""
    job = use_case.retry_document(document_id)
    return JobStatusResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        progress_pct=JOB_PROGRESS.get(job.status, 0),
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    doc = use_case.get_document(document_id)
    job = use_case.job_repo.get_by_document_id(document_id)
    job_status = job.status if job else None
    return _build_document_response(doc, job_status)


@router.get("/{document_id}/download")
def get_download_url(
    document_id: str,
    version: Optional[int] = Query(None),
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    url = use_case.get_presigned_download_url(document_id, version)
    return {"download_url": url}


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    use_case.soft_delete_document(document_id)
    return {"status": "deleted"}


@router.get("/{document_id}/chunks")
def list_chunks(
    document_id: str,
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    """Return all parsed chunks for a document (available after M3 processing)."""
    use_case.get_document(document_id)  # 404 if not found
    chunks = container.get_chunk_repository().get_by_document_id(document_id)
    return {
        "document_id": document_id,
        "total_chunks": len(chunks),
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "chunk_type": c.chunk_type.value,
                "text": c.text[:500],
                "page_number": c.page_number,
                "parent_section_header": c.parent_section_header,
                "token_count": c.token_count,
                "has_table_data": c.table_data_json is not None,
                "has_figure": c.figure_storage_key is not None,
                "bbox": c.bbox_json,
            }
            for c in chunks
        ],
    }


@router.post("/{document_id}/restore")
def restore_document(
    document_id: str,
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    use_case.restore_document(document_id)
    return {"status": "restored"}


@router.put("/{document_id}/metadata", response_model=DocumentMetadataResponse)
def update_metadata(
    document_id: str,
    metadata: dict,
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    updated = use_case.update_metadata(document_id, metadata)
    return DocumentMetadataResponse(**updated.__dict__)
