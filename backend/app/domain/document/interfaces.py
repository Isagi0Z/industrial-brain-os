from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, Dict
from app.domain.document.models import (
    Document,
    DocumentVersion,
    DocumentMetadata,
    ProcessingJob,
    DocumentChunk,
)
from app.domain.document.constants import DocumentStatus, JobStatus


class IDocumentRepository(ABC):
    @abstractmethod
    def create(self, document: Document) -> Document:
        pass

    @abstractmethod
    def get_by_id(self, document_id: str) -> Optional[Document]:
        pass

    @abstractmethod
    def get_by_sha256(self, sha256_hash: str) -> Optional[Document]:
        pass

    @abstractmethod
    def update_status(self, document_id: str, status: DocumentStatus) -> None:
        pass

    @abstractmethod
    def soft_delete(self, document_id: str) -> None:
        pass

    @abstractmethod
    def restore(self, document_id: str) -> None:
        pass

    @abstractmethod
    def list_documents(
        self,
        skip: int = 0,
        limit: int = 50,
        status: Optional[DocumentStatus] = None,
        include_deleted: bool = False,
    ) -> Tuple[List[Document], int]:
        """Returns (documents, total_count)."""
        pass

    @abstractmethod
    def add_version(self, version: DocumentVersion) -> DocumentVersion:
        pass

    @abstractmethod
    def get_versions(self, document_id: str) -> List[DocumentVersion]:
        pass

    @abstractmethod
    def upsert_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        pass

    @abstractmethod
    def get_metadata(self, document_id: str) -> Optional[DocumentMetadata]:
        pass


class IStorageService(ABC):
    @abstractmethod
    def get_presigned_upload_url(
        self, bucket_name: str, object_name: str, expires_in_sec: int = 3600
    ) -> str:
        pass

    @abstractmethod
    def get_presigned_download_url(
        self, bucket_name: str, object_name: str, expires_in_sec: int = 3600
    ) -> str:
        pass

    @abstractmethod
    def upload_file(
        self, bucket_name: str, object_name: str, file_data: bytes, content_type: str
    ) -> None:
        pass

    @abstractmethod
    def download_file(self, bucket_name: str, object_name: str) -> bytes:
        pass

    @abstractmethod
    def delete_file(self, bucket_name: str, object_name: str) -> None:
        pass

    @abstractmethod
    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        pass


class IJobRepository(ABC):
    """Persistence interface for document processing jobs."""

    @abstractmethod
    def create(self, job: ProcessingJob) -> ProcessingJob:
        pass

    @abstractmethod
    def get_by_document_id(self, document_id: str) -> Optional[ProcessingJob]:
        """Returns the most recent job for a document."""
        pass

    @abstractmethod
    def get_by_id(self, job_id: str) -> Optional[ProcessingJob]:
        """Returns a single job by its id, or None (M15 — /jobs/{job_id})."""
        pass

    @abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> None:
        pass

    @abstractmethod
    def get_latest_statuses(self, document_ids: List[str]) -> Dict[str, JobStatus]:
        """Batch-fetch the latest job status per document. Avoids N+1 queries."""
        pass


class IQueueService(ABC):
    """Abstraction over the message queue used to trigger background processing."""

    @abstractmethod
    def enqueue_ingestion_job(self, document_id: str, job_id: str) -> None:
        """Push a job payload onto the ingestion queue."""
        pass


class IChunkRepository(ABC):
    """Persistence interface for document chunks (M3)."""

    @abstractmethod
    def bulk_insert(self, chunks: List[DocumentChunk]) -> None:
        """Insert all chunks for a document in a single transaction."""
        pass

    @abstractmethod
    def get_by_document_id(self, document_id: str) -> List[DocumentChunk]:
        pass

    @abstractmethod
    def delete_by_document_id(self, document_id: str) -> None:
        """Remove all chunks for a document (used on retry)."""
        pass


class IDocumentParser(ABC):
    """Extracts structured chunks from raw file bytes (M3)."""

    @abstractmethod
    def can_parse(self, mime_type: str) -> bool:
        pass

    @abstractmethod
    def parse(
        self,
        document_id: str,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
    ) -> List[DocumentChunk]:
        """Return a flat ordered list of DocumentChunk objects."""
        pass
