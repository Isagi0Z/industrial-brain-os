"""Unit and integration tests for M10 — Maintenance Brain Agent (LangGraph).

All external dependencies (GraphRAGEngine, Postgres work order repo, Neo4j
failure history repo, the LLM gateway) are mocked in unit tests. The
integration test uses real Postgres, Neo4j, and Redis (Docker Compose).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domain.chat.models import MessageRole
from app.domain.document.constants import ChunkType
from app.domain.graphrag.models import HybridSearchResult, RankedChunk
from app.domain.maintenance_brain.models import FailureRecord, WorkOrder
from app.domain.search.models import SearchResult

try:
    import spacy as _spacy_check  # noqa: F401

    _SPACY_AVAILABLE = True
except ModuleNotFoundError:
    _SPACY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search_result(
    chunk_id: str | None = None,
    text: str = "pump maintenance procedure",
    score: float = 0.5,
    document_title: str = "Manual",
    page_number: int = 1,
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id or str(uuid.uuid4()),
        document_id="doc-1",
        document_title=document_title,
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=page_number,
        parent_section_header=None,
        bbox_json=None,
        score=score,
        role_scope="public",
    )


def _work_order(
    wo_id: str = "WO-1001",
    asset_tag: str = "P-102A",
    status: str = "OPEN",
    priority: str = "HIGH",
    scheduled_date: date | None = None,
) -> WorkOrder:
    return WorkOrder(
        wo_id=wo_id,
        asset_tag=asset_tag,
        description="Replace mechanical seal",
        status=status,
        priority=priority,
        scheduled_date=scheduled_date or date(2026, 7, 5),
    )


def _make_prompt_file(tmp_path):
    content = """
system: |
  You are a test maintenance assistant.
user_template: |
  ASSET: {asset_tag}
  WO: {work_orders_block}
  FAIL: {failure_history_block}
  CTX: {context_blocks}
  Q: {query}
uncertain_template: |
  UNCERTAIN: {query}
