"""M17 observability unit tests.

Covers the two guarantees the observability layer must uphold:
  1. the metric recorders and tracer degrade to safe no-ops (never raise),
     mirroring the offline-safe pattern verified for the M16 recorder; and
  2. when Prometheus is available, the application collectors are created and
     the recorders actually move the underlying counters/gauges.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def metrics_module():
    """Fresh import of the metrics module with app collectors initialized."""
    from app.infrastructure.observability import metrics as m

    importlib.reload(m)
    m.init_app_metrics()
    return m


def _sample(name: str, labels: dict) -> float:
    from prometheus_client import REGISTRY

    value = REGISTRY.get_sample_value(name, labels)
    return value if value is not None else 0.0


def test_init_app_metrics_idempotent(metrics_module):
    # Second init must not raise a duplicate-timeseries error.
    assert metrics_module.init_app_metrics() is True
    assert metrics_module.init_app_metrics() is True


def test_record_http_request_increments_counter(metrics_module):
    labels = {"method": "GET", "path": "/api/v1/health", "status": "200"}
    before = _sample("ib_http_requests_total", labels)
    metrics_module.record_http_request("GET", "/api/v1/health", 200, 0.012)
    after = _sample("ib_http_requests_total", labels)
    assert after == before + 1


def test_record_llm_tokens_splits_prompt_and_completion(metrics_module):
    p_before = _sample(
        "ib_llm_tokens_total", {"model": "ollama/llama3.2", "type": "prompt"}
    )
    c_before = _sample(
        "ib_llm_tokens_total", {"model": "ollama/llama3.2", "type": "completion"}
    )
    metrics_module.record_llm_tokens("ollama/llama3.2", 30, 12)
    p_after = _sample(
        "ib_llm_tokens_total", {"model": "ollama/llama3.2", "type": "prompt"}
    )
    c_after = _sample(
        "ib_llm_tokens_total", {"model": "ollama/llama3.2", "type": "completion"}
    )
    assert p_after == p_before + 30
    assert c_after == c_before + 12


def test_ws_connection_gauge_inc_dec(metrics_module):
    before = _sample("ib_active_ws_connections", {})
    metrics_module.ws_connection_opened()
    assert _sample("ib_active_ws_connections", {}) == before + 1
    metrics_module.ws_connection_closed()
    assert _sample("ib_active_ws_connections", {}) == before


def test_record_celery_task_counter(metrics_module):
    labels = {"task": "parse_task", "status": "succeeded"}
    before = _sample("ib_celery_tasks_total", labels)
    metrics_module.record_celery_task("parse_task", "succeeded")
    assert _sample("ib_celery_tasks_total", labels) == before + 1


def test_recorders_are_noop_before_init(monkeypatch):
    """Calling recorders when collectors are unset must never raise."""
    from app.infrastructure.observability import metrics as m

    importlib.reload(m)  # collectors are None until init_app_metrics()
    # None of these should raise despite collectors being uninitialized.
    m.record_http_request("GET", "/", 200, 0.01)
    m.record_llm_tokens("x", 1, 1)
    m.record_celery_task("t", "started")
    m.ws_connection_opened()
    m.ws_connection_closed()


def test_span_is_noop_without_tracer():
    """The tracing.span() context manager is a no-op until init_tracing runs
    (OTEL_ENABLED is False by default), so it must yield without error and
    current_trace_id() returns None."""
    from app.infrastructure.observability import tracing as t

    with t.span("test.span", **{"attr": 1}):
        pass
    assert t.current_trace_id() is None
    # set_span_attributes without an active span must also be a silent no-op.
    t.set_span_attributes({"k": "v"})
