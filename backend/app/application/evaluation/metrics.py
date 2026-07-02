"""Pure RAG evaluation metric functions (M16, architecture §5).

Deterministic and side-effect-free — fully unit-tested with known inputs.
The retrieval/generation/judging happens in the runner; these functions only
score the results.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from app.domain.evaluation.models import ItemEvaluation
from app.domain.search.models import SearchResult


def retrieval_recall_hit(
    source_document_id: str,
    source_page: Optional[int],
    retrieved: Sequence[SearchResult],
) -> bool:
    """Recall@k for one item: True if the golden source (document_id, and the
    page when specified) appears among the retrieved chunks."""
    for r in retrieved:
        if r.document_id == source_document_id:
            if source_page is None or r.page_number == source_page:
                return True
    return False


def context_precision(relevance_flags: Sequence[bool]) -> float:
    """Fraction of retrieved chunks judged relevant. 0.0 when nothing was
    retrieved (nothing relevant can be present)."""
    if not relevance_flags:
        return 0.0
    return round(sum(1 for f in relevance_flags if f) / len(relevance_flags), 4)


def aggregate(items: List[ItemEvaluation]) -> tuple:
    """Aggregate per-item outcomes into the run's four headline metrics:
    (retrieval_recall, context_precision, faithfulness, hallucination_rate)."""
    n = len(items)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    recall = round(sum(1 for i in items if i.recall_hit) / n, 4)
    precision = round(sum(i.context_precision for i in items) / n, 4)
    faithfulness = round(sum(1 for i in items if i.faithful) / n, 4)
    hallucination_rate = round(sum(1 for i in items if i.hallucinated) / n, 4)
    return recall, precision, faithfulness, hallucination_rate
