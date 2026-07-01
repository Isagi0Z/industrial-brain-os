"""Unit and integration tests for M8 — GraphRAG Engine (Hybrid Retrieval
Pipeline, Stages 1-6).

All external dependencies (Qdrant, PostgreSQL, Neo4j, Redis, the reranker
model) are mocked in unit tests. Integration tests use the real Docker
Compose services and are marked @pytest.mark.integration.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.domain.document.constants import ChunkType
from app.domain.graphrag.models import (
    EntityMention,
    HybridSearchResult,
    KGPath,
    RankedChunk,
)
from app.domain.search.models import SearchResult

try:
    import spacy as _spacy_check  # noqa: F401

    _SPACY_AVAILABLE = True
except ModuleNotFoundError:
    _SPACY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(timezone.utc)


def _search_result(
    chunk_id: str | None = None,
    text: str = "pump maintenance procedure",
    score: float = 0.5,
    document_title: str = "Manual",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id or str(uuid.uuid4()),
        document_id="doc-1",
        document_title=document_title,
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=1,
        parent_section_header=None,
        bbox_json=None,
        score=score,
        role_scope="public",
    )


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class TestHybridSearchResultMarkdown:
    def test_empty_kg_paths_returns_empty_string(self):
        result = HybridSearchResult()
        assert result.kg_paths_as_markdown() == ""

    def test_single_path_renders_table(self):
        result = HybridSearchResult(
            kg_paths=[
                KGPath(
                    source_tag="FT-101",
                    source_type="Sensor",
                    relation_type="MONITORS",
                    target_tag="P-102A",
                    target_type="Equipment",
                )
            ]
        )
        md = result.kg_paths_as_markdown()
        assert "| Source | Relation | Target |" in md
        assert "Sensor:FT-101" in md
        assert "MONITORS" in md
        assert "Equipment:P-102A" in md

    def test_multiple_paths_each_on_own_row(self):
        result = HybridSearchResult(
            kg_paths=[
                KGPath("FT-101", "Sensor", "MONITORS", "P-102A", "Equipment"),
                KGPath("P-102A", "Equipment", "IS_PART_OF", "TRAIN-1", "Asset"),
            ]
        )
        md = result.kg_paths_as_markdown()
        assert md.count("\n") == 3  # header + separator + 2 rows - 1 newlines


# ---------------------------------------------------------------------------
# GraphRAGEngine — merge / token-budget / cache-key helpers
# ---------------------------------------------------------------------------


class TestMergeCandidates:
    def test_dedup_by_chunk_id_keeps_higher_score(self):
        from app.application.graphrag.graphrag_engine import _merge_candidates

        shared_id = str(uuid.uuid4())
        low = _search_result(chunk_id=shared_id, score=0.3)
        high = _search_result(chunk_id=shared_id, score=0.9)

        merged = _merge_candidates([low], [high])
        assert len(merged) == 1
        assert merged[0].score == pytest.approx(0.9)

    def test_distinct_ids_both_kept(self):
        from app.application.graphrag.graphrag_engine import _merge_candidates

        a = _search_result(score=0.5)
        b = _search_result(score=0.6)

        merged = _merge_candidates([a], [b])
        assert len(merged) == 2

    def test_empty_inputs(self):
        from app.application.graphrag.graphrag_engine import _merge_candidates

        assert _merge_candidates([], []) == []


class TestApplyTokenBudget:
    def test_all_chunks_fit_within_budget(self):
        from app.application.graphrag.graphrag_engine import _apply_token_budget

        pairs = [(_search_result(text="short text"), 0.9)]
        ranked = _apply_token_budget(pairs, token_budget=6000)
        assert len(ranked) == 1
        assert isinstance(ranked[0], RankedChunk)

    def test_chunk_exceeding_budget_is_discarded(self):
        from app.application.graphrag.graphrag_engine import _apply_token_budget

        huge_text = "x " * 5000  # ~2500 approx tokens at 4 chars/token
        pairs = [(_search_result(text=huge_text), 0.9)]
        ranked = _apply_token_budget(pairs, token_budget=100)
        assert ranked == []

    def test_stops_at_first_chunk_that_overflows(self):
        from app.application.graphrag.graphrag_engine import _apply_token_budget

        small = _search_result(text="ok", score=0.9)
        huge = _search_result(text="x " * 5000, score=0.8)
        another_small = _search_result(text="ok2", score=0.7)

        pairs = [(small, 0.9), (huge, 0.8), (another_small, 0.7)]
        ranked = _apply_token_budget(pairs, token_budget=100)
        assert len(ranked) == 1
        assert ranked[0].result is small

    def test_preserves_rerank_score(self):
        from app.application.graphrag.graphrag_engine import _apply_token_budget

        pairs = [(_search_result(text="ok"), 0.42)]
        ranked = _apply_token_budget(pairs, token_budget=6000)
        assert ranked[0].rerank_score == pytest.approx(0.42)


class TestCacheKey:
    def test_same_query_and_scope_produce_same_key(self):
        from app.application.graphrag.graphrag_engine import _cache_key

        k1 = _cache_key("pump pressure", "public")
        k2 = _cache_key("pump pressure", "public")
        assert k1 == k2

    def test_different_query_produces_different_key(self):
        from app.application.graphrag.graphrag_engine import _cache_key

        k1 = _cache_key("pump pressure", "public")
        k2 = _cache_key("valve pressure", "public")
        assert k1 != k2

    def test_different_role_scope_produces_different_key(self):
        from app.application.graphrag.graphrag_engine import _cache_key

        k1 = _cache_key("pump pressure", "public")
        k2 = _cache_key("pump pressure", "engineering")
        assert k1 != k2

    def test_key_has_stable_prefix(self):
        from app.application.graphrag.graphrag_engine import _cache_key

        assert _cache_key("x", "public").startswith("graphrag:cache:")


# ---------------------------------------------------------------------------
# GraphRAGEngine — full orchestration (mocked deps)
# ---------------------------------------------------------------------------


def _make_engine(
    bm25_results=None,
    vector_results=None,
    kg_paths=None,
    entity_mentions=None,
    reranked_scores=None,
    cache_hit=None,
):
    from app.application.graphrag.graphrag_engine import GraphRAGEngine

    embedding_uc = MagicMock()

    async def _bm25(*a, **kw):
        return bm25_results or []

    async def _vector(*a, **kw):
        return vector_results or []

    embedding_uc.search_keyword = _bm25
    embedding_uc.search_semantic = _vector

    entity_extractor = MagicMock()
    entity_extractor.extract.return_value = []

    kg_traversal = MagicMock()
    kg_traversal.traverse.return_value = kg_paths or []

    reranker = MagicMock()

    def _rerank(query, candidates):
        if reranked_scores is not None:
            return list(zip(candidates, reranked_scores))
        return [(c, c.score) for c in candidates]

    reranker.rerank = _rerank

    cache = MagicMock()
    cache.get.return_value = cache_hit
    cache.set.return_value = None

    engine = GraphRAGEngine(
        embedding_use_case=embedding_uc,
        entity_extractor=entity_extractor,
        kg_traversal=kg_traversal,
        reranker=reranker,
        cache=cache,
    )
    return engine, embedding_uc, entity_extractor, kg_traversal, reranker, cache


class TestGraphRAGEngineRetrieve:
    def test_cache_hit_returns_cached_result_without_pipeline(self):
        cached = HybridSearchResult(total_candidates_before_rerank=99)
        engine, _, _, kg_traversal, _, cache = _make_engine(cache_hit=cached)

        result = asyncio.run(engine.retrieve("query", "public", 5))

        assert result is cached
        kg_traversal.traverse.assert_not_called()

    def test_cache_miss_runs_full_pipeline_and_caches(self):
        r1 = _search_result(text="bm25 hit", score=0.4)
        r2 = _search_result(text="vector hit", score=0.7)
        engine, _, _, _, _, cache = _make_engine(bm25_results=[r1], vector_results=[r2])

        result = asyncio.run(engine.retrieve("pump pressure", "public", 5))

        assert result.total_candidates_before_rerank == 2
        assert len(result.ranked_chunks) == 2
        cache.set.assert_called_once()

    def test_merged_candidates_deduped_across_bm25_and_vector(self):
        shared_id = str(uuid.uuid4())
        r1 = _search_result(chunk_id=shared_id, text="same chunk", score=0.4)
        r2 = _search_result(chunk_id=shared_id, text="same chunk", score=0.8)
        engine, *_ = _make_engine(bm25_results=[r1], vector_results=[r2])

        result = asyncio.run(engine.retrieve("query", "public", 5))

        assert result.total_candidates_before_rerank == 1

    def test_ranked_chunks_sorted_by_rerank_score_descending(self):
        r1 = _search_result(text="low", score=0.1)
        r2 = _search_result(text="high", score=0.1)
        engine, *_ = _make_engine(bm25_results=[r1, r2], reranked_scores=[0.2, 0.9])

        result = asyncio.run(engine.retrieve("query", "public", 5))

        scores = [rc.rerank_score for rc in result.ranked_chunks]
        assert scores == sorted(scores, reverse=True)

    def test_kg_paths_empty_when_no_entities_extracted(self):
        engine, _, entity_extractor, kg_traversal, _, _ = _make_engine()
        entity_extractor.extract.return_value = []

        result = asyncio.run(engine.retrieve("no tags here", "public", 5))

        assert result.kg_paths == []
        kg_traversal.traverse.assert_not_called()

    def test_kg_paths_populated_when_entities_extracted(self):
        from app.domain.extraction.models import ExtractedEntity

        engine, _, entity_extractor, kg_traversal, _, _ = _make_engine(
            kg_paths=[KGPath("FT-101", "Sensor", "MONITORS", "P-102A", "Equipment")]
        )
        entity_extractor.extract.return_value = [
            ExtractedEntity(
                text="FT-101",
                entity_type="Sensor",
                chunk_id="query",
                tag_number="FT-101",
            )
        ]

        result = asyncio.run(
            engine.retrieve("What sensors monitor pump P-102A?", "public", 5)
        )

        kg_traversal.traverse.assert_called_once()
        called_tags = kg_traversal.traverse.call_args[0][0]
        assert "FT-101" in called_tags
        assert len(result.kg_paths) == 1
        assert result.entity_mentions == [
            EntityMention(tag_number="FT-101", entity_type="Sensor")
        ]

    def test_duplicate_tags_deduped_before_traversal(self):
        from app.domain.extraction.models import ExtractedEntity

        engine, _, entity_extractor, kg_traversal, _, _ = _make_engine()
        entity_extractor.extract.return_value = [
            ExtractedEntity(
                text="FT-101", entity_type="Sensor", chunk_id="q", tag_number="FT-101"
            ),
            ExtractedEntity(
                text="FT-101", entity_type="Sensor", chunk_id="q", tag_number="FT-101"
            ),
        ]

        asyncio.run(engine.retrieve("FT-101 FT-101", "public", 5))

        called_tags = kg_traversal.traverse.call_args[0][0]
        assert called_tags == ["FT-101"]

    def test_empty_candidates_returns_empty_ranked_chunks(self):
        engine, *_ = _make_engine()
        result = asyncio.run(engine.retrieve("nothing matches", "public", 5))
        assert result.ranked_chunks == []
        assert result.total_candidates_before_rerank == 0


# ---------------------------------------------------------------------------
# CrossEncoderReranker
# ---------------------------------------------------------------------------


class TestCrossEncoderReranker:
    def test_empty_candidates_returns_empty_list(self):
        from app.infrastructure.graphrag.cross_encoder_reranker import (
            CrossEncoderReranker,
        )

        reranker = CrossEncoderReranker()
        assert reranker.rerank("query", []) == []

    def test_unavailable_model_passes_through_original_scores(self, monkeypatch):
        import app.infrastructure.graphrag.cross_encoder_reranker as mod

        monkeypatch.setattr(mod, "_RERANKER_AVAILABLE", False)
        reranker = mod.CrossEncoderReranker()

        candidates = [_search_result(score=0.3), _search_result(score=0.7)]
        results = reranker.rerank("query", candidates)

        assert len(results) == 2
        assert {score for _, score in results} == {0.3, 0.7}

    def test_available_model_uses_predict_scores(self, monkeypatch):
        import app.infrastructure.graphrag.cross_encoder_reranker as mod

        fake_model = MagicMock()
        fake_model.predict.return_value = [0.95, 0.05]

        monkeypatch.setattr(mod, "_RERANKER_AVAILABLE", True)
        monkeypatch.setattr(mod, "_get_model", lambda name: fake_model)

        reranker = mod.CrossEncoderReranker()
        candidates = [_search_result(text="a"), _search_result(text="b")]
        results = reranker.rerank("query", candidates)

        assert [score for _, score in results] == [0.95, 0.05]
        fake_model.predict.assert_called_once()


# ---------------------------------------------------------------------------
# Neo4jKGTraversalService
# ---------------------------------------------------------------------------


class TestNeo4jKGTraversalService:
    def _mock_driver_with_records(self, records_by_tag):
        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = lambda s: session
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        def _run(query, tag, max_level, limit):
            rows = records_by_tag.get(tag, [])
            return rows

        session.run.side_effect = _run
        return driver, session

    def test_maps_records_to_kg_paths(self):
        from app.infrastructure.graphrag.neo4j_kg_traversal import (
            Neo4jKGTraversalService,
        )

        record = {
            "source_tag": "FT-101",
            "source_type": "Sensor",
            "relation_type": "MONITORS",
            "target_tag": "P-102A",
            "target_type": "Equipment",
        }
        driver, _ = self._mock_driver_with_records({"FT-101": [record]})

        service = Neo4jKGTraversalService(driver)
        paths = service.traverse(["FT-101"], max_depth=2, limit=50)

        assert len(paths) == 1
        assert paths[0].source_tag == "FT-101"
        assert paths[0].relation_type == "MONITORS"
        assert paths[0].target_tag == "P-102A"

    def test_skips_records_with_missing_tags(self):
        from app.infrastructure.graphrag.neo4j_kg_traversal import (
            Neo4jKGTraversalService,
        )

        record = {
            "source_tag": None,
            "source_type": "Sensor",
            "relation_type": "MONITORS",
            "target_tag": "P-102A",
            "target_type": "Equipment",
        }
        driver, _ = self._mock_driver_with_records({"FT-101": [record]})

        service = Neo4jKGTraversalService(driver)
        paths = service.traverse(["FT-101"], max_depth=2, limit=50)

        assert paths == []

    def test_dedups_identical_edges_across_tags(self):
        from app.infrastructure.graphrag.neo4j_kg_traversal import (
            Neo4jKGTraversalService,
        )

        record = {
            "source_tag": "FT-101",
            "source_type": "Sensor",
            "relation_type": "MONITORS",
            "target_tag": "P-102A",
            "target_type": "Equipment",
        }
        driver, _ = self._mock_driver_with_records(
            {"FT-101": [record], "P-102A": [record]}
        )

        service = Neo4jKGTraversalService(driver)
        paths = service.traverse(["FT-101", "P-102A"], max_depth=2, limit=50)

        assert len(paths) == 1

    def test_one_tag_failure_does_not_abort_others(self):
        from app.infrastructure.graphrag.neo4j_kg_traversal import (
            Neo4jKGTraversalService,
        )

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = lambda s: session
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        good_record = {
            "source_tag": "FT-101",
            "source_type": "Sensor",
            "relation_type": "MONITORS",
            "target_tag": "P-102A",
            "target_type": "Equipment",
        }

        def _run(query, tag, max_level, limit):
            if tag == "BAD-TAG":
                raise RuntimeError("Cypher error")
            return [good_record]

        session.run.side_effect = _run

        service = Neo4jKGTraversalService(driver)
        paths = service.traverse(["BAD-TAG", "FT-101"], max_depth=2, limit=50)

        assert len(paths) == 1
        assert paths[0].source_tag == "FT-101"

    def test_empty_tags_returns_empty(self):
        from app.infrastructure.graphrag.neo4j_kg_traversal import (
            Neo4jKGTraversalService,
        )

        driver = MagicMock()
        service = Neo4jKGTraversalService(driver)
        assert service.traverse([], max_depth=2, limit=50) == []


# ---------------------------------------------------------------------------
# RedisGraphRAGCache
# ---------------------------------------------------------------------------


class TestRedisGraphRAGCache:
    def test_round_trip_serialize_deserialize(self):
        from app.infrastructure.graphrag.redis_graphrag_cache import (
            RedisGraphRAGCache,
        )

        store: dict = {}

        mock_redis = MagicMock()
        mock_redis.set.side_effect = lambda k, v, ex=None: store.__setitem__(k, v)
        mock_redis.get.side_effect = lambda k: store.get(k)

        cache = RedisGraphRAGCache(lambda: mock_redis)

        original = HybridSearchResult(
            ranked_chunks=[
                RankedChunk(result=_search_result(text="hello"), rerank_score=0.8)
            ],
            kg_paths=[KGPath("FT-101", "Sensor", "MONITORS", "P-102A", "Equipment")],
            entity_mentions=[EntityMention(tag_number="FT-101", entity_type="Sensor")],
            total_candidates_before_rerank=5,
            rerank_latency_ms=123.4,
        )

        cache.set("graphrag:cache:test", original, ttl_seconds=300)
        restored = cache.get("graphrag:cache:test")

        assert restored is not None
        assert restored.total_candidates_before_rerank == 5
        assert restored.rerank_latency_ms == pytest.approx(123.4)
        assert restored.ranked_chunks[0].result.text == "hello"
        assert restored.kg_paths[0].relation_type == "MONITORS"
        assert restored.entity_mentions[0].tag_number == "FT-101"

    def test_get_returns_none_on_cache_miss(self):
        from app.infrastructure.graphrag.redis_graphrag_cache import (
            RedisGraphRAGCache,
        )

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        cache = RedisGraphRAGCache(lambda: mock_redis)

        assert cache.get("missing-key") is None

    def test_get_returns_none_on_redis_error(self):
        from app.infrastructure.graphrag.redis_graphrag_cache import (
            RedisGraphRAGCache,
        )

        mock_redis = MagicMock()
        mock_redis.get.side_effect = RuntimeError("connection lost")
        cache = RedisGraphRAGCache(lambda: mock_redis)

        assert cache.get("any-key") is None

    def test_set_does_not_raise_on_redis_error(self):
        from app.infrastructure.graphrag.redis_graphrag_cache import (
            RedisGraphRAGCache,
        )

        mock_redis = MagicMock()
        mock_redis.set.side_effect = RuntimeError("connection lost")
        cache = RedisGraphRAGCache(lambda: mock_redis)

        cache.set("any-key", HybridSearchResult(), ttl_seconds=300)  # must not raise

    def test_set_passes_ttl_to_redis(self):
        from app.infrastructure.graphrag.redis_graphrag_cache import (
            RedisGraphRAGCache,
        )

        mock_redis = MagicMock()
        cache = RedisGraphRAGCache(lambda: mock_redis)

        cache.set("k", HybridSearchResult(), ttl_seconds=300)

        call_kwargs = mock_redis.set.call_args.kwargs
        assert call_kwargs["ex"] == 300


# ---------------------------------------------------------------------------
# Integration tests — real Docker Compose services
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_neo4j_kg_traversal_finds_monitors_path():
    """Seed Sensor-[:MONITORS]->Equipment in real Neo4j, verify traversal."""
    from app.infrastructure.di.container import container
    from app.infrastructure.graphrag.neo4j_kg_traversal import (
        Neo4jKGTraversalService,
    )

    driver = container.get_neo4j()
    test_sensor_tag = "FT-TEST-901"
    test_equipment_tag = "P-TEST-902"

    with driver.session() as session:
        session.run(
            "MERGE (s:Sensor {tag_number: $sensor_tag}) "
            "MERGE (e:Equipment {tag_number: $equipment_tag}) "
            "MERGE (s)-[:MONITORS]->(e)",
            sensor_tag=test_sensor_tag,
            equipment_tag=test_equipment_tag,
        )

    try:
        service = Neo4jKGTraversalService(driver)
        paths = service.traverse([test_sensor_tag], max_depth=2, limit=50)

        assert any(
            p.source_tag == test_sensor_tag
            and p.relation_type == "MONITORS"
            and p.target_tag == test_equipment_tag
            for p in paths
        )
    finally:
        with driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.tag_number IN [$s, $e] DETACH DELETE n",
                s=test_sensor_tag,
                e=test_equipment_tag,
            )


@pytest.mark.integration
def test_integration_redis_graphrag_cache_round_trip():
    """Cache a real HybridSearchResult in real Redis and read it back."""
    from app.infrastructure.di.container import container
    from app.infrastructure.graphrag.redis_graphrag_cache import RedisGraphRAGCache

    cache = RedisGraphRAGCache(container.get_redis)
    key = "graphrag:cache:test-integration-key"

    result = HybridSearchResult(
        kg_paths=[KGPath("FT-1", "Sensor", "MONITORS", "P-1", "Equipment")],
        total_candidates_before_rerank=3,
    )

    try:
        cache.set(key, result, ttl_seconds=60)
        restored = cache.get(key)

        assert restored is not None
        assert restored.total_candidates_before_rerank == 3
        assert restored.kg_paths[0].relation_type == "MONITORS"
    finally:
        container.get_redis().delete(key)


@pytest.mark.integration
@pytest.mark.skipif(
    not _SPACY_AVAILABLE, reason="spaCy not installed in this environment"
)
def test_integration_query_entity_extraction_and_kg_path():
    """Full roadmap acceptance test: query 'What sensors monitor pump
    P-102A?' → extracted tag → KG traversal → Sensor-MONITORS->Equipment
    path appears in the result.
    """
    from app.infrastructure.di.container import container
    from app.infrastructure.extraction.spacy_entity_extractor import (
        SpacyEntityExtractor,
    )
    from app.infrastructure.graphrag.neo4j_kg_traversal import (
        Neo4jKGTraversalService,
    )
    from app.domain.document.models import DocumentChunk

    driver = container.get_neo4j()
    sensor_tag = "FT-9101"
    equipment_tag = "P-102A"

    with driver.session() as session:
        session.run(
            "MERGE (s:Sensor {tag_number: $sensor_tag}) "
            "MERGE (e:Equipment {tag_number: $equipment_tag}) "
            "MERGE (s)-[:MONITORS]->(e)",
            sensor_tag=sensor_tag,
            equipment_tag=equipment_tag,
        )

    try:
        extractor = SpacyEntityExtractor("en_core_web_sm")
        chunk = DocumentChunk(
            id="q",
            document_id="q",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text="What sensors monitor pump P-102A?",
            page_number=None,
            parent_section_header=None,
            bbox_json=None,
            token_count=6,
            created_at=_now(),
            table_data_json=None,
            figure_storage_key=None,
        )
        entities = extractor.extract(chunk)
        tags = [e.tag_number for e in entities if e.tag_number]
        assert equipment_tag in tags

        service = Neo4jKGTraversalService(driver)
        paths = service.traverse(tags, max_depth=2, limit=50)

        assert any(
            p.relation_type == "MONITORS" and p.target_tag == equipment_tag
            for p in paths
        )
    finally:
        with driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.tag_number IN [$s, $e] DETACH DELETE n",
                s=sensor_tag,
                e=equipment_tag,
            )
