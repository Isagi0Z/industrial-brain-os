"""Evaluation Layer domain models (M16 — architecture §5).

A golden dataset of QA pairs is run through the retrieval + generation
pipeline; each item yields an ItemEvaluation, and the run aggregates them
into an EvaluationRun with the four headline RAG metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class GoldenQAItem:
    """One golden question with its known answer + source coordinates."""

    question: str
    expected_answer: str
    source_document_id: str
    source_page: Optional[int]
    expected_entity_mentions: List[str] = field(default_factory=list)
    category: str = "general"


@dataclass
class ItemEvaluation:
    """Per-question evaluation outcome."""

    question: str
    category: str
    recall_hit: bool  # golden source appeared in the top-k retrieved chunks
    context_precision: float  # fraction of retrieved chunks judged relevant
    faithful: bool  # answer derivable from retrieved context only
    hallucinated: bool  # response cited a non-retrieved source (M14 signal)
    retrieved_count: int


@dataclass
class EvaluationRun:
    """Aggregated result of one evaluation pass over the golden dataset."""

    run_id: str
    retrieval_recall: float
    context_precision: float
    faithfulness: float
    hallucination_rate: float
    total_items: int
    run_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    items: List[ItemEvaluation] = field(default_factory=list)
