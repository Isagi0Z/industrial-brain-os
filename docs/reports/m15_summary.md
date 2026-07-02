# M15 Summary — Event-Driven Ingestion Pipeline (Celery + Redis)

**Milestone**: M15
**Status**: ✅ Complete
**Date**: 2026-07-02

## Delivered

Replaced the synchronous, in-process ingestion daemon with a **Celery task
chain** on a Redis broker (ADR-015). Document upload now dispatches an async
`parse → embed → kg` chain and returns immediately; a separate worker process
runs the pipeline and advances the job's status, polled via
`GET /api/v1/jobs/{job_id}`.

- **Celery app** (`celery/celery_app.py`): Redis broker + result backend
  (separate logical DBs), json serializer, `task_acks_late`, configurable
  concurrency.
- **Tasks** (`celery/tasks.py`): `parse_task → embed_task → kg_task`, each a
  thin wrapper over the existing M2/M3, M4, M7 use case — no reimplementation.
  Retry ×3 with exponential backoff (60→120→240s); on exhaustion sets
  `jobs.status=FAILED` with `error_details {task, message}`; Correlation-ID
  restored from the payload; in-progress status set at each stage.
- **`CeleryQueueService`**: dispatches the chain behind the unchanged
  `IQueueService` port (so `DocumentUseCase` and its tests are untouched);
  captures the request Correlation-ID into the payload.
- **`GET /api/v1/jobs/{job_id}`**: reuses `JobStatusResponse` + `JOB_PROGRESS`;
  backed by new `IJobRepository.get_by_id`.
- **Deployment**: `Dockerfile` fixed (build context = repo root, copies `ai/`
  + `ontology/`); `docker-compose.yml` adds `ib_backend` + `ib_worker` (same
  image, `celery -A app.worker worker`, concurrency 2).

## Files created

```
backend/app/infrastructure/celery/__init__.py
backend/app/infrastructure/celery/celery_app.py
backend/app/infrastructure/celery/tasks.py
backend/app/worker.py
backend/app/infrastructure/document/celery_queue_service.py
backend/app/presentation/api/v1/endpoints/jobs.py
backend/tests/test_ingestion_celery.py
docs/walkthroughs/m15_walkthrough.md
docs/verification/m15_verification.md
docs/reports/m15_summary.md
```

## Files modified

```
backend/app/infrastructure/config/settings.py      — INGESTION_BACKEND, CELERY_* + broker/result URL properties
backend/requirements.txt                            — +celery[redis]>=5.3.0
backend/app/main.py                                 — lifespan skips in-process worker under the Celery backend
backend/app/infrastructure/di/container.py          — get_queue_service returns CeleryQueueService (configurable)
backend/app/domain/document/interfaces.py           — IJobRepository.get_by_id
backend/app/infrastructure/document/job_repository.py — PostgresJobRepository.get_by_id
backend/app/application/document/services.py         — DocumentUseCase.get_job_by_id
backend/app/presentation/api/v1/router.py            — register jobs router
backend/Dockerfile                                   — build context = repo root; copy ai/ + ontology/
docker-compose.yml                                   — +ib_backend +ib_worker; drop obsolete version key
docs/implementation_roadmap.md                       — M15 checklist [x] + SHA
```

## Key technical decisions

- **IQueueService swap, zero use-case churn.** M15 changes only the
  implementation behind the queue port; `DocumentUseCase` (and
  `test_document_upload`) are unchanged. The DI container selects
  Celery vs. the legacy Redis-list daemon via `INGESTION_BACKEND`.
- **Tasks reuse the existing use cases** — the whole point of the pre-M14
  refactor and the "avoid duplication" directive. Nothing in M2/M3/M4/M7
  was rewritten.
- **3-task chain (parse/embed/kg), documented deviation** from the roadmap's
  4-task list: M2 extraction and M3 parsing are one `DocumentParsingUseCase`
  in this codebase, so they are one Celery task rather than a fractured pair.
- **Stateless workers** (Engineering Bible §28): the payload carries only ids
  + correlation id; all state in PostgreSQL/Redis; `task_acks_late` for
  crash redelivery.
- **No migration**: the `jobs` table already carried `error_details JSONB`.

## Blockers encountered

- **PyPI SSL** installing `celery` — resolved with `--trusted-host` (the
  sandbox's known cert issue).
- **Worker cwd** — the initial host worker launched from the repo root and
  couldn't find the venv; relaunched from `backend/` with `--pool=solo`
  (Windows).
- **Docker image build** for `ib_worker` isn't feasible offline (heavy ML
  deps need network); the compose service is defined and the Dockerfile
  fixed, and E2E ran a host worker instead (dev's normal pattern).

## Test results

- **12 new M15 tests** (`test_ingestion_celery.py`) — all pass.
- **337 total backend tests pass** (325 baseline + 12), 0 failed.
- **Live E2E**: upload → Celery chain dispatched → separate worker consumed
  `parse (0.5s) → embed (11.8s) → kg (3.8s)` → job `COMPLETED (100%)` via
  `GET /jobs/{job_id}`; in-process daemon confirmed retired.

## What M15 unlocks

Ingestion now scales independently of the API and survives worker restarts.
The remaining Phase-3 item is **M16** (evaluation layer — golden-dataset RAG
metrics, consuming the M14 citation/hallucination signal), after which the
platform enters the Final Demo phase.
