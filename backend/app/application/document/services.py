import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from app.domain.document.interfaces import IDocumentRepository, IStorageService
from app.domain.document.models import Document, DocumentVersion, DocumentMetadata
from app.domain.document.constants import DocumentStatus, ALLOWED_MIME_TYPES, MAX_FILE_SIZE_BYTES
from app.presentation.middleware.error_handler import DomainException

class DocumentUseCase:
    def __init__(self, document_repo: IDocumentRepository, storage_service: IStorageService):
        self.document_repo = document_repo
        self.storage_service = storage_service
        self.bucket_name = "documents"

    def upload_document(self, filename: str, mime_type: str, file_data: bytes, user_id: str) -> Document:
        # Validate Size
        size_bytes = len(file_data)
        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise DomainException("FILE_TOO_LARGE", f"File size exceeds limit of {MAX_FILE_SIZE_BYTES} bytes")
        
        # Validate MIME
        if mime_type not in ALLOWED_MIME_TYPES:
            raise DomainException("INVALID_MIME_TYPE", f"MIME type {mime_type} is not allowed")

        # Duplicate detection (SHA-256)
        sha256_hash = hashlib.sha256(file_data).hexdigest()
        existing_doc = self.document_repo.get_by_sha256(sha256_hash)
        if existing_doc:
            raise DomainException("DUPLICATE_FILE", "A document with the same content already exists")

        # Create Document Record
        now = datetime.now(timezone.utc)
        document_id = str(uuid.uuid4())
        
        document = Document(
            id=document_id,
            original_filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256_hash=sha256_hash,
            status=DocumentStatus.UPLOADED,
            created_at=now,
            updated_at=now,
            created_by=user_id,
        )

        self.document_repo.create(document)

        # Upload to MinIO
        version_number = 1
        storage_path = f"{document_id}/v{version_number}/{filename}"
        self.storage_service.upload_file(self.bucket_name, storage_path, file_data, mime_type)

        # Create Version Record
        version_id = str(uuid.uuid4())
        version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=version_number,
            storage_path=storage_path,
            size_bytes=size_bytes,
            created_at=now,
            created_by=user_id
        )
        self.document_repo.add_version(version)

        # Update status
        self.document_repo.update_status(document_id, DocumentStatus.VALIDATED)
        document.status = DocumentStatus.VALIDATED
        
        # Load versions
        document.versions = [version]

        return document

    def get_document(self, document_id: str) -> Document:
        document = self.document_repo.get_by_id(document_id)
        if not document:
            raise DomainException("DOCUMENT_NOT_FOUND", "Document not found")
        
        document.versions = self.document_repo.get_versions(document_id)
        document.metadata = self.document_repo.get_metadata(document_id)
        return document

    def soft_delete_document(self, document_id: str) -> None:
        doc = self.get_document(document_id)
        if doc.is_deleted:
            return
        self.document_repo.soft_delete(document_id)

    def restore_document(self, document_id: str) -> None:
        doc = self.document_repo.get_by_id(document_id)
        if not doc:
            raise DomainException("DOCUMENT_NOT_FOUND", "Document not found")
        if not doc.is_deleted:
            return
        self.document_repo.restore(document_id)

    def update_metadata(self, document_id: str, metadata_dict: dict) -> DocumentMetadata:
        doc = self.get_document(document_id)
        now = datetime.now(timezone.utc)
        
        existing = self.document_repo.get_metadata(document_id)
        if existing:
            existing.metadata = metadata_dict
            existing.updated_at = now
            return self.document_repo.upsert_metadata(existing)
        else:
            new_metadata = DocumentMetadata(
                id=str(uuid.uuid4()),
                document_id=document_id,
                metadata=metadata_dict,
                created_at=now,
                updated_at=now
            )
            return self.document_repo.upsert_metadata(new_metadata)

    def get_presigned_download_url(self, document_id: str, version_number: Optional[int] = None) -> str:
        doc = self.get_document(document_id)
        versions = doc.versions
        if not versions:
            raise DomainException("NO_VERSIONS", "Document has no versions")
        
        target_version = versions[0]
        if version_number is not None:
            for v in versions:
                if v.version_number == version_number:
                    target_version = v
                    break
            else:
                raise DomainException("VERSION_NOT_FOUND", f"Version {version_number} not found")

        return self.storage_service.get_presigned_download_url(self.bucket_name, target_version.storage_path)

    def list_documents(self, skip: int = 0, limit: int = 50, status: Optional[str] = None) -> Tuple[List[Document], int]:
        doc_status = None
        if status:
            try:
                doc_status = DocumentStatus(status)
            except ValueError:
                raise DomainException("INVALID_STATUS", f"Invalid status: {status}")
        
        return self.document_repo.list_documents(skip, limit, doc_status, include_deleted=False)
