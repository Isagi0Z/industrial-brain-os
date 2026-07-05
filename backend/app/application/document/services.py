import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict

from app.domain.document.interfaces import (
    IDocumentRepository,
    IStorageService,
    IJobRepository,
    IQueueService,
)
from app.domain.document.models import (
    Document,
    DocumentVersion,
    DocumentMetadata,
    ProcessingJob,
)
from app.domain.document.constants import (
    DocumentStatus,
    JobStatus,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
)
from app.domain.document.mime import resolve_mime
from app.presentation.middleware.error_handler import DomainException
from industrial_brain_shared.constants import ErrorCode


class DocumentUseCase:
    """Orchestrates all document-related use cases."""

    def __init__(
        self,
        document_repo: IDocumentRepository,
        storage_service: IStorageService,
        job_repo: IJobRepository,
        queue_service: IQueueService,
    ):
        self.document_repo = document_repo
        self.storage_service = storage_service
        self.job_repo = job_repo
        self.queue_service = queue_service

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_document(
        self, filename: str, mime_type: str, file_data: bytes, user_id: str
    ) -> Document:
        """Validate, store, and queue a new document for processing."""
        size_bytes = len(file_data)
        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise DomainException(
                ErrorCode.FILE_TOO_LARGE,
                f"File size {size_bytes} exceeds maximum of {MAX_FILE_SIZE_BYTES} bytes.",
                status_code=413,
            )

        # Resolve the real type from extension + content: browsers send a generic
        # or wrong content-type for many industrial formats (CSV, Markdown, ...).
        canonical_mime = resolve_mime(mime_type, filename, file_data[:64])
        if canonical_mime not in ALLOWED_MIME_TYPES:
            raise DomainException(
                ErrorCode.INVALID_MIME_TYPE,
                f"File type '{canonical_mime}' (from '{filename}') is not accepted. "
                f"Supported: PDF, DOCX, XLSX, PPTX, CSV/TSV, TXT, Markdown, JSON, XML, "
                f"HTML, images (PNG/JPG/GIF/BMP/TIFF/WEBP), email (EML/MSG), ZIP.",
            )

        sha256_hash = hashlib.sha256(file_data).hexdigest()
        if self.document_repo.get_by_sha256(sha256_hash):
            raise DomainException(
                ErrorCode.DUPLICATE_FILE,
                "A document with identical content already exists.",
            )

        now = datetime.now(timezone.utc)
        document_id = str(uuid.uuid4())

        document = Document(
            id=document_id,
            original_filename=filename,
            mime_type=canonical_mime,
            size_bytes=size_bytes,
            sha256_hash=sha256_hash,
            status=DocumentStatus.UPLOADED,
            created_at=now,
            updated_at=now,
            created_by=user_id,
        )
        self.document_repo.create(document)

        storage_key = f"{document_id}/v1/{filename}"
        self.storage_service.upload_file(
            "industrial-documents", storage_key, file_data, canonical_mime
        )

        version = DocumentVersion(
            id=str(uuid.uuid4()),
            document_id=document_id,
            version_number=1,
            storage_path=storage_key,
            size_bytes=size_bytes,
            created_at=now,
            created_by=user_id,
        )
        self.document_repo.add_version(version)

        job = ProcessingJob(
            id=str(uuid.uuid4()),
            document_id=document_id,
            status=JobStatus.QUEUED,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.job_repo.create(job)
        self.queue_service.enqueue_ingestion_job(document_id, job.id)

        self.document_repo.update_status(
            document_id, DocumentStatus.READY_FOR_PROCESSING
        )
        document.status = DocumentStatus.READY_FOR_PROCESSING
        document.versions = [version]

        return document

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_document(self, document_id: str) -> Document:
        document = self.document_repo.get_by_id(document_id)
        if not document:
            raise DomainException(
                ErrorCode.DOCUMENT_NOT_FOUND,
                "Document not found.",
                status_code=404,
            )
        document.versions = self.document_repo.get_versions(document_id)
        document.metadata = self.document_repo.get_metadata(document_id)
        return document

    def get_document_status(self, document_id: str) -> ProcessingJob:
        self.get_document(document_id)  # validates existence
        job = self.job_repo.get_by_document_id(document_id)
        if not job:
            raise DomainException(
                ErrorCode.JOB_NOT_FOUND,
                "No processing job found for this document.",
                status_code=404,
            )
        return job

    def get_job_by_id(self, job_id: str) -> ProcessingJob:
        """Look up a single processing job by its id (M15 — /jobs/{job_id})."""
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise DomainException(
                ErrorCode.JOB_NOT_FOUND,
                "Job not found.",
                status_code=404,
            )
        return job

    def list_documents(
        self, skip: int = 0, limit: int = 50, status: Optional[str] = None
    ) -> Tuple[List[Document], int]:
        doc_status = None
        if status:
            try:
                doc_status = DocumentStatus(status)
            except ValueError:
                raise DomainException(
                    ErrorCode.INVALID_STATUS, f"Invalid status value: '{status}'"
                )
        return self.document_repo.list_documents(
            skip, limit, doc_status, include_deleted=False
        )

    def list_documents_with_job_status(
        self, skip: int = 0, limit: int = 50, status: Optional[str] = None
    ) -> Tuple[List[Tuple[Document, Optional[JobStatus]]], int]:
        """Returns documents annotated with their latest job status (batch-fetched)."""
        docs, total = self.list_documents(skip, limit, status)
        doc_ids = [d.id for d in docs]
        job_statuses: Dict[str, JobStatus] = (
            self.job_repo.get_latest_statuses(doc_ids) if doc_ids else {}
        )
        return [(doc, job_statuses.get(doc.id)) for doc in docs], total

    # ------------------------------------------------------------------
    # Delete / Restore
    # ------------------------------------------------------------------

    def soft_delete_document(self, document_id: str) -> None:
        doc = self.get_document(document_id)
        if not doc.is_deleted:
            self.document_repo.soft_delete(document_id)

    def restore_document(self, document_id: str) -> None:
        doc = self.document_repo.get_by_id(document_id)
        if not doc:
            raise DomainException(
                ErrorCode.DOCUMENT_NOT_FOUND, "Document not found.", status_code=404
            )
        if doc.is_deleted:
            self.document_repo.restore(document_id)

    # ------------------------------------------------------------------
    # Retry
    # ------------------------------------------------------------------

    def retry_document(self, document_id: str) -> ProcessingJob:
        """Re-queue a failed document for processing."""
        self.get_document(document_id)  # validates existence
        latest_job = self.job_repo.get_by_document_id(document_id)
        if not latest_job or latest_job.status != JobStatus.FAILED:
            raise DomainException(
                ErrorCode.INVALID_STATUS,
                "Document job must be in FAILED state to retry.",
            )

        now = datetime.now(timezone.utc)
        new_job = ProcessingJob(
            id=str(uuid.uuid4()),
            document_id=document_id,
            status=JobStatus.QUEUED,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.job_repo.create(new_job)
        self.queue_service.enqueue_ingestion_job(document_id, new_job.id)
        self.document_repo.update_status(
            document_id, DocumentStatus.READY_FOR_PROCESSING
        )
        return new_job

    # ------------------------------------------------------------------
    # Metadata & Download
    # ------------------------------------------------------------------

    def update_metadata(
        self, document_id: str, metadata_dict: dict
    ) -> DocumentMetadata:
        self.get_document(document_id)
        now = datetime.now(timezone.utc)
        existing = self.document_repo.get_metadata(document_id)
        if existing:
            existing.metadata = metadata_dict
            existing.updated_at = now
            return self.document_repo.upsert_metadata(existing)
        new_meta = DocumentMetadata(
            id=str(uuid.uuid4()),
            document_id=document_id,
            metadata=metadata_dict,
            created_at=now,
            updated_at=now,
        )
        return self.document_repo.upsert_metadata(new_meta)

    def get_presigned_download_url(
        self, document_id: str, version_number: Optional[int] = None
    ) -> str:
        doc = self.get_document(document_id)
        versions = doc.versions
        if not versions:
            raise DomainException(
                ErrorCode.NO_VERSIONS,
                "Document has no stored versions.",
                status_code=404,
            )

        target = versions[0]
        if version_number is not None:
            for v in versions:
                if v.version_number == version_number:
                    target = v
                    break
            else:
                raise DomainException(
                    ErrorCode.VERSION_NOT_FOUND,
                    f"Version {version_number} not found.",
                    status_code=404,
                )

        return self.storage_service.get_presigned_download_url(
            "industrial-documents", target.storage_path
        )
