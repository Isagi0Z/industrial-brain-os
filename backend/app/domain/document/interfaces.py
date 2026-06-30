from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from app.domain.document.models import Document, DocumentVersion, DocumentMetadata
from app.domain.document.constants import DocumentStatus


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
        """Returns a tuple of (documents, total_count)"""
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
    def delete_file(self, bucket_name: str, object_name: str) -> None:
        pass

    @abstractmethod
    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        pass
