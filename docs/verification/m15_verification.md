# M15 Verification Report

## Environment

| Check | Result |
|---|---|
| Docker connection | ✅ Engine 29.5.2, context `desktop-linux` |
| Running containers | 5 infra (postgres/redis/neo4j healthy; qdrant/minio `unhealthy` label — pre-existing `wget` healthcheck bug; both respond 200) |
| Docker Compose status | valid (`docker compose config` clean after adding `ib_backend` + `ib_worker`, dropping obsolete `version` key) |
| RepoWise sync | ✅ current at HEAD `fc7f02f` (pre-M15) |
| Current HEAD (pre-commit) | `fc7f02f` |
| Redis broker DB | ✅ `redis-cli -n 1 ping` → PONG |

## Quality Gate Results

| Gate | Tool | Result |
|------|------|--------|
| Formatting | `black` | ✅ Pass (M15 files clean; unrelated `worker.py` drift reverted) |
| Lint | `ruff check .` | ✅ All checks passed (repo-wide) |
| Type check | `mypy app/` | ✅ **10 errors in 8 files — identical to the pre-M15 baseline**; 0 new; 0 in any M15 file (the `worker.py` blpop errors are pre-existing) |
| Full suite | `pytest tests/` | ✅ **337 passed** (325 pre-M15 baseline + 12 new M15 tests), 0 failed |
| Docker services | direct checks | ✅ all infra respond healthy |
| Backend startup | `uvicorn` (INGESTION_BACKEND=celery) | ✅ boots; **in-process worker NOT started** (log has no "IngestionWorker started"); `/api/v1/health` → healthy |
| Celery worker | `celery -A app.worker worker --pool=solo` | ✅ connected to broker `redis://…/1` + results `…/2`; registered `ingestion.parse/embed/kg`; `celery@… ready.` |
| Frontend build | `pnpm build` | ✅ built in 17.48s, 0 errors |

## New Tests (test_ingestion_celery.py — 12 tests)

| Class / test | Covers |
|--------------|--------|
| `TestCeleryQueueService` (2) | dispatches the chain with document/job/**correlation_id** in the payload; implements `IQueueService` |
| `test_restore_correlation_*` (2) | correlation contextvar restored from payload (and default `-`) |
| `TestRetryBackoff` (4) | exponential backoff 60/120/240 by retry count; retries exhausted → job `FAILED` with `error_details` carrying task name + exception |
| `TestTaskExecution` (2) | full chain in **eager mode** runs parse→embed→kg, threads the payload, hits EXTRACTING/EMBEDDING/KG_EXTRACTING; embed skipped when no chunks |
| `TestJobLookup` (2) | `get_job_by_id` returns the job / raises 404 |

## Live End-to-End Verification

Backend (Celery backend) + a host-run Celery worker against the live Redis
broker; uploaded a small PNG:

```
POST /api/v1/documents/  → 201 immediately, job_status=QUEUED
   (heavy parse/embed/kg is dispatched to the worker, not awaited)

Celery worker log (separate process):
   Task ingestion.parse[…] received → parse_task started → succeeded in 0.52s
   Task ingestion.embed[…] received → succeeded in 11.81s
   Task ingestion.kg[…]    received → succeeded in 3.83s

GET /api/v1/jobs/{job_id} → status=COMPLETED, progress_pct=100
```

This proves the complete async flow: upload dispatches a Celery chain, a
**separate worker process** consumes all three tasks in sequence (payload
threaded forward), status transitions land in PostgreSQL, and the new
`/jobs/{job_id}` polling endpoint reports terminal `COMPLETED`. The
in-process daemon was confirmed retired under the Celery backend.

## Checklist coverage

- [x] `celery` + `kombu` in requirements.txt (pinned `celery[redis]>=5.3.0`)
- [x] Celery app: broker=Redis, backend=Redis, task serializer=json
- [x] `parse_task` → M2/M3 parsing use case; chains to `embed_task`
- [x] `embed_task` → M4 embedding use case; chains to `kg_task`
- [x] `kg_task` → M7 extraction use case (NER + relations + Neo4j)
- [~] roadmap's separate `extract_task`+`parse_task` are a single `parse_task` here — M2 extraction is folded into the M3 parsing use case (documented reuse-driven deviation; net pipeline unchanged)
- [x] Each task: max 3 retries, exponential backoff 60→120→240s
- [x] Each task updates `jobs.status` at start; the reused use case sets completion status
- [x] Failed task → `jobs.status=FAILED`, `error_details` JSON with task name + exception
- [x] Upload returns `{document_id, job_id(QUEUED)}` without awaiting processing (201 immediate; heavy stages run in the worker)
- [x] `ib_worker` service in docker-compose.yml (same image as backend, `celery -A app.worker worker`)
- [x] Worker concurrency 2, configurable via `CELERY_WORKER_CONCURRENCY`
- [x] Celery task logs include the propagated Correlation-ID
- [x] No session state in worker memory — payload carries ids only; state in PostgreSQL/Redis
- [x] Unit tests: retry logic, job status transitions, Correlation-ID propagation
- [x] Integration: upload → all tasks complete (verified live: parse→embed→kg → COMPLETED)

## Architecture compliance

- ADR-015 (event-driven processing): synchronous chain replaced by Celery
  tasks with retry; API responds immediately; workers scale independently. ✅
- Engineering Bible §23 (LLM/retry): 3 retries, exponential backoff. ✅
- Engineering Bible §28 (stateless services): payload carries only ids;
  `task_acks_late` for redelivery. ✅
- Engineering Bible §16 (logging): Correlation-ID propagated to worker logs. ✅
- Reuse: parse/embed/kg tasks delegate to the existing use cases; the
  `IQueueService` swap leaves `DocumentUseCase` and its tests unchanged. ✅

## Notes / limitations (not code defects)

- The `ib_worker` Docker image was not built in-sandbox (installing the heavy
  ML deps needs network the offline sandbox lacks); the compose service is
  defined and the Dockerfile was fixed (build context = repo root, copies
  `ai/` + `ontology/`). E2E used a host-run worker — the same host-run pattern
  the API uses in dev.
- Upload latency measured ~2.8s on a cold first request; this is dominated by
  the synchronous MinIO store + Postgres writes inherent to *upload*, not by
  document *processing* (which is now fully async in the worker). The
  architectural deliverable — decoupling heavy processing from the request —
  is verified above.
- Pre-existing, unchanged: `worker.py` mypy/black notes, qdrant/minio
  healthcheck labels, broken dev seeder, `llama3.2` not pulled (E2E used
  `mistral`).
