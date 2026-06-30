# M2 Summary — Document Ingestion Pipeline

**Milestone**: M2  
**Phase**: MVP  
**Completed**: 2026-06-30  
**Commit**: (stamped after push)  
**Depends on**: M1 (infrastructure, auth)

---

## Deliverables

### Backend (14 files changed / 2 new)

| File | Change |
|------|--------|
| `shared/python/.../constants.py` | +8 `ErrorCode` values |
| `backend/app/presentation/middleware/error_handler.py` | Fixed `.value` bug, `warn`→`warning` |
| `backend/app/domain/document/constants.py` | `JobStatus` enum, `JOB_PROGRESS`, 100 MB limit, XLSX MIME |
| `backend/app/domain/document/models.py` | `ProcessingJob` dataclass |
| `backend/app/domain/document/interfaces.py` | `IJobRepository`, `IQueueService` |
| `backend/app/application/document/services.py` | `upload_document`, `get_document_status`, `list_documents_with_job_status`, `retry_document` |
| `backend/app/infrastructure/document/job_repository.py` | NEW — `PostgresJobRepository` |
| `backend/app/infrastructure/document/queue_service.py` | NEW — `RedisQueueService` |
| `backend/app/infrastructure/document/minio_storage_service.py` | Removed stale bucket creation |
| `backend/app/infrastructure/di/container.py` | Wired `job_repo` and `queue_svc` |
| `backend/app/presentation/api/v1/endpoints/document.py` | 201 status, `job_status` field, `/status`, `/retry` |
| `backend/tests/test_document_upload.py` | NEW — 11 unit tests |
| `scripts/init_infra.py` | Fixed Windows Unicode encoding on print |

### Frontend (2 files changed)

| File | Change |
|------|--------|
| `frontend/src/components/documents/DocumentUpload.tsx` | Accepted types, client validation, callback, success message |
| `frontend/src/components/documents/DocumentList.tsx` | `job_status` badge, auto-poll, retry button, manual refresh |

---

## API Surface Added

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/documents/` | Upload document (status 201) |
| `GET` | `/api/v1/documents/` | List with `job_status` per doc |
| `GET` | `/api/v1/documents/{id}/status` | Job status + progress_pct |
| `POST` | `/api/v1/documents/{id}/retry` | Re-queue FAILED document |

---

## Validation Results

| Gate | Result |
|------|--------|
| Black formatting | PASS |
| Ruff lint | PASS |
| ESLint (frontend) | PASS |
| TypeScript build | PASS |
| pytest (13 tests) | PASS — 13/13 |
| Docker health | PASS — 5/5 healthy |
| E2E upload flow | PASS |
| MIME rejection | PASS |
| Redis queue write | PASS |
| Frontend serves | PASS |

---

## Architecture Compliance

- **Clean Architecture**: domain models define `ProcessingJob`; interfaces (`IJobRepository`, `IQueueService`) in domain layer; implementations in infrastructure; use case in application layer.
- **SOLID**: `DocumentUseCase` has one reason to change per use case; `IJobRepository` and `IQueueService` are injectable; `PostgresJobRepository` can be swapped for any SQL backend.
- **DDD**: `ProcessingJob` is an aggregate root tracking the processing lifecycle; `JobStatus` is a value object.
- **No hardcoded secrets**: all credentials come from `settings` (env vars).
- **No N+1**: batch `get_latest_statuses` uses `DISTINCT ON (document_id)` in a single PostgreSQL query.
- **No ORM imports in domain**: domain layer only uses dataclasses and Python stdlib.

---

## Not in Scope (M3+)

| Feature | Milestone |
|---------|-----------|
| OCR / text extraction | M3 |
| Celery worker consuming `ingestion:jobs` | M5 |
| Vector embeddings | M4 |
| Graph extraction (Neo4j) | M5 |
| LLM-based copilot | M6 |
