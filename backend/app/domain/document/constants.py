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
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# MIME types accepted at the upload boundary (M2 scope: PDF, DOCX, XLSX, PNG, JPG)
ALLOWED_MIME_TYPES: frozenset = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "image/png",
    }
)

MAX_FILE_SIZE_BYTES: int = 100 * 1024 * 1024  # 100 MB

# Progress percentages by job status (for the /status endpoint)
JOB_PROGRESS: dict = {
    JobStatus.QUEUED: 10,
    JobStatus.PROCESSING: 50,
    JobStatus.COMPLETED: 100,
    JobStatus.FAILED: 0,
}
