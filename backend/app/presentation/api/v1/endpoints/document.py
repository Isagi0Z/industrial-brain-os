from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, UploadFile, File, Query
from pydantic import BaseModel
from datetime import datetime

from app.infrastructure.di.container import container
from app.application.document.services import DocumentUseCase
from app.presentation.api.dependencies.auth import get_current_user
from app.domain.auth.models import User
from app.domain.document.constants import DocumentStatus

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_use_case() -> DocumentUseCase:
    return container.get_document_use_case()


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


class PaginatedDocumentResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


@router.post("/", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    file_data = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unknown_file"

    doc = use_case.upload_document(
        filename=filename,
        mime_type=mime_type,
        file_data=file_data,
        user_id=current_user.id,
    )

    # Convert domain model to response model
    doc_dict = doc.__dict__.copy()
    if doc.metadata:
        doc_dict["metadata"] = DocumentMetadataResponse(**doc.metadata.__dict__)
    doc_dict["versions"] = [DocumentVersionResponse(**v.__dict__) for v in doc.versions]

    return DocumentResponse(**doc_dict)


@router.get("/", response_model=PaginatedDocumentResponse)
def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    docs, total = use_case.list_documents(skip, limit, status)

    response_docs = []
    for doc in docs:
        doc_dict = doc.__dict__.copy()
        if doc.metadata:
            doc_dict["metadata"] = DocumentMetadataResponse(**doc.metadata.__dict__)
        doc_dict["versions"] = [
            DocumentVersionResponse(**v.__dict__) for v in doc.versions
        ]
        response_docs.append(DocumentResponse(**doc_dict))

    return PaginatedDocumentResponse(documents=response_docs, total=total)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    use_case: DocumentUseCase = Depends(get_document_use_case),
    current_user: User = Depends(get_current_user),
):
    doc = use_case.get_document(document_id)
    doc_dict = doc.__dict__.copy()
    if doc.metadata:
        doc_dict["metadata"] = DocumentMetadataResponse(**doc.metadata.__dict__)
    doc_dict["versions"] = [DocumentVersionResponse(**v.__dict__) for v in doc.versions]
    return DocumentResponse(**doc_dict)


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
    updated_meta = use_case.update_metadata(document_id, metadata)
    return DocumentMetadataResponse(**updated_meta.__dict__)