"""
    path = tmp_path / "synthesize_guidance.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _make_agent(
    tmp_path,
    gateway_response: str = "Guidance text.",
    hybrid_result: HybridSearchResult | None = None,
    entities=None,
    work_orders=None,
    failure_history=None,
    max_steps: int = 10,
    gateway_raises: bool = False,
    graphrag_raises: bool = False,
    work_order_repo_raises: bool = False,
):
    from app.application.maintenance_brain.maintenance_brain_agent import (
        MaintenanceBrainAgent,
    )

    graphrag_engine = MagicMock()

    async def _retrieve(*a, **kw):
        if graphrag_raises:
            raise RuntimeError("GraphRAG boom")
        return hybrid_result if hybrid_result is not None else HybridSearchResult()

    graphrag_engine.retrieve = _retrieve

    entity_extractor = MagicMock()
    entity_extractor.extract.return_value = entities or []

    work_order_repo = MagicMock()
    if work_order_repo_raises:
        work_order_repo.find_open_by_asset_tag.side_effect = RuntimeError("DB boom")
        work_order_repo.find_by_wo_id.side_effect = RuntimeError("DB boom")
    else:
        work_order_repo.find_open_by_asset_tag.return_value = work_orders or []
        work_order_repo.find_by_wo_id.return_value = (
            work_orders[0] if work_orders else None
        )

    failure_history_repo = MagicMock()
    failure_history_repo.search_by_asset_tag.return_value = failure_history or []

    gateway = MagicMock()

    async def _generate(messages, max_tokens):
        if gateway_raises:
            raise RuntimeError("Gateway boom")
        return gateway_response, 10, 5

    gateway.generate = _generate
    gateway.model_name = "test-model"

    history_store: dict = {}
    history_repo = MagicMock()

    def _get_history(session_id):
        return history_store.get(session_id, [])

    def _append(session_id, messages, ttl):
        history_store.setdefault(session_id, [])
        history_store[session_id].extend(messages)

    history_repo.get_history = _get_history
    history_repo.append_messages = _append

    agent = MaintenanceBrainAgent(
        graphrag_engine=graphrag_engine,
        entity_extractor=entity_extractor,
        work_order_repo=work_order_repo,
        failure_history_repo=failure_history_repo,
        model_gateway=gateway,
        history_repo=history_repo,
        prompt_path=_make_prompt_file(tmp_path),
        max_steps=max_steps,
    )
    return agent, history_store


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class TestDomainModels:
    def test_work_order_defaults(self):
        wo = WorkOrder(
            wo_id="WO-1",
            asset_tag="P-1",
            description="x",
            status="OPEN",
            priority="LOW",
        )
        assert wo.scheduled_date is None
        assert wo.completed_date is None

    def test_failure_record_defaults(self):
        f = FailureRecord(failure_code="FM-1", description="seal wear")
        assert f.severity is None
        assert f.typical_cause is None


# ---------------------------------------------------------------------------
# Tool registry (ai/agents/maintenance_brain/tools.py)
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_work_order_lookup_by_wo_id(self):
        from ai.agents.maintenance_brain.tools import work_order_lookup

        repo = MagicMock()
        wo = _work_order()
        repo.find_by_wo_id.return_value = wo
        result = work_order_lookup(repo, wo_id="WO-1001")
        assert result == [wo]
        repo.find_by_wo_id.assert_called_once_with("WO-1001")

    def test_work_order_lookup_by_wo_id_not_found(self):
        from ai.agents.maintenance_brain.tools import work_order_lookup

        repo = MagicMock()
        repo.find_by_wo_id.return_value = None
        result = work_order_lookup(repo, wo_id="WO-9999")
        assert result == []

    def test_work_order_lookup_by_asset_tag(self):
        from ai.agents.maintenance_brain.tools import work_order_lookup

        repo = MagicMock()
        wos = [_work_order()]
        repo.find_by_asset_tag.return_value = wos
        result = work_order_lookup(repo, asset_tag="P-102A")
        assert result == wos

    def test_work_order_lookup_with_neither_returns_empty(self):
        from ai.agents.maintenance_brain.tools import work_order_lookup

        repo = MagicMock()
        assert work_order_lookup(repo) == []
        repo.find_by_wo_id.assert_not_called()
        repo.find_by_asset_tag.assert_not_called()

    def test_maintenance_schedule_query_delegates(self):
        from ai.agents.maintenance_brain.tools import maintenance_schedule_query

        repo = MagicMock()
        wos = [_work_order()]
        repo.find_open_by_asset_tag.return_value = wos
        result = maintenance_schedule_query(repo, "P-102A")
        assert result == wos

    def test_maintenance_schedule_query_empty_asset_tag(self):
        from ai.agents.maintenance_brain.tools import maintenance_schedule_query

        repo = MagicMock()
        assert maintenance_schedule_query(repo, None) == []
        repo.find_open_by_asset_tag.assert_not_called()

    def test_failure_history_search_delegates(self):
        from ai.agents.maintenance_brain.tools import failure_history_search

        repo = MagicMock()
        records = [FailureRecord(failure_code="FM-1", description="seal wear")]
        repo.search_by_asset_tag.return_value = records
        result = failure_history_search(repo, "P-102A")
        assert result == records

    def test_failure_history_search_empty_asset_tag(self):
        from ai.agents.maintenance_brain.tools import failure_history_search

        repo = MagicMock()
        assert failure_history_search(repo, None) == []
        repo.search_by_asset_tag.assert_not_called()

    def test_oem_manual_lookup_filters_by_title_heuristic(self):
        from ai.agents.maintenance_brain.tools import oem_manual_lookup

        manual_chunk = _search_result(document_title="Pump Installation Manual")
        random_chunk = _search_result(document_title="Weekly Safety Meeting Minutes")
        hybrid = HybridSearchResult(
            ranked_chunks=[
                RankedChunk(result=manual_chunk, rerank_score=0.9),
                RankedChunk(result=random_chunk, rerank_score=0.8),
            ]
        )
        engine = MagicMock()

        async def _retrieve(query, role_scope, top_k):
            return hybrid

        engine.retrieve = _retrieve

        result = asyncio.run(oem_manual_lookup(engine, "q", "public", 5))
        titles = [rc.result.document_title for rc in result.ranked_chunks]
        assert titles == ["Pump Installation Manual"]

    def test_oem_manual_lookup_case_insensitive(self):
        from ai.agents.maintenance_brain.tools import oem_manual_lookup

        chunk = _search_result(document_title="CENTRIFUGAL PUMP OEM DATASHEET")
        hybrid = HybridSearchResult(
            ranked_chunks=[RankedChunk(result=chunk, rerank_score=0.9)]
        )
        engine = MagicMock()

        async def _retrieve(query, role_scope, top_k):
            return hybrid

        engine.retrieve = _retrieve

        result = asyncio.run(oem_manual_lookup(engine, "q", "public", 5))
        assert len(result.ranked_chunks) == 1

    def test_extract_asset_tag_tool_filters_untagged(self):
        from ai.agents.maintenance_brain.tools import extract_asset_tag_tool
        from app.domain.extraction.models import ExtractedEntity

        extractor = MagicMock()
        extractor.extract.return_value = [
            ExtractedEntity(
                text="the", entity_type="Unknown", chunk_id="q", tag_number=None
            ),
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            ),
        ]
        result = extract_asset_tag_tool(extractor, "check on P-102A please")
        assert result == "P-102A"

    def test_extract_asset_tag_tool_returns_none_when_no_tag(self):
        from ai.agents.maintenance_brain.tools import extract_asset_tag_tool

        extractor = MagicMock()
        extractor.extract.return_value = []
        assert extract_asset_tag_tool(extractor, "how is everything") is None

    @pytest.mark.skipif(
        not _SPACY_AVAILABLE, reason="spaCy not installed in this environment"
    )
    def test_extract_asset_tag_tool_with_real_spacy(self):
        from ai.agents.maintenance_brain.tools import extract_asset_tag_tool
        from app.infrastructure.extraction.spacy_entity_extractor import (
            SpacyEntityExtractor,
        )

        extractor = SpacyEntityExtractor("en_core_web_sm")
        result = extract_asset_tag_tool(
            extractor, "Show me open work orders for pump P-102A"
        )
        assert result == "P-102A"


# ---------------------------------------------------------------------------
# MaintenanceBrainAgent — full graph orchestration
# ---------------------------------------------------------------------------


class TestMaintenanceBrainAgentRouting:
    def test_asset_tag_found_runs_full_pipeline(self, tmp_path):
        chunk = _search_result(chunk_id="c1", document_title="Pump OEM Manual")
        hybrid = HybridSearchResult(
            ranked_chunks=[RankedChunk(result=chunk, rerank_score=0.9)]
        )
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        work_orders = [_work_order()]
        failure_history = [FailureRecord(failure_code="FM-1", description="seal wear")]

        agent, _ = _make_agent(
            tmp_path,
            gateway_response="Replace the seal. [[chunk:c1]]",
            hybrid_result=hybrid,
            entities=entities,
            work_orders=work_orders,
            failure_history=failure_history,
        )
        state = asyncio.run(
            agent.run(
                "Show me all open work orders for pump P-102A and the relevant "
                "maintenance procedure",
                "s1",
                "public",
            )
        )

        assert state["error_flag"] is False
        assert state["asset_tag"] == "P-102A"
        assert state["work_orders"] == work_orders
        assert state["failure_history"] == failure_history
        assert len(state["citations"]) == 1
        assert "[1]" in state["draft_answer"]
        assert "Manual Sources:" in state["draft_answer"]

    def test_no_asset_tag_skips_retrieval_and_uses_uncertain_template(self, tmp_path):
        agent, _ = _make_agent(
            tmp_path, gateway_response="Please specify an asset tag."
        )
        state = asyncio.run(agent.run("how is maintenance going", "s2", "public"))

        assert state["asset_tag"] is None
        assert state["work_orders"] == []
        assert state["failure_history"] == []
        assert state["retrieved_chunks"] == []
        assert state["draft_answer"] == "Please specify an asset tag."

    def test_explicit_wo_id_uses_work_order_lookup_not_schedule_query(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        wo = _work_order(wo_id="WO-1001")
        agent, _ = _make_agent(tmp_path, entities=entities, work_orders=[wo])

        state = asyncio.run(
            agent.run("What is the status of WO-1001 for P-102A?", "s3", "public")
        )

        assert state["work_orders"] == [wo]


class TestMaintenanceBrainAgentStepLimit:
    def test_normal_query_completes_within_default_step_limit(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        agent, _ = _make_agent(tmp_path, entities=entities, max_steps=10)
        state = asyncio.run(agent.run("status of P-102A", "s4", "public"))
        assert state["step_count"] <= 10
        assert "STEP_LIMIT_EXCEEDED" not in state["draft_answer"]

    def test_low_step_limit_triggers_step_limit_exceeded(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        agent, _ = _make_agent(tmp_path, entities=entities, max_steps=2)
        state = asyncio.run(agent.run("status of P-102A", "s5", "public"))
        assert state["error_flag"] is True
        assert "STEP_LIMIT_EXCEEDED" in state["draft_answer"]

    def test_step_limit_of_one_triggers_immediately(self, tmp_path):
        agent, _ = _make_agent(tmp_path, max_steps=1)
        state = asyncio.run(agent.run("anything", "s6", "public"))
        assert state["error_flag"] is True
        assert "STEP_LIMIT_EXCEEDED" in state["draft_answer"]


class TestMaintenanceBrainAgentFallback:
    def test_graphrag_failure_sets_error_flag_and_returns_partial_answer(
        self, tmp_path
    ):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        agent, _ = _make_agent(tmp_path, entities=entities, graphrag_raises=True)
        state = asyncio.run(agent.run("status of P-102A", "s7", "public"))

        assert state["error_flag"] is True
        assert state["draft_answer"] != ""

    def test_work_order_repo_failure_sets_error_flag(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        agent, _ = _make_agent(tmp_path, entities=entities, work_order_repo_raises=True)
        state = asyncio.run(agent.run("status of P-102A", "s8", "public"))

        assert state["error_flag"] is True
        assert state["draft_answer"] != ""

    def test_gateway_failure_sets_error_flag(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        agent, _ = _make_agent(tmp_path, entities=entities, gateway_raises=True)
        state = asyncio.run(agent.run("status of P-102A", "s9", "public"))

        assert state["error_flag"] is True
        assert state["draft_answer"] != ""

    def test_fallback_does_not_raise_to_caller(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        agent, _ = _make_agent(
            tmp_path,
            entities=entities,
            graphrag_raises=True,
            gateway_raises=True,
            work_order_repo_raises=True,
        )
        state = asyncio.run(agent.run("status of P-102A", "s10", "public"))
        assert state["error_flag"] is True


class TestMaintenanceBrainAgentCitationValidation:
    def test_hallucinated_citation_is_stripped(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        chunk = _search_result(chunk_id="real-chunk", document_title="Pump Manual")
        hybrid = HybridSearchResult(
            ranked_chunks=[RankedChunk(result=chunk, rerank_score=0.9)]
        )
        agent, _ = _make_agent(
            tmp_path,
            entities=entities,
            gateway_response="Fact [[chunk:real-chunk]]. Fake [[chunk:fake-chunk]].",
            hybrid_result=hybrid,
        )
        state = asyncio.run(agent.run("status of P-102A", "s11", "public"))

        assert len(state["citations"]) == 1
        assert state["citations"][0].chunk_id == "real-chunk"
        assert "fake-chunk" not in state["draft_answer"]

    def test_no_citations_produces_no_sources_section(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="q",
                tag_number="P-102A",
            )
        ]
        agent, _ = _make_agent(
            tmp_path, entities=entities, gateway_response="No manual excerpt needed."
        )
        state = asyncio.run(agent.run("status of P-102A", "s12", "public"))

        assert state["citations"] == []
        assert "Manual Sources:" not in state["draft_answer"]


class TestMaintenanceBrainAgentSessionPersistence:
    def test_run_persists_turn_to_history_repo(self, tmp_path):
        agent, history_store = _make_agent(tmp_path, gateway_response="An answer.")
        asyncio.run(agent.run("A question", "session-a", "public"))

        assert "session-a" in history_store
        messages = history_store["session-a"]
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        assert messages[1].role == MessageRole.ASSISTANT

    def test_second_turn_sees_first_turn_history(self, tmp_path):
        agent, history_store = _make_agent(tmp_path, gateway_response="Second answer.")
        asyncio.run(agent.run("First question", "session-b", "public"))
        asyncio.run(agent.run("Second question", "session-b", "public"))

        messages = history_store["session-b"]
        assert len(messages) == 4
        assert messages[0].content == "First question"
        assert messages[2].content == "Second question"


# ---------------------------------------------------------------------------
# Integration test — real Postgres, Neo4j, Redis
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_demo_scenario_open_work_orders_and_procedure(tmp_path):
    """Roadmap acceptance test: "Show me all open work orders for pump
    P-102A and the relevant maintenance procedure" — verified against real
    Postgres (work_orders), real Neo4j (EXHIBITS failure history), and real
    Redis (session persistence)."""
    from app.application.maintenance_brain.maintenance_brain_agent import (
        MaintenanceBrainAgent,
    )
    from app.infrastructure.chat.redis_history_repository import (
        RedisChatHistoryRepository,
    )
    from app.infrastructure.di.container import container
    from app.infrastructure.maintenance.failure_history_repository import (
        Neo4jFailureHistoryRepository,
    )
    from app.infrastructure.maintenance.work_order_repository import (
        PostgresWorkOrderRepository,
    )

    # Must match the industrial tag regex (letters-hyphen-digits-optional-letter)
    # used by SpacyEntityExtractor/_extract_asset_tag_tool, e.g. "P-102A".
    digits = "".join(c for c in uuid.uuid4().hex if c.isdigit())[:3].ljust(3, "1")
    asset_tag = f"P-{digits}A"
    session_id = f"m10-integration-{uuid.uuid4()}"

    pg = container.get_postgres()
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO work_orders (wo_id, asset_tag, description, status, priority, scheduled_date)
            VALUES (%s, %s, %s, 'OPEN', 'HIGH', %s)
            """,
            (
                f"WO-TEST-{uuid.uuid4().hex[:6]}",
                asset_tag,
                "Test seal replacement",
                date(2026, 7, 5),
            ),
        )
    pg.commit()

    driver = container.get_neo4j()
    with driver.session() as session:
        session.run(
            "MERGE (e:Equipment {tag_number: $tag}) "
            "MERGE (f:FailureMode {failure_code: 'FM-TEST', description: 'Seal wear'}) "
            "MERGE (e)-[:EXHIBITS]->(f)",
            tag=asset_tag,
        )

    work_order_repo = PostgresWorkOrderRepository(container.get_postgres)
    failure_history_repo = Neo4jFailureHistoryRepository(driver)
    history_repo = RedisChatHistoryRepository(container.get_redis)

    graphrag_engine = MagicMock()

    async def _retrieve(*a, **kw):
        return HybridSearchResult()

    graphrag_engine.retrieve = _retrieve

    entity_extractor = container.get_entity_extractor()

    gateway = MagicMock()

    async def _generate(messages, max_tokens):
        return "Here are the open work orders and failure history.", 5, 5

    gateway.generate = _generate

    agent = MaintenanceBrainAgent(
        graphrag_engine=graphrag_engine,
        entity_extractor=entity_extractor,
        work_order_repo=work_order_repo,
        failure_history_repo=failure_history_repo,
        model_gateway=gateway,
        history_repo=history_repo,
        prompt_path=_make_prompt_file(tmp_path),
    )

    try:
        state = asyncio.run(
            agent.run(
                f"Show me all open work orders for pump {asset_tag} and the "
                "relevant maintenance procedure",
                session_id,
                "public",
            )
        )

        assert state["error_flag"] is False
        assert state["asset_tag"] == asset_tag
        assert len(state["work_orders"]) == 1
        assert state["work_orders"][0].status == "OPEN"
        assert len(state["failure_history"]) == 1
        assert state["failure_history"][0].failure_code == "FM-TEST"

        history = history_repo.get_history(session_id)
        assert len(history) == 2
    finally:
        with pg.cursor() as cur:
            cur.execute("DELETE FROM work_orders WHERE asset_tag = %s", (asset_tag,))
        pg.commit()
        with driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.tag_number = $tag OR n.failure_code = 'FM-TEST' "
                "DETACH DELETE n",
                tag=asset_tag,
            )
        history_repo.clear_session(session_id)
