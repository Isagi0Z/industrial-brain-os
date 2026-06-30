# M2 Verification Report — Document Ingestion Pipeline

**Milestone**: M2  
**Date**: 2026-06-30  
**Status**: PASSED

---

## Checklist

### Formatting

| Check | Command | Result |
|-------|---------|--------|
| Black (format) | `python -m black app tests` | 6 files reformatted, 0 errors |
| Black (verify) | `python -m black --check app tests` | All 44 files unchanged |
| Ruff (lint+fix) | `python -m ruff check app tests --fix` | 1 fixed, 0 remaining |
| Ruff (verify) | `python -m ruff check app tests` | 0 errors |

### Type Checking (Frontend)

| Check | Command | Result |
|-------|---------|--------|
| TypeScript build | `pnpm build` | 1486 modules transformed, 0 errors |
| ESLint | `eslint src --ext .ts,.tsx` | 0 errors, 0 warnings |

### Tests

| Test | Module | Result |
|------|--------|--------|
| Health endpoint responds | `test_health.py` | PASSED |
| Health includes all services | `test_health.py` | PASSED |
| Rejects oversized file (413) | `test_document_upload.py` | PASSED |
| Rejects invalid MIME type | `test_document_upload.py` | PASSED |
| Rejects duplicate SHA-256 | `test_document_upload.py` | PASSED |
| Upload creates document + job | `test_document_upload.py` | PASSED |
| Accepts XLSX MIME type | `test_document_upload.py` | PASSED |
| Accepts PNG MIME type | `test_document_upload.py` | PASSED |
| Stores to "industrial-documents" bucket | `test_document_upload.py` | PASSED |
| Status returns QUEUED job | `test_document_upload.py` | PASSED |
| Status raises if no job exists | `test_document_upload.py` | PASSED |
| Retry re-queues FAILED doc | `test_document_upload.py` | PASSED |
| Retry raises if not FAILED | `test_document_upload.py` | PASSED |

**Total: 13/13 passed**

### Infrastructure (Docker)

| Service | Status |
|---------|--------|
| PostgreSQL (`ib_postgres`) | Running |
| Neo4j (`ib_neo4j`) | Running |
| Qdrant (`ib_qdrant`) | Running |
| Redis (`ib_redis`) | Running |
| MinIO (`ib_minio`) | Running |

### Database / Infra Init

| Check | Result |
|-------|--------|
| Alembic migrations applied | 001_baseline_schema applied |
| MinIO bucket `industrial-documents` | Created |
| MinIO bucket `processed-chunks` | Created |
| Neo4j constraints | Applied |
| Qdrant collection `document_chunks` | Created |

### Backend Health

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development",
  "databases": {
    "postgres": "healthy",
    "neo4j": "healthy",
    "qdrant": "healthy",
    "redis": "healthy",
    "minio": "healthy"
  }
}
```

### End-to-End API Tests

#### Upload PDF (Success)
```
POST /api/v1/documents/
HTTP 201
{
  "id": "741ad888-19e8-46fa-b44f-6fc293b97bb6",
  "original_filename": "tmpx8_qswe9.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 41,
  "status": "READY_FOR_PROCESSING",
  "job_status": "QUEUED"
}
```

#### Get Job Status
```
GET /api/v1/documents/741ad888-19e8-46fa-b44f-6fc293b97bb6/status
HTTP 200
{
  "job_id": "5c4b79dd-50a5-49e3-a120-bb3fe17333ed",
  "document_id": "741ad888-19e8-46fa-b44f-6fc293b97bb6",
  "status": "QUEUED",
  "progress_pct": 10,
  "error_message": null
}
```

#### List Documents (with job_status)
```
GET /api/v1/documents/?limit=5
HTTP 200
{
  "total": 2,
  "documents": [{ "job_status": "QUEUED", ... }]
}
```

#### MIME Validation (Rejection)
```
POST /api/v1/documents/  [application/x-executable]
HTTP 422
{ "code": "INVALID_MIME_TYPE" }
```

#### Redis Queue Depth
```
LLEN ingestion:jobs = 1
LRANGE ingestion:jobs 0 0 = ['{"document_id": "741ad888-...", "job_id": "5c4b79dd-..."}']
```

### Frontend

| Check | Result |
|-------|--------|
| Dev server starts | http://localhost:5173 (HTTP 200) |
| Build output | 250 kB JS, 1.4 kB CSS, 0.56 kB HTML |
| ESLint | 0 errors |
| TypeScript | 0 errors |

---

## Skipped (by design)

- `repowise update` — CLI does not support local `update` command; index is refreshed automatically by webhook on push.

---

## Conclusion

All 13 tests pass. All 5 Docker services are healthy. The upload API flow is verified end-to-end: file accepted → stored in MinIO → job created in PostgreSQL → payload pushed to Redis. MIME rejection and status endpoints both work correctly. Frontend builds and serves without errors.

**M2 is complete and ready to commit.**
