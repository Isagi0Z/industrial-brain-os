# M1 Walkthrough — Infrastructure Validation & Database Initialization

**Milestone**: M1  
**Phase**: MVP  
**Completed**: 2026-06-30

---

## What Was Built

M1 closes the gap between the baseline repository skeleton (commits `3061f0a`–`4bb9a3b`) and a fully initialized storage layer. Every downstream milestone (M2–M6) can now write to clean, schema-validated storage targets.

---

## File-by-File Walkthrough

### 1. `backend/pytest.ini`
Fixed `PYTHONPATH` so `pytest tests/` works without manual `PYTHONPATH=.` prefix. Added `asyncio_mode = strict` for future async tests.

### 2. `backend/alembic.ini`
Standard Alembic configuration pointing `script_location = migrations`. The `sqlalchemy.url` is a placeholder — it is overridden at runtime by `migrations/env.py` from application settings. This prevents credentials from being duplicated in config files.

### 3. `backend/migrations/env.py`
Alembic environment script that:
- Adds the `backend/` directory to `sys.path` so `app.*` imports resolve.
- Reads `settings.POSTGRES_*` to build the live database URL dynamically.
- Supports both offline (SQL script generation) and online (live connection) migration modes.
- Uses `target_metadata = None` — all DDL is written as raw SQL via `op.execute()`, with no SQLAlchemy ORM dependency in application code.

### 4. `backend/migrations/versions/001_baseline_schema.py`
Initial migration creating **all nine tables** required for the MVP phase. All `CREATE TABLE` statements use `IF NOT EXISTS`, making the migration idempotent against a database that was pre-initialized by the `_ensure_tables()` calls in the repository layer.

**Tables created**:

| Table | Purpose |
| :---- | :------ |
| `users` | Auth identities |
| `roles` | RBAC role definitions with JSONB permissions |
| `documents` | Document master records |
| `document_versions` | Version history per document |
| `document_metadata` | JSONB metadata per document |
| `document_classifications` | AI classification labels |
| `document_chunks` | Chunked text for embedding pipeline (M4) |
| `jobs` | Async processing job state machine |
| `audit_logs` | Immutable audit trail with Correlation-ID |

**Indexes created**: `idx_documents_status`, `idx_documents_created_by`, `idx_chunks_document_id`, `idx_jobs_document_id`, `idx_jobs_status`, `idx_audit_user_id`, `idx_audit_created_at`, `idx_audit_correlation_id`.

### 5. `backend/app/infrastructure/database/infra_init.py`
Idempotent initialization module for the three non-relational services:

**Qdrant**:
- Creates `document_chunks` collection (1024-dim, Cosine distance) if absent.
- Applies payload indexes on `document_id`, `role_scope`, `page_number`, `chunk_type` for RBAC-aware filtered searches.

**Neo4j**:
- Applies four uniqueness constraints: `Asset.tag_number`, `Equipment.tag_number`, `Sensor.tag_number`, `Document.source_id`.
- Applies two property indexes: `FailureMode.failure_code`, `Procedure.procedure_type`.
- All Cypher uses `IF NOT EXISTS` (Neo4j 5.x) for idempotency.

**MinIO**:
- Creates buckets `industrial-documents` (raw uploads) and `processed-chunks` (extracted text artifacts) if absent.

All three functions are individually callable and are orchestrated by `run_all()`.

### 6. `backend/app/main.py` (updated)
Startup lifespan now calls `init_infrastructure(qdrant, neo4j, minio)` immediately after connectivity verification. If any service is unreachable at startup, infrastructure init is skipped gracefully with an error log (does not crash the API).

### 7. `scripts/init_infra.py`
Standalone CLI script for running the full init sequence outside of the API process. Useful for CI, first-boot setup, and verification:

```
python scripts/init_infra.py
```

Exits 0 on success, 1 on any connectivity or init failure.

### 8. `scripts/init_infra.sh`
Bash wrapper around `init_infra.py` for use in Unix-like environments (CI, WSL, Linux deploy).

### 9. `Makefile` (updated)
Added three new targets:
- `make db-migrate` — runs `alembic upgrade head`
- `make db-reset` — runs `alembic downgrade base && alembic upgrade head`
- `make init-infra` — runs `python scripts/init_infra.py`

### 10. `frontend/src/context/AuthContext.tsx` (new)
`AuthProvider` + `useAuth()` hook — provides `{ token, setToken }` backed by `localStorage`. Required by `DocumentDetails`, `DocumentList`, and `DocumentUpload` which were importing this context but it had never been created.

### 11. `frontend/src/App.tsx` (updated)
Wrapped `RouterProvider` inside `<AuthProvider>` so all routes have access to authentication state.

### 12. Bug fixes
- `backend/app/infrastructure/logging/logger.py`: Fixed `AttributeError: 'LogRecord' object has no attribute 'asctime'` by using `getattr(record, 'asctime', None)`.
- `backend/app/application/document/services.py`: Removed unused `doc = ...` assignment (ruff F841).
- Pre-existing unused imports removed from `document_repository.py` and `document.py` endpoint (ruff F401).
- All 8 backend files reformatted by `black`.

---

## How to Run

```bash
# 1. Start infrastructure
docker compose up -d

# 2. Run database migrations
make db-migrate

# 3. Initialise Qdrant / Neo4j / MinIO
make init-infra

# 4. Start backend
cd backend && uvicorn app.main:app --reload

# 5. Start frontend
cd frontend && pnpm dev
```

---

## Alembic Usage

```bash
# Apply migrations
cd backend && alembic upgrade head

# View history
cd backend && alembic history

# Roll back one step
cd backend && alembic downgrade -1

# Full reset (destroys data)
make db-reset
```
