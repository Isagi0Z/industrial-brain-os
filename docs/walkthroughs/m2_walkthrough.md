# M2 Walkthrough — Document Ingestion Pipeline

**Milestone**: M2  
**Phase**: MVP  
**Completed**: 2026-06-30  
**Depends on**: M1

---

## What Was Built

M2 wires the document upload flow end-to-end: a user uploads a file through the React frontend (or REST API), the backend validates and stores it in MinIO, creates a PostgreSQL document record, creates a `ProcessingJob` in QUEUED state, and pushes a payload onto the Redis `ingestion:jobs` queue for downstream workers (M3+).

---

## Architecture Overview

```
Frontend (React)
  └── POST /api/v1/documents/  [multipart/form-data]
        │
        ▼
  Presentation Layer (FastAPI endpoint)
  └── validates auth token, reads UploadFile bytes
        │
        ▼
  Application Layer (DocumentUseCase.upload_document)
  ├── validate size ≤ 100 MB
  ├── validate MIME type (PDF / DOCX / XLSX / PNG / JPEG)
  ├── SHA-256 duplicate detection
  ├── persist Document → PostgreSQL
  ├── upload binary → MinIO "industrial-documents" bucket
  ├── persist DocumentVersion → PostgreSQL
  ├── create ProcessingJob (status=QUEUED) → PostgreSQL
  ├── enqueue job payload → Redis "ingestion:jobs" list
  └── update document status → READY_FOR_PROCESSING
```

---

## File-by-File Walkthrough

### Backend

#### `shared/python/industrial_brain_shared/constants.py`
Extended `ErrorCode` with document-specific codes: `DOCUMENT_NOT_FOUND`, `DUPLICATE_FILE`, `FILE_TOO_LARGE`, `INVALID_MIME_TYPE`, `INVALID_STATUS`, `JOB_NOT_FOUND`, `NO_VERSIONS`, `VERSION_NOT_FOUND`.

#### `backend/app/presentation/middleware/error_handler.py`
Fixed a pre-existing bug where `exc.code.value` would `AttributeError` when `code` was a raw string. Replaced with `_code_str()` helper that safely handles both `ErrorCode` enum members and raw strings. Also migrated all logging from `warn` → `warning` (correct method name).

#### `backend/app/domain/document/constants.py`
- Added `JobStatus` enum: `QUEUED | PROCESSING | COMPLETED | FAILED`
- Updated `ALLOWED_MIME_TYPES`: PDF, DOCX, DOC, XLSX, XLS, PNG, JPEG
- Updated `MAX_FILE_SIZE_BYTES`: 100 MB (was 50 MB)
- Added `JOB_PROGRESS` dict mapping each `JobStatus` to a progress percentage

#### `backend/app/domain/document/models.py`
Added `ProcessingJob` dataclass: `id, document_id, status (JobStatus), error_message, created_at, updated_at`

#### `backend/app/domain/document/interfaces.py`
Added two new abstract interfaces:
- `IJobRepository` — `create`, `get_by_document_id`, `update_status`, `get_latest_statuses` (batch)
- `IQueueService` — `enqueue_ingestion_job`

#### `backend/app/application/document/services.py`
Major rewrite of `DocumentUseCase`:
- `upload_document`: now creates `ProcessingJob` (QUEUED) and enqueues to Redis
- `get_document_status`: returns the latest job for a document
- `list_documents_with_job_status`: batch-fetches job statuses (no N+1)
- `retry_document`: re-queues FAILED documents
- All errors now use typed `ErrorCode` enum members

#### `backend/app/infrastructure/document/job_repository.py` (NEW)
`PostgresJobRepository` implementing `IJobRepository`. Uses the `jobs` table from migration 001. Batch status fetch uses PostgreSQL `DISTINCT ON` for efficiency. JSONB `error_details` field is mapped to/from `error_message` string.

