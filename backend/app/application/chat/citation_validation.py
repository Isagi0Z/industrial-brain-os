"""Stage 8 — citation validation (M14, architecture §4).

Parses ``[source_N]`` markers from the LLM answer and resolves each to the
Nth retrieved chunk (1-based). Markers that do not resolve to a retrieved
chunk are "hallucinated": they are stripped from the answer and counted.
Returns the cleaned answer plus a ``CitationValidationReport`` carrying the
absolute source coordinates (document_id, page_number, bbox_json) of every
validated citation.

Resolution note: the retrieved chunks (and the ``Citation`` objects derived
from them) already carry their PostgreSQL-originated coordinates from the
retrieval pipeline, so ``[source_N]`` is resolved against the in-memory
ordered citation list rather than a redundant PostgreSQL round-trip
(ADR-001 — avoid blocking DB I/O on the hot path). The ordering of
``ordered_citations`` matches the ``[source_N]`` numbering assigned when the
context was assembled.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from app.domain.chat.models import (
    Citation,
    CitationValidationReport,
    ValidatedSource,
)

_SOURCE_MARKER = re.compile(r"\[source_(\d+)\]", re.IGNORECASE)

QUALITY_OK = "OK"
QUALITY_WARNING = "CITATION_WARNING"


def validate_citations(
    answer: str, ordered_citations: List[Citation]
) -> Tuple[str, CitationValidationReport]:
    """Return (cleaned_answer, report). Hallucinated ``[source_N]`` markers
    (N out of range) are removed from the answer and counted."""
    n = len(ordered_citations)
    validated: Dict[int, ValidatedSource] = {}
    hallucinated_count = 0

    def _replace(match: "re.Match[str]") -> str:
        nonlocal hallucinated_count
        idx = int(match.group(1))
        if 1 <= idx <= n:
            if idx not in validated:
                c = ordered_citations[idx - 1]
                validated[idx] = ValidatedSource(
                    source_index=idx,
                    chunk_id=c.chunk_id,
                    document_id=c.storage_key or "",
                    document_title=c.document_title,
                    page_number=c.page_number,
                    bbox_json=c.bbox_json,
                )
            return match.group(0)  # keep a valid marker in the answer
        hallucinated_count += 1
        return ""  # strip the hallucinated marker

    cleaned = _SOURCE_MARKER.sub(_replace, answer)

    validated_sources = [validated[k] for k in sorted(validated)]
    quality_flag = QUALITY_WARNING if hallucinated_count > 0 else QUALITY_OK
    report = CitationValidationReport(
        validated_count=len(validated_sources),
        hallucinated_count=hallucinated_count,
        quality_flag=quality_flag,
        validated_sources=validated_sources,
    )
    return cleaned, report
