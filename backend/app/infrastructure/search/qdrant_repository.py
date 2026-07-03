"""Qdrant vector repository — wraps qdrant-client with domain types."""

from __future__ import annotations

import logging
import time
from typing import Callable, List

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from app.domain.document.constants import ChunkType
from app.domain.search.interfaces import IVectorRepository
from app.domain.search.models import SearchResult
from app.infrastructure.observability.tracing import set_span_attributes, span

logger = logging.getLogger(__name__)


class QdrantVectorRepository(IVectorRepository):
    def __init__(self, get_client_fn: Callable[[], QdrantClient]) -> None:
        self._get_client = get_client_fn

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        client = self._get_client()
        existing = {c.name for c in client.get_collections().collections}
        if collection_name not in existing:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=vector_size,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection '%s' dim=%d", collection_name, vector_size
            )

    def upsert(
        self,
        collection_name: str,
        chunk_id: str,
        vector: List[float],
        payload: dict,
    ) -> None:
        self.batch_upsert(
            collection_name,
            [{"id": chunk_id, "vector": vector, "payload": payload}],
        )

    def batch_upsert(
        self,
        collection_name: str,
        points: List[dict],
    ) -> None:
        if not points:
            return
        client = self._get_client()
        qdrant_points = [
            qdrant_models.PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p["payload"],
            )
            for p in points
        ]
        client.upsert(collection_name=collection_name, points=qdrant_points)
        logger.debug("Upserted %d points into '%s'", len(points), collection_name)

    def search(
        self,
        collection_name: str,
        vector: List[float],
        role_scope: str,
        limit: int,
    ) -> List[SearchResult]:
        client = self._get_client()
        scope_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="role_scope",
                    match=qdrant_models.MatchValue(value=role_scope),
                )
            ]
        )
        t0 = time.monotonic()
        with span(
            "vector_db.search",
            **{"vector_db.collection": collection_name, "vector_db.top_k": limit},
        ):
            hits = client.search(
                collection_name=collection_name,
                query_vector=vector,
                query_filter=scope_filter,
                limit=limit,
                with_payload=True,
            )
            set_span_attributes(
                {
                    "vector_db.result_count": len(hits),
                    "vector_db.latency_ms": round((time.monotonic() - t0) * 1000, 1),
                }
            )
        results: List[SearchResult] = []
        for hit in hits:
            p = hit.payload or {}
            results.append(
                SearchResult(
                    chunk_id=str(hit.id),
                    document_id=p.get("document_id", ""),
                    document_title=p.get("document_title", ""),
                    chunk_type=ChunkType(p.get("chunk_type", "paragraph")),
                    text=p.get("text", ""),
                    page_number=p.get("page_number"),
                    parent_section_header=p.get("parent_section_header"),
                    bbox_json=p.get("bbox_json"),
                    score=float(hit.score),
                    role_scope=p.get("role_scope", role_scope),
                )
            )
        return results

    def delete_by_document(self, collection_name: str, document_id: str) -> None:
        client = self._get_client()
        client.delete(
            collection_name=collection_name,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="document_id",
                            match=qdrant_models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )
        logger.debug(
            "Deleted vectors for document %s from '%s'", document_id, collection_name
        )
