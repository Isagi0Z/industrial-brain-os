# M17 — Observability Stack (OpenTelemetry + Prometheus + Grafana)

## What this milestone delivers

Distributed tracing and metrics across the platform (architecture §, ADR-016
tracing, ADR-017 metrics). Every LLM call, vector search, graph traversal, and
Celery ingestion task emits an OpenTelemetry span exported to **Jaeger**;
runtime and RAG-quality metrics are scraped by **Prometheus** and rendered in
two pre-provisioned **Grafana** dashboards. Traces and structured logs join on
the same id (Correlation-ID ↔ OTel trace id).

```
HTTP request ──► PrometheusMetricsMiddleware ─► ib_http_requests_total
                                                ib_http_request_duration_seconds
   │  (FastAPIInstrumentor root span, trace id = correlation id)
   ├─► GraphRAGEngine.retrieve
   │      ├─ span "vector_db.search"   {collection, top_k, result_count, latency_ms}
   │      └─ span "graph_db.traverse"  {query_type, depth, result_count, latency_ms}
   ├─► ChatUseCase → ModelGateway.generate
   │      └─ span "llm.generate"       {model, prompt_tokens, completion_tokens, latency_ms}
   │                                    ib_llm_tokens_total{model,type}
   └─► upload → Celery chain (separate process, same trace via Correlation-ID)
          span "celery.parse_task" → "celery.embed_task" → "celery.kg_task"
          ib_celery_tasks_total{task,status}

Prometheus ── scrapes ──► ib_backend:8000/metrics ──► Grafana dashboards
Jaeger ◄── OTLP/HTTP 4318 ── spans from API + worker ──► Jaeger UI :16686
```

## Components

| Layer | Files |
|-------|-------|
| Tracing | `infrastructure/observability/tracing.py` — tracer init (OTLP/HTTP → Jaeger), `span()` context manager, `set_span_attributes()`, `current_trace_id()` |
| Metrics | `infrastructure/observability/metrics.py` — app Prometheus collectors (HTTP, LLM tokens, Celery, WebSocket) + guarded recorders; M16 `evaluation/metrics.py` gauges reused |
| HTTP middleware | `presentation/middleware/metrics_middleware.py` — per-request count + latency by route template |
| Instrumented hot paths | `chat/ollama_gateway.py`, `chat/gemini_gateway.py` (llm.generate), `search/qdrant_repository.py` (vector_db.search), `graphrag/neo4j_kg_traversal.py` (graph_db.traverse), `celery/tasks.py` (celery.*) |
| Log correlation | `logging/logger.py` — injects `trace_id` into every JSON log record |
| Compose | `docker-compose.yml` — `jaeger`, `prometheus`, `grafana` services; `OTEL_*` env on `ib_backend` + `ib_worker` |
| Monitoring config | `monitoring/prometheus/prometheus.yml`; `monitoring/grafana/provisioning/{datasources,dashboards}/*.yml`; `monitoring/grafana/dashboards/{api_performance,rag_quality}.json` |
| Tests | `tests/test_observability.py` (7 tests) |

## Span attributes (checklist mapping)

- **LLM** `llm.generate`: `llm.model`, `llm.prompt_tokens`, `llm.completion_tokens`, `llm.latency_ms`
- **Qdrant** `vector_db.search`: `vector_db.collection`, `vector_db.top_k`, `vector_db.result_count`, `vector_db.latency_ms`
- **Neo4j** `graph_db.traverse`: `graph_db.query_type`, `graph_db.depth`, `graph_db.result_count`, `graph_db.latency_ms`
- **Celery** `celery.{parse,embed,kg}_task`: `celery.task`, `job_id`, `document_id`
- Every span additionally carries `correlation_id` (Engineering Bible §16). No
  secrets, passwords, or raw query text are ever set as attributes.

## Metrics exposed on `/metrics`

| Metric | Type | Labels | Dashboard use |
|--------|------|--------|---------------|
| `ib_http_requests_total` | counter | method, path, status | request rate, error rate |
| `ib_http_request_duration_seconds` | histogram | method, path | p50/p95/p99 latency |
| `ib_llm_tokens_total` | counter | model, type | token usage per hour |
| `ib_celery_tasks_total` | counter | task, status | ingestion task rate |
| `ib_active_ws_connections` | gauge | — | live streaming clients |
| `ib_hallucination_rate` / `ib_faithfulness_score` / `ib_retrieval_recall` | gauge (M16) | — | RAG quality dashboard |

## Ports & access

- Jaeger UI: `http://localhost:16686` — OTLP in on 4317 (gRPC) / 4318 (HTTP)
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin/admin by default; override with `GRAFANA_ADMIN_*`)

`docker compose up` brings all three monitoring services up with datasources
and dashboards auto-provisioned — no manual configuration.

## Config (settings + env)

| Setting | Default | Compose value |
|---------|---------|---------------|
| `OTEL_ENABLED` | `false` (host/dev) | `true` |
| `OTEL_SERVICE_NAME` | `industrial-brain-api` | api / worker |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | `http://jaeger:4318` |

## Deviations (documented, not defects)

- The checklist's `opentelemetry-instrumentation-sqlalchemy` does not apply —
  this project uses no SQLAlchemy ORM (psycopg2 + Neo4j/Qdrant clients), so DB
  observability is delivered by explicit spans at the repository/service
  wrappers (`vector_db.search`, `graph_db.traverse`) instead.
- **Celery queue depth**: Prometheus scrapes the API process, so the ingestion
  panel charts task *rate* via `ib_celery_tasks_total` (recorded in-task) and
  per-task worker spans appear in Jaeger. A true queue-depth gauge would need a
  redis-exporter or a worker-side metrics port; the trace view already gives
  per-task ingestion visibility.
- Tracing/metrics are **guarded no-ops** when the SDK is unavailable or
  `OTEL_ENABLED=false`, so nothing here can break the request/ingestion path —
  the same offline-safe pattern as LLMLingua, PaddleOCR, and the reranker.
