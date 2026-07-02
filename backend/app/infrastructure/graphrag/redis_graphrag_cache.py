"""Redis cache for GraphRAG hybrid search results (Engineering Bible §27 —
cache frequent queries using fast, local storage).

Keyed by the caller (hash of query + role_scope), 5-minute TTL set by
GraphRAGEngine.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

import redis

from app.domain.document.constants import ChunkType
from app.domain.graphrag.interfaces import IGraphRAGCache
from app.domain.graphrag.models import (
    CompressionResult,
    EntityMention,
    HybridSearchResult,
    KGPath,
    RankedChunk,
)
from app.domain.search.models import SearchResult

logger = logging.getLogger(__name__)


class RedisGraphRAGCache(IGraphRAGCache):
    def __init__(self, get_redis_fn: Callable[[], redis.Redis]) -> None:
        self._get_redis = get_redis_fn

    def get(self, key: str) -> Optional[HybridSearchResult]:
        try:
            raw = self._get_redis().get(key)
            if raw is None:
                return None
            return _deserialize(json.loads(raw))  # type: ignore[arg-type]
        except Exception as exc:
            logger.warning("GraphRAG cache read failed: %s", exc)
            return None

    def set(self, key: str, result: HybridSearchResult, ttl_seconds: int) -> None:
        try:
            payload = json.dumps(_serialize(result))
            self._get_redis().set(key, payload, ex=ttl_seconds)
        except Exception as exc:
            logger.warning("GraphRAG cache write failed: %s", exc)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize(result: HybridSearchResult) -> dict:
    return {
        "ranked_chunks": [
            {
                "rerank_score": rc.rerank_score,
                "result": {
                    "chunk_id": rc.result.chunk_id,
                    "document_id": rc.result.document_id,
                    "document_title": rc.result.document_title,
                    "chunk_type": rc.result.chunk_type.value,
                    "text": rc.result.text,
                    "page_number": rc.result.page_number,
                    "parent_section_header": rc.result.parent_section_header,
                    "bbox_json": rc.result.bbox_json,
                    "score": rc.result.score,
                    "role_scope": rc.result.role_scope,
                },
            }
            for rc in result.ranked_chunks
        ],
        "kg_paths": [
            {
                "source_tag": p.source_tag,
                "source_type": p.source_type,
                "relation_type": p.relation_type,
                "target_tag": p.target_tag,
                "target_type": p.target_type,
            }
            for p in result.kg_paths
        ],
        "entity_mentions": [
            {"tag_number": m.tag_number, "entity_type": m.entity_type}
            for m in result.entity_mentions
        ],
        "total_candidates_before_rerank": result.total_candidates_before_rerank,
        "rerank_latency_ms": result.rerank_latency_ms,
        "compressed_context": result.compressed_context,
        "compression": _serialize_compression(result.compression),
    }


def _serialize_compression(compression: Optional[CompressionResult]) -> Optional[dict]:
    if compression is None:
        return None
    return {
        "compressed_text": compression.compressed_text,
        "original_tokens": compression.original_tokens,
        "compressed_tokens": compression.compressed_tokens,
        "ratio": compression.ratio,
        "was_compressed": compression.was_compressed,
    }


def _deserialize_compression(data: Optional[dict]) -> Optional[CompressionResult]:
    if not data:
        return None
    return CompressionResult(
        compressed_text=data.get("compressed_text", ""),
        original_tokens=data.get("original_tokens", 0),
        compressed_tokens=data.get("compressed_tokens", 0),
        ratio=data.get("ratio", 1.0),
        was_compressed=data.get("was_compressed", False),
    )


def _deserialize(data: dict) -> HybridSearchResult:
    ranked_chunks = [
        RankedChunk(
            result=SearchResult(
                chunk_id=rc["result"]["chunk_id"],
                document_id=rc["result"]["document_id"],
                document_title=rc["result"]["document_title"],
                chunk_type=ChunkType(rc["result"]["chunk_type"]),
                text=rc["result"]["text"],
                page_number=rc["result"]["page_number"],
                parent_section_header=rc["result"]["parent_section_header"],
                bbox_json=rc["result"]["bbox_json"],
                score=rc["result"]["score"],
                role_scope=rc["result"]["role_scope"],
            ),
            rerank_score=rc["rerank_score"],
        )
        for rc in data.get("ranked_chunks", [])
    ]
    kg_paths = [
        KGPath(
            source_tag=p["source_tag"],
            source_type=p["source_type"],
            relation_type=p["relation_type"],
            target_tag=p["target_tag"],
            target_type=p["target_type"],
        )
        for p in data.get("kg_paths", [])
    ]
    entity_mentions = [
        EntityMention(tag_number=m["tag_number"], entity_type=m["entity_type"])
        for m in data.get("entity_mentions", [])
    ]
    return HybridSearchResult(
        ranked_chunks=ranked_chunks,
        kg_paths=kg_paths,
        entity_mentions=entity_mentions,
        total_candidates_before_rerank=data.get("total_candidates_before_rerank", 0),
        rerank_latency_ms=data.get("rerank_latency_ms", 0.0),
        compressed_context=data.get("compressed_context", ""),
        compression=_deserialize_compression(data.get("compression")),
    )
