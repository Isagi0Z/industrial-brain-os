"""OpenTelemetry tracing (M17, ADR-016).

Initializes an OTLP/HTTP exporter (Jaeger's collector speaks OTLP on 4318)
and auto-instruments FastAPI. Hot-path components (LLM gateways, Qdrant
search, Neo4j traversal, Celery tasks) create spans through the ``span``
helper below, which:

- attaches the request Correlation-ID (the logging contextvar) to every
  span so traces and structured logs join on the same id (Engineering
  Bible §16);
- is a **no-op** when OpenTelemetry is not installed or ``OTEL_ENABLED``
  is false — the same guarded-degradation pattern as every other optional
  runtime in this codebase, so tracing can never break the pipeline;
- must never receive sensitive values (tokens, passwords, raw user
  queries) as attributes — callers pass sizes/ids/latencies only
  (Engineering Bible §16).

The project intentionally has no SQLAlchemy, so the checklist's
``opentelemetry-instrumentation-sqlalchemy`` is replaced by spans at our
own repository/service wrappers (documented deviation in the M17
walkthrough).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

_TRACER = None  # set by init_tracing when OTel is available + enabled

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - otel is a declared dependency
    _OTEL_AVAILABLE = False


def init_tracing(app: Optional[Any] = None) -> bool:
    """Initialize the tracer provider + OTLP exporter and (optionally)
    auto-instrument a FastAPI app. Returns True when tracing is live."""
    global _TRACER
    from app.infrastructure.config.settings import settings

    if not settings.OTEL_ENABLED:
        logger.info("OTel tracing disabled (OTEL_ENABLED=false).")
        return False
    if not _OTEL_AVAILABLE:
        logger.warning("OTel SDK unavailable — tracing is a no-op.")
        return False

    try:
        resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=f"{settings.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces"
                )
            )
        )
        _otel_trace.set_tracer_provider(provider)
        _TRACER = _otel_trace.get_tracer("industrial-brain")

        if app is not None:
            try:
                from opentelemetry.instrumentation.fastapi import (
                    FastAPIInstrumentor,
                )

                FastAPIInstrumentor.instrument_app(app)
            except Exception as exc:
                logger.warning("FastAPI OTel instrumentation skipped: %s", exc)

        logger.info(
            "OTel tracing initialized",
            extra={"otlp_endpoint": settings.OTEL_EXPORTER_OTLP_ENDPOINT},
        )
        return True
    except Exception as exc:
        logger.warning("OTel tracing init failed — no-op: %s", exc)
        _TRACER = None
        return False


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """Create a span carrying the Correlation-ID plus the given attributes.
    No-op when tracing is not initialized. Callers must not pass sensitive
    values (tokens, passwords, raw query text) as attributes."""
    if _TRACER is None:
        yield
        return
    from app.infrastructure.logging.logger import correlation_id_ctx

    with _TRACER.start_as_current_span(name) as sp:
        try:
            sp.set_attribute("correlation_id", correlation_id_ctx.get())
            for key, value in attributes.items():
                if value is not None:
                    sp.set_attribute(key, value)
        except Exception:  # never let attribute errors break the caller
            pass
        yield


def set_span_attributes(attributes: Dict[str, Any]) -> None:
    """Attach attributes to the current span (post-call results such as
    token counts / latency). No-op without an active recording span."""
    if _TRACER is None:
        return
    try:
        current = _otel_trace.get_current_span()
        if current is not None and current.is_recording():
            for key, value in attributes.items():
                if value is not None:
                    current.set_attribute(key, value)
    except Exception:
        pass


def current_trace_id() -> Optional[str]:
    """Hex trace id of the active span (for log correlation), or None."""
    if _TRACER is None:
        return None
    try:
        ctx = _otel_trace.get_current_span().get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None
