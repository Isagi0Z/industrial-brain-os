"""GraphRAG domain models (M8 — 8-Stage Hybrid Retrieval Pipeline, Stages 1-6).

HybridSearchResult is the DTO returned by IGraphRAGEngine.retrieve(), combining
BM25 + dense vector candidates (Stages 1-3) with KG traversal paths (Stage 4)
after GraphRAG synthesis (Stage 5) and cross-encoder reranking (Stage 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.domain.search.models import SearchResult


@dataclass
class KGPath:
    """A single relationship edge discovered during KG traversal (Stage 4)."""

    source_tag: str
    source_type: str
    relation_type: str
    target_tag: str
    target_type: str


@dataclass
class EntityMention:
    """An entity tag recognized in the user's query text."""

    tag_number: str
    entity_type: str


@dataclass
class RankedChunk:
    """A search result annotated with its cross-encoder rerank score."""

    result: SearchResult
    rerank_score: float


@dataclass
class HybridSearchResult:
    """Aggregated output of the hybrid retrieval pipeline (Stages 1-6)."""

    ranked_chunks: List[RankedChunk] = field(default_factory=list)
    kg_paths: List[KGPath] = field(default_factory=list)
    entity_mentions: List[EntityMention] = field(default_factory=list)
    total_candidates_before_rerank: int = 0
    rerank_latency_ms: float = 0.0

    def kg_paths_as_markdown(self) -> str:
        """Render kg_paths as a Markdown table (Engineering Bible §20 —
        unfiltered subgraphs must never be sent directly to the LLM)."""
        if not self.kg_paths:
            return ""
        lines = [
            "| Source | Relation | Target |",
            "| --- | --- | --- |",
        ]
        for p in self.kg_paths:
            lines.append(
                f"| {p.source_type}:{p.source_tag} | {p.relation_type} "
                f"| {p.target_type}:{p.target_tag} |"
            )
        return "\n".join(lines)
