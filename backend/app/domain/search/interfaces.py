"""Search domain interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.domain.document.models import DocumentChunk
from app.domain.search.models import SearchResult


class IEmbeddingService(ABC):
    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Return 1024-dim embedding vectors for each text."""

    @abstractmethod
    def embed_one(self, text: str) -> List[float]:
        """Return 1024-dim embedding vector for a single text."""


class IVectorRepository(ABC):
    @abstractmethod
    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        """Create Qdrant collection if it does not exist."""

    @abstractmethod
    def upsert(
        self,
        collection_name: str,
        chunk_id: str,
        vector: List[float],
        payload: dict,
    ) -> None:
        """Idempotent upsert of a single vector point."""

    @abstractmethod
    def batch_upsert(
        self,
        collection_name: str,
        points: List[dict],
    ) -> None:
        """Idempotent batch upsert. Each dict: {id, vector, payload}."""

    @abstractmethod
    def search(
        self,
        collection_name: str,
        vector: List[float],
        role_scope: str,
        limit: int,
    ) -> List[SearchResult]:
        """Return top-k semantically similar chunks filtered by role_scope."""

    @abstractmethod
    def delete_by_document(self, collection_name: str, document_id: str) -> None:
        """Remove all vectors for a document (for re-ingestion idempotency)."""


class IBM25Repository(ABC):
    @abstractmethod
    def build_index(
        self,
        document_id: str,
        chunks: List[DocumentChunk],
        role_scope: str,
    ) -> None:
        """Build (or rebuild) the BM25 index for all chunks of a document."""

    @abstractmethod
    def search(
        self,
        query: str,
        role_scope: str,
        limit: int,
    ) -> List[SearchResult]:
        """Return top-k BM25-ranked chunks within role_scope."""

    @abstractmethod
    def delete_by_document(self, document_id: str) -> None:
        """Remove BM25 index entries for a document."""