#### `backend/app/infrastructure/document/queue_service.py` (NEW)
`RedisQueueService` implementing `IQueueService`. Pushes `{"document_id": ..., "job_id": ...}` JSON payloads onto the `ingestion:jobs` Redis list via `RPUSH` (FIFO queue for Celery workers in M5+).

#### `backend/app/infrastructure/document/minio_storage_service.py`
Removed the hardcoded `"documents"` bucket auto-creation from `__init__`. Bucket initialization is now exclusively owned by `infra_init.py` (M1), eliminating the bucket name inconsistency.

#### `backend/app/infrastructure/di/container.py`
Added `get_job_repository()` and `get_queue_service()` factory methods. Updated `get_document_use_case()` to inject both.

#### `backend/app/presentation/api/v1/endpoints/document.py`
New endpoints and models:
- `POST /` → status 201 (was 200), now returns `job_status: "QUEUED"` in response
- `GET /` → enriched with `job_status` per document (batch-fetched)
- `GET /{id}/status` → returns `JobStatusResponse` with `progress_pct`
- `POST /{id}/retry` → re-queues a FAILED document
- `JobStatusResponse` model: `job_id, document_id, status, progress_pct, error_message, created_at, updated_at`

#### `backend/tests/test_document_upload.py` (NEW)
11 unit tests covering:
- File size validation (413 status)
- MIME type validation
- SHA-256 duplicate detection
- Successful upload creates document + job in QUEUED state + enqueues
- XLSX and PNG acceptance
- Correct bucket name (`industrial-documents`)
- `get_document_status` returns job
- `get_document_status` raises if no job
- `retry_document` re-queues FAILED documents
- `retry_document` raises if status is not FAILED

### Frontend

#### `frontend/src/components/documents/DocumentUpload.tsx`
- Updated `accept` attribute: `.pdf,.docx,.doc,.xlsx,.xls,.png,.jpg,.jpeg`
- Added client-side validation (size + MIME) before sending the request
- Shows `job_status: QUEUED` in success message
- Added `onUploadComplete` callback prop to allow parent to refresh list
- Added `RefreshCw` "Clear" button for error state
- Progress bar now goes to 85% during fetch, then jumps to 100%

#### `frontend/src/components/documents/DocumentList.tsx`
- `job_status` field displayed as the primary status badge
- Auto-polling every 5 seconds when any document has QUEUED / PROCESSING / READY_FOR_PROCESSING status
- Polling stops automatically when no in-progress documents remain
- Manual `RefreshCw` button added
- FAILED documents show an orange `RefreshCw` retry button
- Animated `Clock` spinner on in-progress status badges
- Status filter options updated to user-facing labels (Queued, Completed, Failed)
- MIME type displayed as subtitle under filename

---

## How to Verify

```bash
# 1. Start all services
docker compose up -d

# 2. Run migrations
cd backend && alembic upgrade head

# 3. Initialize infrastructure
python scripts/init_infra.py

# 4. Start backend
cd backend && uvicorn app.main:app --reload

# 5. Start frontend
cd frontend && pnpm dev

# 6. Run tests
cd backend && pytest tests/ -v

# 7. Test via API
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@industrialbrain.local&password=ChangeMe123!" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/test.pdf;type=application/pdf"

curl http://localhost:8000/api/v1/documents/{document_id}/status \
  -H "Authorization: Bearer $TOKEN"
```

---

## Status Flow

```
Upload received
    │
    ▼
Document created (status=UPLOADED)
    │
    ▼
Binary stored in MinIO "industrial-documents/{uuid}/v1/{filename}"
    │
    ▼
ProcessingJob created (status=QUEUED)
    │
    ▼
Job pushed to Redis "ingestion:jobs" list
    │
    ▼
Document status → READY_FOR_PROCESSING
    │
    ▼  [M3 — Celery workers will pick this up]
Job status → PROCESSING → COMPLETED | FAILED
```

---

## Not Implemented in M2 (by design)

- OCR / text extraction (M3)
- PaddleOCR / LayoutParser (M3)
- Vector embeddings (M4)
- Graph extraction (M5)
- Celery worker consuming the Redis queue (M5)
