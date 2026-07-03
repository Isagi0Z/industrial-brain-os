"""Prometheus HTTP metrics middleware (M17, ADR-017).

Records request count (with status) and latency for every HTTP request so the
Grafana "API Performance" dashboard can chart request rate, error rate, and
p50/p95/p99 latency. Uses the *matched route template* (e.g.
``/api/v1/documents/{document_id}``) as the ``path`` label rather than the
concrete URL, keeping label cardinality bounded (Engineering Bible §16). The
``/metrics`` scrape endpoint itself is skipped to avoid self-observation noise.

Recording is a no-op when ``prometheus_client`` is unavailable — the metric
helpers guard themselves — so this middleware never affects request handling.
"""

from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.observability.metrics import record_http_request


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/metrics"):
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            route = request.scope.get("route")
            # Prefer the route template; fall back to the raw path only when no
            # route matched (404s) — bounded because unmatched paths are rare.
            label_path = getattr(route, "path", None) or path
            record_http_request(request.method, label_path, status_code, duration)
