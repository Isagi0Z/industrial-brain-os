"""Evaluation Layer domain interfaces (M16, ADR-013 — domain-agnostic)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.evaluation.models import EvaluationRun


class IEvaluationJudge(ABC):
    """LLM-as-a-judge (architecture §5). Implementations wrap the model
    gateway + version-controlled prompts; both methods must degrade to a
    conservative default rather than raise, so a judge outage never crashes
    an evaluation run."""

    @abstractmethod
    async def judge_faithfulness(self, answer: str, context: str) -> bool:
        """True if `answer` is derivable from `context` only (not from the
        model's prior knowledge)."""

    @abstractmethod
    async def judge_relevance(self, chunk_text: str, expected_answer: str) -> bool:
        """True if `chunk_text` is relevant to answering the question (used
        for context precision)."""


class IEvaluationRepository(ABC):
    @abstractmethod
    def save(self, run: EvaluationRun) -> None:
        """Persist an evaluation run (metrics + timestamp)."""

    @abstractmethod
    def get_latest(self) -> Optional[EvaluationRun]:
        """Return the most recent evaluation run, or None if none exist."""


class IMetricsRecorder(ABC):
    """Publishes evaluation metrics to a monitoring backend (Prometheus).
    Kept behind a port so the application layer never imports the metrics
    client (ADR-013)."""

    @abstractmethod
    def record(self, run: EvaluationRun) -> None:
        """Update the exported gauges from a completed run."""
