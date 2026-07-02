"""GraphRAG domain interfaces (ADR-013 — domain-agnostic, infra-free)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.domain.graphrag.models import (
    CompressionResult,
    HybridSearchResult,
    KGPath,
)
from app.domain.search.models import SearchResult


class IGraphRAGEngine(ABC):
    @abstractmethod
    async def retrieve(
        self, query: str, role_scope: str, top_k: int
    ) -> HybridSearchResult:
        """Run the full hybrid retrieval pipeline (Stages 1-7) for a query."""


class IContextCompressor(ABC):
    """Stage 7 (M14) — compress an assembled context string before the LLM
    call (e.g. LLMLingua). Implementations must degrade gracefully: if the
    backend is unavailable or the context is below the min-token threshold,
    return the input unchanged with ``was_compressed=False``."""

    @abstractmethod
    def compress(
        self, context: str, target_ratio: float, min_tokens: int
    ) -> CompressionResult:
        """Return a CompressionResult; never raises for the caller."""


class IKGTraversalService(ABC):
    @abstractmethod
    def traverse(self, tags: List[str], max_depth: int, limit: int) -> List[KGPath]:
        """Return relationship edges within max_depth hops of the given tags."""


class ICrossEncoderReranker(ABC):
    @abstractmethod
    def rerank(
        self, query: str, candidates: List[SearchResult]
    ) -> List[Tuple[SearchResult, float]]:
        """Score each candidate against the query; order is not guaranteed."""


class IGraphRAGCache(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[HybridSearchResult]:
        """Return the cached result for key, or None on miss/error."""

    @abstractmethod
    def set(self, key: str, result: HybridSearchResult, ttl_seconds: int) -> None:
        """Cache result under key for ttl_seconds."""
