from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.domain.document.constants import DocumentStatus


@dataclass
class StorageObject:
    bucket_name: str
    object_name: str
    size_bytes: int
    content_type: str


@dataclass
class DocumentVersion:
    id: str
    document_id: str
    version_number: int
    storage_path: str
    size_bytes: int
    created_at: datetime
    created_by: str


@dataclass
class DocumentMetadata:
    id: str
    document_id: str
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class DocumentClassification:
    id: str
    document_id: str
    category: str
    confidence: float
    created_at: datetime


@dataclass
class Document:
    id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256_hash: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
    is_deleted: bool = False
    
    # Navigation properties
    versions: List[DocumentVersion] = field(default_factory=list)
    metadata: Optional[DocumentMetadata] = None
    classifications: List[DocumentClassification] = field(default_factory=list)
