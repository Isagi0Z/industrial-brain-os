"""GraphRAGEngine — orchestrates Stages 1-6 of the 8-stage hybrid retrieval
pipeline (architecture §4, ADR-008, ADR-009).

Pipeline:
  Stages 1-3 (BM25 + metadata filter + dense vector) and Stage 4 (KG
  traversal) run concurrently via asyncio.gather. Stage 5 (GraphRAG
  synthesis: dedupe + merge candidates) and Stage 6 (cross-encoder
  reranking) run sequentially afterward.

Results are cached in Redis keyed by hash(query + role_scope) with a
5-minute TTL (Engineering Bible §27). Token budget is enforced after
reranking — chunks beyond the configured budget are discarded rather than
truncated mid-text (Engineering Bible §20).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from starlette.concurrency import run_in_threadpool

from app.application.search.embedding_use_case import EmbeddingUseCase
from app.domain.document.constants import ChunkType
from app.domain.document.models import DocumentChunk
from app.domain.extraction.interfaces import IEntityExtractor
from app.domain.extraction.models import ExtractedEntity
from app.domain.graphrag.interfaces import (
    ICrossEncoderReranker,
    IGraphRAGCache,
    IGraphRAGEngine,
    IKGTraversalService,
)
from app.domain.graphrag.models import EntityMention, HybridSearchResult, RankedChunk
from app.domain.search.models import SearchResult

logger = logging.getLogger(__name__)

_MAX_KG_DEPTH = 2  # ADR-004 mitigation — hardcoded traversal depth limit
_KG_TRAVERSAL_LIMIT = 50
_TOKEN_BUDGET = 6000
_APPROX_CHARS_PER_TOKEN = 4
_CACHE_TTL_SECONDS = 300  # 5 minutes


class GraphRAGEngine(IGraphRAGEngine):
    def __init__(
        self,
        embedding_use_case: EmbeddingUseCase,
        entity_extractor: IEntityExtractor,
        kg_traversal: IKGTraversalService,
        reranker: ICrossEncoderReranker,
        cache: IGraphRAGCache,
        token_budget: int = _TOKEN_BUDGET,
        cache_ttl_seconds: int = _CACHE_TTL_SECONDS,
        max_kg_depth: int = _MAX_KG_DEPTH,
        kg_traversal_limit: int = _KG_TRAVERSAL_LIMIT,
    ) -> None:
        self._embedding_uc = embedding_use_case
        self._entity_extractor = entity_extractor
        self._kg_traversal = kg_traversal
        self._reranker = reranker
        self._cache = cache
        self._token_budget = token_budget
        self._cache_ttl = cache_ttl_seconds
        self._max_kg_depth = max_kg_depth
        self._kg_limit = kg_traversal_limit

    async def retrieve(
        self, query: str, role_scope: str, top_k: int
    ) -> HybridSearchResult:
        cache_key = _cache_key(query, role_scope)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("GraphRAG cache hit", extra={"cache_key": cache_key})
            return cached

        t0 = time.monotonic()

        bm25_task = self._embedding_uc.search_keyword(query, role_scope, top_k * 2)
        vector_task = self._embedding_uc.search_semantic(query, role_scope, top_k * 2)
        kg_task = run_in_threadpool(self._traverse_kg, query)

        bm25_results, vector_results, (kg_paths, entity_mentions) = (
            await asyncio.gather(bm25_task, vector_task, kg_task)
        )

        merged = _merge_candidates(bm25_results, vector_results)
        total_before_rerank = len(merged)

        reranked = await run_in_threadpool(self._reranker.rerank, query, merged)
        reranked.sort(key=lambda pair: pair[1], reverse=True)

        ranked_chunks = _apply_token_budget(reranked, self._token_budget)

        rerank_latency_ms = (time.monotonic() - t0) * 1000.0

        result = HybridSearchResult(
            ranked_chunks=ranked_chunks,
            kg_paths=kg_paths,
            entity_mentions=entity_mentions,
            total_candidates_before_rerank=total_before_rerank,
            rerank_latency_ms=round(rerank_latency_ms, 1),
        )

        self._cache.set(cache_key, result, self._cache_ttl)
        return result

    # ------------------------------------------------------------------
    # Stage 4 — KG traversal
    # ------------------------------------------------------------------

    def _traverse_kg(self, query: str) -> Tuple[List, List[EntityMention]]:
        entities = self._extract_query_entities(query)
        if not entities:
            return [], []
        tags = [e.tag_number for e in entities if e.tag_number]
        paths = self._kg_traversal.traverse(tags, self._max_kg_depth, self._kg_limit)
        mentions = [
            EntityMention(tag_number=e.tag_number, entity_type=e.entity_type)
            for e in entities
            if e.tag_number
        ]
        return paths, mentions

    def _extract_query_entities(self, query: str) -> List[ExtractedEntity]:
        chunk = DocumentChunk(
            id="query",
            document_id="query",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text=query,
            page_number=None,
            parent_section_header=None,
            bbox_json=None,
            token_count=len(query.split()),
            created_at=datetime.now(timezone.utc),
            table_data_json=None,
            figure_storage_key=None,
        )
        entities = self._entity_extractor.extract(chunk)
        seen: set = set()
        deduped: List[ExtractedEntity] = []
        for e in entities:
            if e.tag_number and e.tag_number not in seen:
                seen.add(e.tag_number)
                deduped.append(e)
        return deduped


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _cache_key(query: str, role_scope: str) -> str:
    digest = hashlib.sha256(f"{query}|{role_scope}".encode("utf-8")).hexdigest()
    return f"graphrag:cache:{digest}"


def _merge_candidates(
    bm25_results: List[SearchResult], vector_results: List[SearchResult]
) -> List[SearchResult]:
    """Stage 5 — dedupe by chunk_id, keeping the higher-scoring candidate."""
    merged: Dict[str, SearchResult] = {}
    for r in bm25_results + vector_results:
        existing = merged.get(r.chunk_id)
        if existing is None or r.score > existing.score:
            merged[r.chunk_id] = r
    return list(merged.values())


def _apply_token_budget(
    reranked: List[Tuple[SearchResult, float]], token_budget: int
) -> List[RankedChunk]:
    ranked_chunks: List[RankedChunk] = []
    remaining = token_budget
    for result, score in reranked:
        approx_tokens = len(result.text) // _APPROX_CHARS_PER_TOKEN
        if approx_tokens > remaining:
            break
        ranked_chunks.append(RankedChunk(result=result, rerank_score=score))
        remaining -= approx_tokens
    return ranked_chunks
