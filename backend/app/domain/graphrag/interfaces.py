"""GraphRAG domain interfaces (ADR-013 — domain-agnostic, infra-free)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.domain.graphrag.models import HybridSearchResult, KGPath
from app.domain.search.models import SearchResult


class IGraphRAGEngine(ABC):
    @abstractmethod
    async def retrieve(
        self, query: str, role_scope: str, top_k: int
    ) -> HybridSearchResult:
        """Run the full hybrid retrieval pipeline (Stages 1-6) for a query."""


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
