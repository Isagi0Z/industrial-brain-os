from enum import Enum


class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"
    VALIDATED = "VALIDATED"
    READY_FOR_PROCESSING = "READY_FOR_PROCESSING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    PARSING = "PARSING"
    CHUNKED = "CHUNKED"
    EMBEDDING = "EMBEDDING"
    INDEXED = "INDEXED"
    KG_EXTRACTING = "KG_EXTRACTING"
    KG_POPULATED = "KG_POPULATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChunkType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    FOOTER = "footer"
    LIST_ITEM = "list_item"


# Canonical MIME types accepted at the upload boundary. Uploads are resolved to
# one of these (extension + content sniff) before validation, so heterogeneous
# industrial documents (CSV, Markdown, JSON, PPTX, email, ZIP, more image types)
# are all accepted. See app.domain.document.mime and the parser registry.
ALLOWED_MIME_TYPES: frozenset = frozenset(
    {
        # documents
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        # text / structured
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/tab-separated-values",
        "application/json",
        "application/xml",
        "text/xml",
        "text/html",
        "application/x-yaml",
        # images
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/bmp",
        "image/tiff",
        "image/webp",
        # email
        "message/rfc822",
        "application/vnd.ms-outlook",
        # archive
        "application/zip",
    }
)

MAX_FILE_SIZE_BYTES: int = 100 * 1024 * 1024  # 100 MB

# Progress percentages by job status (for the /status endpoint)
JOB_PROGRESS: dict = {
    JobStatus.QUEUED: 5,
    JobStatus.EXTRACTING: 20,
    JobStatus.EXTRACTED: 40,
    JobStatus.PARSING: 55,
    JobStatus.CHUNKED: 70,
    JobStatus.EMBEDDING: 85,
    JobStatus.INDEXED: 90,
    JobStatus.KG_EXTRACTING: 93,
    JobStatus.KG_POPULATED: 97,
    JobStatus.COMPLETED: 100,
    JobStatus.FAILED: 0,
}

# Chunking parameters (ADR-012)
CHUNK_SOFT_MAX_TOKENS: int = 512
CHUNK_HARD_MAX_TOKENS: int = 768
CHUNK_OVERLAP_TOKENS: int = 64
LAYOUT_CONFIDENCE_THRESHOLD: float = 0.75
