# M15 Walkthrough — Event-Driven Ingestion Pipeline (Celery + Redis)

## Overview

M15 replaces the synchronous, in-process ingestion daemon (`IngestionWorker`
polling a Redis list) with a **Celery task chain** on a Redis broker
(ADR-015). Document upload now dispatches an async chain and returns
immediately; a separate worker process runs the pipeline and advances the
job's status in PostgreSQL, which clients poll via `GET /api/v1/jobs/{job_id}`.

```
POST /api/v1/documents/  ──► DocumentUseCase.upload_document
     (validate, hash-dedupe, store to MinIO, create job=QUEUED)
        │
        └─ IQueueService.enqueue_ingestion_job(document_id, job_id)
              → CeleryQueueService: chain(parse_task.s(payload),
                                          embed_task.s(), kg_task.s()).apply_async()
        │
     returns 201 immediately (processing is fully async)

[ celery -A app.worker worker ]  (separate process, Redis broker)
     ingestion.parse → DocumentParsingUseCase.parse_document   (M2+M3)
     ingestion.embed → EmbeddingUseCase.embed_document          (M4)
     ingestion.kg    → ExtractionUseCase.run_for_document        (M7)
        each: restore Correlation-ID, mark in-progress, run use case,
              forward payload, retry ×3 (60→120→240s), FAILED on exhaustion

GET /api/v1/jobs/{job_id}  ──► current status + progress_pct
```

## Reuse, not reimplementation

Per the "avoid duplicate implementations" directive, the Celery tasks are
**thin wrappers over the existing use cases** — no M2/M3/M4/M7 logic was
rewritten:

| Task | Delegates to | Milestone |
|------|--------------|-----------|
| `parse_task` | `DocumentParsingUseCase.parse_document` | M2 PyMuPDF extract + M3 layout/OCR/chunk (unified in one use case in this codebase) |
| `embed_task` | `EmbeddingUseCase.embed_document` | M4 embed + Qdrant upsert |
| `kg_task` | `ExtractionUseCase.run_for_document` | M7 NER + relations + Neo4j |

**Deliberate 3-task chain (not 4).** The roadmap lists `extract_task` and
`parse_task` separately, but in this codebase M2 text extraction and M3 layout
parsing/chunking are a single `DocumentParsingUseCase` — splitting them into
two Celery tasks would mean either double-parsing or fracturing a tested use
case. The chain is therefore `parse → embed → kg`, matching the real
use-case boundaries. Documented here as a conscious, reuse-driven deviation.

## The IQueueService swap (zero use-case churn)

`DocumentUseCase` calls `queue_service.enqueue_ingestion_job(document_id,
job_id)` — unchanged. M15 only swaps the *implementation* behind that port:

- `RedisQueueService` (legacy) → pushed a JSON payload onto a Redis list.
- `CeleryQueueService` (M15) → dispatches the Celery chain, capturing the
  request's Correlation-ID (a contextvar set by the logging middleware) into
  the task payload so every worker-side log line joins the same trace.

The DI container selects the implementation via `settings.INGESTION_BACKEND`
(`"celery"` default; `"redis-queue"` keeps the legacy daemon). Because
`DocumentUseCase` and its tests target the `IQueueService` port, all existing
upload tests pass unchanged.

## Task resilience (Engineering Bible §23, §28)

- **Retry / backoff**: `_handle_failure` retries up to 3× with exponential
  backoff — 60 → 120 → 240 s (`countdown = 60 · 2^retries`). On the final
  attempt it sets `jobs.status = FAILED` with `error_details = {task,
  message}` and re-raises.
- **Status transitions**: each task marks its in-progress status at start
  (EXTRACTING / EMBEDDING / KG_EXTRACTING); the reused use case sets the
  completion status (CHUNKED / INDEXED / KG_POPULATED → COMPLETED).
- **Stateless workers**: the payload carries only ids + the correlation id;
  all state lives in PostgreSQL / Redis. `task_acks_late=True` re-delivers a
  task if a worker dies mid-execution.
- **Correlation-ID propagation**: `_restore_correlation` re-sets the contextvar
  from the payload at the start of every task.

## New / changed surfaces

| Layer | Change |
|-------|--------|
| Infrastructure | `celery/celery_app.py` (Redis broker/backend, json serializer, concurrency); `celery/tasks.py` (parse/embed/kg + retry/backoff/failure); `document/celery_queue_service.py`; `app/worker.py` entrypoint |
| Application | `DocumentUseCase.get_job_by_id` (reuses the job repo) |
| Domain | `IJobRepository.get_by_id` |
| Infrastructure (repo) | `PostgresJobRepository.get_by_id` |
| Presentation | `jobs.py` — `GET /api/v1/jobs/{job_id}` (reuses `JobStatusResponse` + `JOB_PROGRESS`); registered in the router |
| Config | `settings.py` — `INGESTION_BACKEND`, `CELERY_*`, `celery_broker_url`/`celery_result_backend` properties |
| Lifespan | `main.py` starts the in-process worker only when `INGESTION_BACKEND != "celery"` |
| Deploy | `Dockerfile` fixed (build context = repo root; copies `ai/` + `ontology/`); `docker-compose.yml` adds `ib_backend` + `ib_worker` (same image, `celery -A app.worker worker`, concurrency 2), drops the obsolete `version` key |

## Configuration

| Setting | Default |
|---------|---------|
| `INGESTION_BACKEND` | `celery` |
| `CELERY_BROKER_DB` / `CELERY_RESULT_DB` | Redis DB `1` / `2` |
| `CELERY_WORKER_CONCURRENCY` | `2` |

Broker/result URLs are derived from the existing Redis settings
(`redis://:<pw>@<host>:<port>/<db>`), so no new credentials.

## Environment notes

`celery[redis]>=5.3.0` added to `requirements.txt` (pulls `kombu`). The worker
runs as `celery -A app.worker worker`; on Windows dev use `--pool=solo`. The
`ib_worker` compose service is defined for containerized deployment; building
that image requires network access to install the (heavy) ML dependencies,
which the offline sandbox lacks — so E2E used a host-run worker against the
live Redis broker (the same host-run pattern the API itself uses in dev). No
migration is needed: the `jobs` table already carries `error_details JSONB`.
