"""Unit tests for M2 — Document Ingestion Pipeline.

All external dependencies (repositories, storage, queue) are mocked so
these tests run without Docker services.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.application.document.services import DocumentUseCase
from app.domain.document.constants import (
    DocumentStatus,
    JobStatus,
    MAX_FILE_SIZE_BYTES,
)
from app.domain.document.models import Document, ProcessingJob
from app.presentation.middleware.error_handler import DomainException
from industrial_brain_shared.constants import ErrorCode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mocked_use_case():
    doc_repo = MagicMock()
    storage = MagicMock()
    job_repo = MagicMock()
    queue_svc = MagicMock()
    use_case = DocumentUseCase(doc_repo, storage, job_repo, queue_svc)
    return use_case, doc_repo, storage, job_repo, queue_svc


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# upload_document — validation
# ---------------------------------------------------------------------------


def test_upload_rejects_oversized_file(mocked_use_case):
    use_case, *_ = mocked_use_case
    oversized = b"x" * (MAX_FILE_SIZE_BYTES + 1)
    with pytest.raises(DomainException) as exc_info:
        use_case.upload_document("big.pdf", "application/pdf", oversized, "user1")
    assert exc_info.value.code == ErrorCode.FILE_TOO_LARGE
    assert exc_info.value.status_code == 413


def test_upload_rejects_invalid_mime_type(mocked_use_case):
    use_case, *_ = mocked_use_case
    with pytest.raises(DomainException) as exc_info:
        use_case.upload_document(
            "malware.exe", "application/x-executable", b"data", "user1"
        )
    assert exc_info.value.code == ErrorCode.INVALID_MIME_TYPE


def test_upload_rejects_duplicate_sha256(mocked_use_case):
    use_case, doc_repo, *_ = mocked_use_case
    doc_repo.get_by_sha256.return_value = MagicMock()  # simulate existing document
    with pytest.raises(DomainException) as exc_info:
        use_case.upload_document(
            "dup.pdf", "application/pdf", b"duplicate content", "user1"
        )
    assert exc_info.value.code == ErrorCode.DUPLICATE_FILE


# ---------------------------------------------------------------------------
# upload_document — success path
# ---------------------------------------------------------------------------


def test_upload_success_creates_document_and_job(mocked_use_case):
    use_case, doc_repo, storage, job_repo, queue_svc = mocked_use_case
    doc_repo.get_by_sha256.return_value = None
    doc_repo.create.side_effect = lambda doc: doc
    doc_repo.add_version.side_effect = lambda v: v
    job_repo.create.side_effect = lambda job: job

    doc = use_case.upload_document(
        "report.pdf", "application/pdf", b"pdf content here", "user-42"
    )

    # Document created with correct status
    assert doc.status == DocumentStatus.READY_FOR_PROCESSING
    assert doc.original_filename == "report.pdf"
    assert doc.created_by == "user-42"

    # Version persisted
    doc_repo.add_version.assert_called_once()

    # Job created in QUEUED state
    job_repo.create.assert_called_once()
    created_job: ProcessingJob = job_repo.create.call_args[0][0]
    assert created_job.status == JobStatus.QUEUED
    assert created_job.document_id == doc.id

    # Job enqueued to Redis
    queue_svc.enqueue_ingestion_job.assert_called_once_with(doc.id, created_job.id)


def test_upload_accepts_xlsx(mocked_use_case):
    use_case, doc_repo, storage, job_repo, queue_svc = mocked_use_case
    doc_repo.get_by_sha256.return_value = None
    doc_repo.create.side_effect = lambda d: d
    doc_repo.add_version.side_effect = lambda v: v
    job_repo.create.side_effect = lambda j: j

    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    doc = use_case.upload_document("data.xlsx", xlsx_mime, b"xlsx bytes", "user1")
    assert doc.mime_type == xlsx_mime


def test_upload_accepts_png(mocked_use_case):
    use_case, doc_repo, storage, job_repo, queue_svc = mocked_use_case
    doc_repo.get_by_sha256.return_value = None
    doc_repo.create.side_effect = lambda d: d
    doc_repo.add_version.side_effect = lambda v: v
    job_repo.create.side_effect = lambda j: j

    doc = use_case.upload_document("diagram.png", "image/png", b"png bytes", "user1")
    assert doc.mime_type == "image/png"


def test_upload_stores_to_industrial_documents_bucket(mocked_use_case):
    use_case, doc_repo, storage, job_repo, queue_svc = mocked_use_case
    doc_repo.get_by_sha256.return_value = None
    doc_repo.create.side_effect = lambda d: d
    doc_repo.add_version.side_effect = lambda v: v
    job_repo.create.side_effect = lambda j: j

    use_case.upload_document("file.pdf", "application/pdf", b"content", "u1")

    call_args = storage.upload_file.call_args
    assert call_args[0][0] == "industrial-documents"


# ---------------------------------------------------------------------------
# get_document_status
# ---------------------------------------------------------------------------


def test_get_document_status_returns_queued_job(mocked_use_case):
    use_case, doc_repo, _, job_repo, _ = mocked_use_case
    now = _now()
    mock_doc = Document(
        id="doc-abc",
        original_filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=512,
        sha256_hash="deadbeef",
        status=DocumentStatus.READY_FOR_PROCESSING,
        created_at=now,
        updated_at=now,
        created_by="user1",
    )
    mock_job = ProcessingJob(
        id="job-xyz",
        document_id="doc-abc",
        status=JobStatus.QUEUED,
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    doc_repo.get_by_id.return_value = mock_doc
    doc_repo.get_versions.return_value = []
    doc_repo.get_metadata.return_value = None
    job_repo.get_by_document_id.return_value = mock_job

    job = use_case.get_document_status("doc-abc")
    assert job.status == JobStatus.QUEUED
    assert job.document_id == "doc-abc"


def test_get_document_status_raises_if_no_job(mocked_use_case):
    use_case, doc_repo, _, job_repo, _ = mocked_use_case
    now = _now()
    doc_repo.get_by_id.return_value = Document(
        id="doc-nojob",
        original_filename="x.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        sha256_hash="abc",
        status=DocumentStatus.UPLOADED,
        created_at=now,
        updated_at=now,
        created_by="u1",
    )
    doc_repo.get_versions.return_value = []
    doc_repo.get_metadata.return_value = None
    job_repo.get_by_document_id.return_value = None

    with pytest.raises(DomainException) as exc_info:
        use_case.get_document_status("doc-nojob")
    assert exc_info.value.code == ErrorCode.JOB_NOT_FOUND


# ---------------------------------------------------------------------------
# retry_document
# ---------------------------------------------------------------------------


def test_retry_requeues_failed_document(mocked_use_case):
    use_case, doc_repo, _, job_repo, queue_svc = mocked_use_case
    now = _now()
    doc_repo.get_by_id.return_value = Document(
        id="doc-fail",
        original_filename="f.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        sha256_hash="ff",
        status=DocumentStatus.FAILED,
        created_at=now,
        updated_at=now,
        created_by="u1",
    )
    doc_repo.get_versions.return_value = []
    doc_repo.get_metadata.return_value = None
    job_repo.get_by_document_id.return_value = ProcessingJob(
        id="job-old",
        document_id="doc-fail",
        status=JobStatus.FAILED,
        error_message="OCR timeout",
        created_at=now,
        updated_at=now,
    )
    job_repo.create.side_effect = lambda j: j

    new_job = use_case.retry_document("doc-fail")
    assert new_job.status == JobStatus.QUEUED
    queue_svc.enqueue_ingestion_job.assert_called_once_with("doc-fail", new_job.id)


def test_retry_raises_if_not_failed(mocked_use_case):
    use_case, doc_repo, _, job_repo, _ = mocked_use_case
    now = _now()
    doc_repo.get_by_id.return_value = Document(
        id="doc-ok",
        original_filename="g.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        sha256_hash="gg",
        status=DocumentStatus.READY_FOR_PROCESSING,
        created_at=now,
        updated_at=now,
        created_by="u1",
    )
    doc_repo.get_versions.return_value = []
    doc_repo.get_metadata.return_value = None
    job_repo.get_by_document_id.return_value = ProcessingJob(
        id="job-q",
        document_id="doc-ok",
        status=JobStatus.QUEUED,
        error_message=None,
        created_at=now,
        updated_at=now,
    )

    with pytest.raises(DomainException) as exc_info:
        use_case.retry_document("doc-ok")
    assert exc_info.value.code == ErrorCode.INVALID_STATUS
