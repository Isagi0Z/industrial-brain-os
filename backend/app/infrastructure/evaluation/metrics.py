"""Prometheus metrics for the Evaluation Layer (M16, ADR-017).

Exposes three gauges — updated after every evaluation run — on the default
Prometheus registry so the (M17) Prometheus server can scrape them and the
`/metrics` endpoint can render them:

    ib_hallucination_rate   — fraction of golden answers citing a phantom source
    ib_faithfulness_score   — fraction of answers derivable from context only
    ib_retrieval_recall     — Recall@k over the golden dataset

Guarded so a missing ``prometheus_client`` degrades to a no-op recorder
rather than crashing the app (offline-safe, like the other optional deps).
"""

from __future__ import annotations

import logging

from app.domain.evaluation.interfaces import IMetricsRecorder
from app.domain.evaluation.models import EvaluationRun

logger = logging.getLogger(__name__)

try:
    import prometheus_client  # noqa: F401

    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover - prometheus_client is a declared dep
    _PROM_AVAILABLE = False


class PrometheusMetricsRecorder(IMetricsRecorder):
    def __init__(self) -> None:
        self._available = _PROM_AVAILABLE
        if not self._available:
            logger.warning("prometheus_client unavailable — metrics are a no-op")
            return
        # get_or_create so repeated construction (e.g. tests, reload) is safe.
        self._hallucination = _get_or_create_gauge(
            "ib_hallucination_rate",
            "Fraction of evaluation answers citing a non-retrieved source",
        )
        self._faithfulness = _get_or_create_gauge(
            "ib_faithfulness_score",
            "Fraction of evaluation answers derivable from retrieved context",
        )
        self._recall = _get_or_create_gauge(
            "ib_retrieval_recall",
            "Recall@k over the golden evaluation dataset",
        )

    def record(self, run: EvaluationRun) -> None:
        if not self._available:
            return
        self._hallucination.set(run.hallucination_rate)
        self._faithfulness.set(run.faithfulness)
        self._recall.set(run.retrieval_recall)


def _get_or_create_gauge(name: str, doc: str):
    """Return an existing gauge with this name or create it — avoids the
    'Duplicated timeseries' error when the recorder is built more than once."""
    from prometheus_client import REGISTRY, Gauge

    existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
    if existing is not None:
        return existing
    return Gauge(name, doc)
