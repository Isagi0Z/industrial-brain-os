"""Pure RAG evaluation metric functions (M16, architecture §5).

Deterministic and side-effect-free — fully unit-tested with known inputs.
The retrieval/generation/judging happens in the runner; these functions only
score the results.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from app.domain.evaluation.models import ItemEvaluation
from app.domain.search.models import SearchResult


def _title_stem(title: str) -> str:
    """Filename stem, lowercased: "OEM-P102A-Manual.pdf" -> "oem-p102a-manual"."""
    stem = (title or "").rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    return stem.strip().lower()


def _matches_source(r: SearchResult, want: str, page: Optional[int]) -> bool:
    """One retrieved chunk vs one golden source slug.

    Slug matching: raw ``document_id`` (UUID-pinned datasets keep working) or
    the ``document_title`` filename stem, case-insensitive. Page matching:
    ±1 tolerance — the demo PDFs are regenerated on every seeding and their
    pagination can shift by a page without the fact moving documents.
    """
    doc_id = (r.document_id or "").strip().lower()
    if doc_id != want and _title_stem(r.document_title) != want:
        return False
    if page is None or r.page_number is None:
        return True
    return abs(r.page_number - page) <= 1


def first_golden_hit_rank(
    source_document_id: str,
    source_page: Optional[int],
    retrieved: Sequence[SearchResult],
    alternate_sources: Sequence[str] = (),
) -> Optional[int]:
    """1-based rank of the first retrieved chunk that comes from ANY golden
    source (canonical or alternate), or None when nothing hits.

    The demo corpus is intentionally redundant — the same fact often lives in
    an OEM manual, a JSON spec sheet, and an inspection report — so recall
    credits every document listed for the item, not one arbitrary canonical
    source. The page pin applies only to the canonical source; alternates
    match on document alone.
    """
    want = (source_document_id or "").strip().lower()
    alts = {(a or "").strip().lower() for a in alternate_sources if a}
    for rank, r in enumerate(retrieved, start=1):
        if _matches_source(r, want, source_page):
            return rank
        for alt in alts:
            if _matches_source(r, alt, None):
                return rank
    return None


def retrieval_recall_hit(
    source_document_id: str,
    source_page: Optional[int],
    retrieved: Sequence[SearchResult],
    alternate_sources: Sequence[str] = (),
) -> bool:
    """Recall@k for one item: True if any golden source appears among the
    retrieved chunks (see ``first_golden_hit_rank`` for matching rules)."""
    return (
        first_golden_hit_rank(
            source_document_id, source_page, retrieved, alternate_sources
        )
        is not None
    )


def mrr(ranks: Sequence[Optional[int]]) -> float:
    """Mean Reciprocal Rank over per-item first-hit ranks (None = miss = 0)."""
    if not ranks:
        return 0.0
    return round(sum(1.0 / r for r in ranks if r) / len(ranks), 4)


def ndcg_at_k(ranks: Sequence[Optional[int]]) -> float:
    """Binary-relevance nDCG over per-item first-hit ranks.

    With a single relevant document per query the ideal DCG is 1 (hit at
    rank 1), so per-item nDCG reduces to 1/log2(rank+1); misses score 0.
    """
    import math

    if not ranks:
        return 0.0
    total = sum(1.0 / math.log2(r + 1) for r in ranks if r)
    return round(total / len(ranks), 4)


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
