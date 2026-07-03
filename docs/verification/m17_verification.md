# M17 — Observability Stack — Verification

## Scope

OpenTelemetry tracing (ADR-016) + Prometheus/Grafana metrics (ADR-017) across
the API and Celery worker: LLM, vector, graph, and ingestion spans exported to
Jaeger; runtime + RAG-quality metrics scraped by Prometheus and rendered in two
Grafana dashboards; logs correlated to traces.

## Unit tests

`tests/test_observability.py` — 7 tests:

| Test | Asserts |
|------|---------|
| `test_init_app_metrics_idempotent` | second `init_app_metrics()` never raises duplicate-timeseries |
| `test_record_http_request_increments_counter` | `ib_http_requests_total{...}` +1 |
| `test_record_llm_tokens_splits_prompt_and_completion` | prompt/completion token counters move independently |
| `test_ws_connection_gauge_inc_dec` | `ib_active_ws_connections` inc then dec back |
| `test_record_celery_task_counter` | `ib_celery_tasks_total{task,status}` +1 |
| `test_recorders_are_noop_before_init` | recorders never raise when collectors unset |
| `test_span_is_noop_without_tracer` | `span()`/`set_span_attributes()` no-op, `current_trace_id()` None when disabled |

**Full backend suite: 357 passed, 0 failed** (350 prior + 7 new), run with a
writable pytest basetemp. See the environment note below.

## Live verification

```
1. Tracing no-op path (OTEL_ENABLED=false, default)
   → init returns False; span() yields; current_trace_id() == None   ✅

2. Tracing live path (OTEL_ENABLED=true)
   → init_tracing() == True (OTLP/HTTP exporter to :4318)
   → inside span("test.llm.generate"): current_trace_id() == 32-hex id ✅
   → outside span: None                                               ✅
   (export to a not-yet-running Jaeger fails transiently and is swallowed —
    span creation + trace-id correlation are independent of export)

3. App import + boot
   → app.main imports clean; "Application Prometheus metrics initialized";
     "/metrics endpoint mounted"                                      ✅

4. docker compose config --quiet → valid; 10 services incl.
   jaeger / prometheus / grafana                                      ✅

5. Monitoring stack up (jaeger + prometheus + grafana, --no-deps):
   → Jaeger UI     http://localhost:16686/            → HTTP 200       ✅
   → Prometheus    http://localhost:9090/-/ready      → "Ready"        ✅
   → Prometheus discovered the industrial-brain-api scrape target from
     prometheus.yml (health "down" only because the backend was not
     co-started with --no-deps — proves the scrape config resolves)    ✅
   → Grafana       http://localhost:3000/api/health   → database ok    ✅
   → Grafana datasources provisioned: Prometheus (uid=prometheus) + Jaeger (uid=jaeger) ✅
   → Grafana dashboards provisioned: ib-api-performance, ib-rag-quality ✅
```

## Checklist coverage

- [x] `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi` in `requirements.txt`
- [x] OTel tracer initialized at FastAPI startup; exports to Jaeger via OTLP/HTTP (`init_tracing(app)` in `main.py`)
- [x] Every LLM call span (`llm.generate`) with `llm.model`, `llm.prompt_tokens`, `llm.completion_tokens`, `llm.latency_ms` (Ollama + Gemini)
- [x] Every Qdrant query span (`vector_db.search`) with `vector_db.collection`, `vector_db.top_k`, `vector_db.result_count`, `vector_db.latency_ms`
- [x] Every Neo4j query span (`graph_db.traverse`) with `graph_db.query_type`, `graph_db.depth`, `graph_db.result_count`, `graph_db.latency_ms`
- [x] Every Celery task span (`celery.parse_task` / `embed_task` / `kg_task`); trace context propagated from upload via the restored Correlation-ID
- [x] Correlation-ID stamped on every span; OTel `trace_id` injected into every JSON log record (`logger.py`)
- [x] `jaeger` service (`jaegertracing/all-in-one:1.57`, 16686 UI, 4317/4318 OTLP)
- [x] `prometheus` service scrapes the FastAPI `/metrics` endpoint (`monitoring/prometheus/prometheus.yml`)
- [x] `grafana` service with pre-configured Prometheus + Jaeger datasources
- [x] Grafana dashboard JSON committed to `monitoring/grafana/dashboards/`
- [x] Dashboard panels: request rate, p50/p95/p99 latency, LLM token usage per hour, Celery task rate, active WebSocket connections
- [x] Dashboard panels: hallucination rate + faithfulness score (+ recall) from the M16 gauges
- [x] No sensitive data as span attributes / metric labels — sizes, ids, latencies, route templates only (Engineering Bible §16)
- [x] `docker compose up` brings all monitoring services up with datasources + dashboards auto-provisioned, no extra config
- [~] Smoke test `/chat` → trace in Jaeger UI: span creation + OTLP export path verified live; a full in-network `/chat` trace requires the backend running inside compose with `OTEL_ENABLED=true` (env wired on `ib_backend`)

## Architecture compliance

- ADR-016 (OpenTelemetry): OTLP/HTTP exporter, FastAPI auto-instrumentation,
  explicit hot-path spans. ✅
- ADR-017 (Prometheus + Grafana): `/metrics` scraped by Prometheus; two
  provisioned Grafana dashboards. ✅
- ADR-013 (Clean Architecture): tracing + metrics live in infrastructure +
  presentation; application/domain import none of them. ✅
- Engineering Bible §16: Correlation-ID ↔ trace-id join; no sensitive span
  attributes. ✅
- Reuse: M16 evaluation gauges power the RAG-quality dashboard; the M14/M15
  hot paths gain spans without logic changes. ✅

## Deviations / notes (documented, not code defects)

- `opentelemetry-instrumentation-sqlalchemy` from the checklist is **N/A** — no
  SQLAlchemy ORM in this project; DB spans are placed at the Qdrant/Neo4j
  repository wrappers instead (`vector_db.search`, `graph_db.traverse`).
- **Celery queue depth**: Prometheus scrapes the API process, so the ingestion
  panel shows task *rate* (`ib_celery_tasks_total`) and per-task worker spans
  appear in Jaeger; a true queue-depth gauge would need a redis-exporter or a
  worker-side metrics port (documented, deferred).
- **Environment**: on this Windows host, pytest's default temp base
  (`%TEMP%\pytest-of-*`) raises `PermissionError [WinError 5]` at fixture setup,
  erroring the 71 `tmp_path`-using tests regardless of milestone. Running with a
  writable `--basetemp` yields **357 passed, 0 failed**. This is a machine temp
  ACL issue, not an M17 regression.
- Tracing/metrics are guarded no-ops when the SDK is unavailable or
  `OTEL_ENABLED=false`, so observability can never break request/ingestion flow.
