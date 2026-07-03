# M17 — Observability Stack — Summary

## Objective

Instrument all services with OpenTelemetry spans (ADR-016) and deploy
Prometheus + Grafana (ADR-017) so every agent step, database query, and LLM
call is a traceable span and every runtime/RAG-quality signal is a scraped
metric on a dashboard.

## What was built

- **OpenTelemetry tracing** (`infrastructure/observability/tracing.py`,
  extended from the M16 scaffold): OTLP/HTTP exporter to Jaeger, FastAPI
  auto-instrumentation, a `span()` helper that stamps the Correlation-ID, and
  `current_trace_id()` for log correlation. No-op when `OTEL_ENABLED=false` or
  the SDK is missing.
- **Hot-path spans**: `llm.generate` (Ollama + Gemini, with model/token/latency
  attributes), `vector_db.search` (Qdrant), `graph_db.traverse` (Neo4j),
  `celery.{parse,embed,kg}_task` (ingestion chain).
- **Application Prometheus metrics** (`infrastructure/observability/metrics.py`
  + `presentation/middleware/metrics_middleware.py`): `ib_http_requests_total`,
  `ib_http_request_duration_seconds`, `ib_llm_tokens_total`,
  `ib_celery_tasks_total`, `ib_active_ws_connections` — all guarded no-ops.
- **Log ↔ trace correlation**: the JSON log formatter now stamps `trace_id`
  alongside `correlation_id` on every record (Engineering Bible §16).
- **Compose services**: `jaeger` (16686 UI, 4317/4318 OTLP), `prometheus`
  (9090), `grafana` (3000); `OTEL_*` env wired on `ib_backend` + `ib_worker`.
- **Monitoring config**: Prometheus scrape config, Grafana datasource + dashboard
  provisioning, and two dashboards — **API Performance** (request rate, error
  rate, p50/p95/p99 latency, LLM tokens/hr, Celery task rate, active WS) and
  **RAG Quality** (hallucination / faithfulness / recall from the M16 gauges).

## Files

```
backend/app/infrastructure/observability/tracing.py     — tracer + span helpers (extended)
backend/app/infrastructure/observability/metrics.py     — app Prometheus collectors (new)
backend/app/presentation/middleware/metrics_middleware.py — HTTP metrics (new)
backend/app/infrastructure/chat/ollama_gateway.py       — llm.generate token counter
backend/app/infrastructure/chat/gemini_gateway.py       — llm.generate span + counter
backend/app/infrastructure/search/qdrant_repository.py  — vector_db.search span
backend/app/infrastructure/graphrag/neo4j_kg_traversal.py — graph_db.traverse span
backend/app/infrastructure/celery/tasks.py              — celery.* spans + counters
backend/app/infrastructure/logging/logger.py            — trace_id in log records
backend/app/presentation/api/v1/endpoints/chat.py       — WS connection gauge
backend/app/main.py                                     — metrics middleware + init
backend/requirements.txt                                — +opentelemetry-{sdk,exporter-otlp-proto-http,instrumentation-fastapi}
docker-compose.yml                                      — jaeger + prometheus + grafana
monitoring/prometheus/prometheus.yml                    — scrape config
monitoring/grafana/provisioning/datasources/*.yml       — Prometheus + Jaeger
monitoring/grafana/provisioning/dashboards/*.yml        — dashboard provider
monitoring/grafana/dashboards/{api_performance,rag_quality}.json — 2 dashboards
backend/tests/test_observability.py                     — 7 unit tests
```

## Design notes

- **Guarded degradation everywhere** — tracing and every metric recorder are
  no-ops without the SDK / when disabled, so observability can never break the
  request or ingestion path.
- **Bounded cardinality** — HTTP metrics label on the route *template*, not the
  concrete URL; no ids in label values.
- **No sensitive data** in spans or metric labels (Engineering Bible §16).
- **Clean Architecture** — spans/metrics live in infrastructure + presentation;
  application/domain layers import none of it.

## Verified

- 7 observability unit tests pass; full backend suite green.
- Live tracing verified: real spans created with 32-hex trace ids under
  `OTEL_ENABLED=true`; no-op confirmed when disabled.
- Ruff clean, black formatted, app imports cleanly with `/metrics` mounted.
