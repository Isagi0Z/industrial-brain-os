"""Application Prometheus metrics (M17, ADR-017).

Complements the M16 evaluation gauges (``ib_hallucination_rate`` etc. in
``application/evaluation/metrics.py``) with the runtime metrics the Grafana
"API Performance" dashboard renders:

    ib_http_requests_total{method,path,status}      — request rate + errors
    ib_http_request_duration_seconds{method,path}   — p50/p95/p99 latency
    ib_llm_tokens_total{model,type}                 — LLM token usage
    ib_celery_tasks_total{task,status}              — ingestion dispatch/outcome
    ib_active_ws_connections                        — live streaming clients

All collectors are created through a get-or-create guard so importing this
module twice (tests, reload) never raises "Duplicated timeseries", and every
recorder degrades to a **no-op** when ``prometheus_client`` is unavailable —
the same offline-safe pattern as the tracer and the evaluation recorder.

Metrics recorded here live on the default registry, which the ``/metrics``
ASGI app (mounted in ``main.py``) exposes for Prometheus to scrape. Never
record sensitive values (tokens, passwords, raw query text) as label values;
the ``path`` label is the route *template*, not the concrete URL, to keep
cardinality bounded (Engineering Bible §16).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge, Histogram

    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover - prometheus_client is a declared dep
    _PROM_AVAILABLE = False

# Latency buckets tuned for API + RAG calls (seconds): sub-100ms through 10s.
_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

_http_requests: Optional[object] = None
_http_latency: Optional[object] = None
_llm_tokens: Optional[object] = None
_celery_tasks: Optional[object] = None
_ws_connections: Optional[object] = None
_initialized = False


def _get_or_create(factory, name: str, *args, **kwargs):
    """Return the existing collector registered under ``name`` or build a new
    one — avoids the default registry's duplicate-timeseries error."""
    from prometheus_client import REGISTRY

    existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
    if existing is not None:
        return existing
    return factory(name, *args, **kwargs)


def init_app_metrics() -> bool:
    """Idempotently create the application metric collectors. Returns True when
    Prometheus is available and the collectors are live."""
    global _http_requests, _http_latency, _llm_tokens, _celery_tasks
    global _ws_connections, _initialized

    if _initialized:
        return _PROM_AVAILABLE
    _initialized = True

    if not _PROM_AVAILABLE:
        logger.warning("prometheus_client unavailable — app metrics are a no-op")
        return False

    _http_requests = _get_or_create(
        Counter,
        "ib_http_requests_total",
        "Total HTTP requests handled by the API",
        ["method", "path", "status"],
    )
    _http_latency = _get_or_create(
        Histogram,
        "ib_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path"],
        buckets=_LATENCY_BUCKETS,
    )
    _llm_tokens = _get_or_create(
        Counter,
        "ib_llm_tokens_total",
        "LLM tokens consumed, split by prompt vs completion",
        ["model", "type"],
    )
    _celery_tasks = _get_or_create(
        Counter,
        "ib_celery_tasks_total",
        "Ingestion Celery tasks by name and outcome",
        ["task", "status"],
    )
    _ws_connections = _get_or_create(
        Gauge,
        "ib_active_ws_connections",
        "Currently open chat-stream WebSocket connections",
    )
    logger.info("Application Prometheus metrics initialized.")
    return True


def record_http_request(
    method: str, path: str, status: int, duration_seconds: float
) -> None:
    if _http_requests is None or _http_latency is None:
        return
    try:
        _http_requests.labels(method=method, path=path, status=str(status)).inc()
        _http_latency.labels(method=method, path=path).observe(duration_seconds)
    except Exception:  # never let metrics recording break a request
        pass


def record_llm_tokens(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    if _llm_tokens is None:
        return
    try:
        if prompt_tokens:
            _llm_tokens.labels(model=model, type="prompt").inc(prompt_tokens)
        if completion_tokens:
            _llm_tokens.labels(model=model, type="completion").inc(completion_tokens)
    except Exception:
        pass


def record_celery_task(task: str, status: str) -> None:
    if _celery_tasks is None:
        return
    try:
        _celery_tasks.labels(task=task, status=status).inc()
    except Exception:
        pass


def ws_connection_opened() -> None:
    if _ws_connections is None:
        return
    try:
        _ws_connections.inc()
    except Exception:
        pass


def ws_connection_closed() -> None:
    if _ws_connections is None:
        return
    try:
        _ws_connections.dec()
    except Exception:
        pass
