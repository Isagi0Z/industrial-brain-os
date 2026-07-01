"""Unit and integration tests for M9 — Knowledge Brain Agent (LangGraph).

All external dependencies (GraphRAGEngine, Neo4j, the LLM gateway) are
mocked in unit tests. The multi-turn integration test uses a real Redis
instance (Docker Compose) to verify session state actually accumulates,
per the M9 checklist.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest

from app.domain.chat.models import MessageRole
from app.domain.graphrag.models import HybridSearchResult, KGPath, RankedChunk
from app.domain.search.models import SearchResult
from app.domain.document.constants import ChunkType

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


def _make_prompt_file(tmp_path):
    content = """
system: |
  You are a test assistant.
user_template: |
  CONTEXT: {context_blocks}
  KG: {kg_markdown}
  Q: {query}
uncertain_template: |
  UNCERTAIN: {query}
"""
    path = tmp_path / "synthesize_answer.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _make_agent(
    tmp_path,
    gateway_response: str = "Answer text.",
    hybrid_result: HybridSearchResult | None = None,
    kg_paths=None,
    entities=None,
    max_steps: int = 10,
    gateway_raises: bool = False,
    graphrag_raises: bool = False,
):
    from app.application.knowledge_brain.knowledge_brain_agent import (
        KnowledgeBrainAgent,
    )

    graphrag_engine = MagicMock()

    async def _retrieve(*a, **kw):
        if graphrag_raises:
            raise RuntimeError("GraphRAG boom")
        return hybrid_result if hybrid_result is not None else HybridSearchResult()

    graphrag_engine.retrieve = _retrieve

    entity_extractor = MagicMock()
    entity_extractor.extract.return_value = entities or []

    kg_traversal = MagicMock()
    kg_traversal.traverse.return_value = kg_paths or []

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

    agent = KnowledgeBrainAgent(
        graphrag_engine=graphrag_engine,
        entity_extractor=entity_extractor,
        kg_traversal=kg_traversal,
        model_gateway=gateway,
        history_repo=history_repo,
        prompt_path=_make_prompt_file(tmp_path),
        max_steps=max_steps,
    )
    return agent, history_store


# ---------------------------------------------------------------------------
# _classify_intent
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    def _classify(self, query):
        from app.application.knowledge_brain.knowledge_brain_agent import (
            _classify_intent,
        )

        return _classify_intent(query)

    def test_entity_tag_classified_as_entity_lookup(self):
        assert self._classify("What sensors monitor pump P-102A?") == "entity_lookup"

    def test_compact_tag_classified_as_entity_lookup(self):
        assert self._classify("Show me details for FT101") == "entity_lookup"

    def test_procedural_keyword_classified_as_procedural(self):
        assert self._classify("How to replace a bearing seal") == "procedural"

    def test_steps_keyword_classified_as_procedural(self):
        assert (
            self._classify("What are the steps to isolate this valve") == "procedural"
        )

    def test_generic_question_classified_as_document_search(self):
        assert (
            self._classify("What is the maximum operating pressure")
            == "document_search"
        )

    def test_empty_query_classified_as_unknown(self):
        assert self._classify("") == "unknown"
        assert self._classify("   ") == "unknown"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestFormatHelpers:
    def test_format_context_blocks_includes_chunk_id(self):
        from app.application.knowledge_brain.knowledge_brain_agent import (
            _format_context_blocks,
        )

        chunks = [_search_result(chunk_id="abc123", text="pump info", page_number=3)]
        blocks = _format_context_blocks(chunks)
        assert "abc123" in blocks
        assert "pump info" in blocks
        assert "p.3" in blocks

    def test_format_context_blocks_empty(self):
        from app.application.knowledge_brain.knowledge_brain_agent import (
            _format_context_blocks,
        )

        assert _format_context_blocks([]) == ""

    def test_format_kg_markdown_empty(self):
        from app.application.knowledge_brain.knowledge_brain_agent import (
            _format_kg_markdown,
        )

        assert _format_kg_markdown([]) == ""

    def test_format_kg_markdown_renders_table(self):
        from app.application.knowledge_brain.knowledge_brain_agent import (
            _format_kg_markdown,
        )

        paths = [KGPath("FT-101", "Sensor", "MONITORS", "P-102A", "Equipment")]
        md = _format_kg_markdown(paths)
        assert "Sensor:FT-101" in md
        assert "MONITORS" in md
        assert "Equipment:P-102A" in md


# ---------------------------------------------------------------------------
# Tool registry (ai/agents/knowledge_brain/tools.py)
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_semantic_search_tool_delegates_to_graphrag_engine(self):
        from ai.agents.knowledge_brain.tools import semantic_search_tool

        engine = MagicMock()
        expected = HybridSearchResult(total_candidates_before_rerank=3)

        async def _retrieve(query, role_scope, top_k):
            assert query == "q"
            assert role_scope == "public"
            assert top_k == 5
            return expected

        engine.retrieve = _retrieve
        result = asyncio.run(semantic_search_tool(engine, "q", "public", 5))
        assert result is expected

    def test_graph_search_tool_returns_empty_for_no_tags(self):
        from ai.agents.knowledge_brain.tools import graph_search_tool

        kg_traversal = MagicMock()
        result = graph_search_tool(kg_traversal, [], max_depth=2, limit=50)
        assert result == []
        kg_traversal.traverse.assert_not_called()

    def test_graph_search_tool_delegates_with_tags(self):
        from ai.agents.knowledge_brain.tools import graph_search_tool

        expected = [KGPath("FT-101", "Sensor", "MONITORS", "P-102A", "Equipment")]
        kg_traversal = MagicMock()
        kg_traversal.traverse.return_value = expected

        result = graph_search_tool(kg_traversal, ["FT-101"], max_depth=2, limit=50)
        assert result == expected
        kg_traversal.traverse.assert_called_once_with(["FT-101"], 2, 50)

    def test_entity_lookup_tool_filters_untagged_entities(self):
        from ai.agents.knowledge_brain.tools import entity_lookup_tool
        from app.domain.extraction.models import ExtractedEntity

        extractor = MagicMock()
        extractor.extract.return_value = [
            ExtractedEntity(
                text="FT-101",
                entity_type="Sensor",
                chunk_id="query",
                tag_number="FT-101",
            ),
            ExtractedEntity(
                text="the", entity_type="Unknown", chunk_id="query", tag_number=None
            ),
        ]
        result = entity_lookup_tool(extractor, "FT-101 reading")
        assert len(result) == 1
        assert result[0].tag_number == "FT-101"

    def test_document_lookup_tool_delegates(self):
        from ai.agents.knowledge_brain.tools import document_lookup_tool

        repo = MagicMock()
        repo.get_by_id.return_value = "the-document"
        result = document_lookup_tool(repo, "doc-1")
        assert result == "the-document"
        repo.get_by_id.assert_called_once_with("doc-1")

    @pytest.mark.skipif(
        not _SPACY_AVAILABLE, reason="spaCy not installed in this environment"
    )
    def test_entity_lookup_tool_with_real_spacy_extractor(self):
        from ai.agents.knowledge_brain.tools import entity_lookup_tool
        from app.infrastructure.extraction.spacy_entity_extractor import (
            SpacyEntityExtractor,
        )

        extractor = SpacyEntityExtractor("en_core_web_sm")
        result = entity_lookup_tool(extractor, "What monitors pump P-102A?")
        tags = [e.tag_number for e in result]
        assert "P-102A" in tags


# ---------------------------------------------------------------------------
# KnowledgeBrainAgent — full graph orchestration
# ---------------------------------------------------------------------------


class TestKnowledgeBrainAgentRouting:
    def test_document_search_runs_full_retrieval(self, tmp_path):
        chunk = _search_result(chunk_id="c1", text="pump info")
        hybrid = HybridSearchResult(
            ranked_chunks=[RankedChunk(result=chunk, rerank_score=0.9)],
            kg_paths=[],
        )
        agent, _ = _make_agent(
            tmp_path,
            gateway_response="Pumps run at 50 bar. [[chunk:c1]]",
            hybrid_result=hybrid,
        )
        state = asyncio.run(agent.run("What is the pump pressure?", "s1", "public"))

        assert state["error_flag"] is False
        assert len(state["citations"]) == 1
        assert state["citations"][0].chunk_id == "c1"
        assert "[1]" in state["draft_answer"]
        assert "Sources:" in state["draft_answer"]

    def test_entity_lookup_skips_full_hybrid_search(self, tmp_path):
        from app.domain.extraction.models import ExtractedEntity

        entities = [
            ExtractedEntity(
                text="P-102A",
                entity_type="Equipment",
                chunk_id="query",
                tag_number="P-102A",
            )
        ]
        kg_paths = [KGPath("FT-101", "Sensor", "MONITORS", "P-102A", "Equipment")]

        agent, _ = _make_agent(tmp_path, entities=entities, kg_paths=kg_paths)

        state = asyncio.run(
            agent.run("What sensors monitor pump P-102A?", "s2", "public")
        )

        assert state["kg_paths"] == kg_paths
        assert state["retrieved_chunks"] == []
        assert state["error_flag"] is False

    def test_unknown_query_skips_retrieval_and_uses_uncertain_template(self, tmp_path):
        agent, _ = _make_agent(tmp_path, gateway_response="I'm not sure what you mean.")
        state = asyncio.run(agent.run("   ", "s3", "public"))

        assert state["retrieved_chunks"] == []
        assert state["kg_paths"] == []
        assert state["draft_answer"].startswith("I'm not sure")


class TestKnowledgeBrainAgentStepLimit:
    def test_normal_query_completes_within_default_step_limit(self, tmp_path):
        agent, _ = _make_agent(tmp_path, max_steps=10)
        state = asyncio.run(agent.run("What is the pump pressure?", "s4", "public"))
        assert state["step_count"] <= 10
        assert "STEP_LIMIT_EXCEEDED" not in state["draft_answer"]

    def test_low_step_limit_triggers_step_limit_exceeded(self, tmp_path):
        agent, _ = _make_agent(tmp_path, max_steps=2)
        state = asyncio.run(agent.run("What is the pump pressure?", "s5", "public"))
        assert state["error_flag"] is True
        assert "STEP_LIMIT_EXCEEDED" in state["draft_answer"]

    def test_step_limit_of_one_triggers_immediately(self, tmp_path):
        agent, _ = _make_agent(tmp_path, max_steps=1)
        state = asyncio.run(agent.run("anything", "s6", "public"))
        assert state["error_flag"] is True
        assert "STEP_LIMIT_EXCEEDED" in state["draft_answer"]


class TestKnowledgeBrainAgentFallback:
    def test_graphrag_failure_sets_error_flag_and_returns_partial_answer(
        self, tmp_path
    ):
        agent, _ = _make_agent(tmp_path, graphrag_raises=True)
        state = asyncio.run(agent.run("What is the pump pressure?", "s7", "public"))

        assert state["error_flag"] is True
        assert state["draft_answer"] != ""
        assert (
            "internal issue" in state["draft_answer"]
            or "incomplete" in state["draft_answer"]
        )

    def test_gateway_failure_sets_error_flag_and_returns_partial_answer(self, tmp_path):
        agent, _ = _make_agent(tmp_path, gateway_raises=True)
        state = asyncio.run(agent.run("What is the pump pressure?", "s8", "public"))

        assert state["error_flag"] is True
        assert state["draft_answer"] != ""

    def test_fallback_does_not_raise_to_caller(self, tmp_path):
        agent, _ = _make_agent(tmp_path, graphrag_raises=True, gateway_raises=True)
        # Must not raise — the whole point of the fallback path.
        state = asyncio.run(agent.run("query", "s9", "public"))
        assert state["error_flag"] is True


class TestKnowledgeBrainAgentCitationValidation:
    def test_hallucinated_citation_is_stripped(self, tmp_path):
        chunk = _search_result(chunk_id="real-chunk", text="real info")
        hybrid = HybridSearchResult(
            ranked_chunks=[RankedChunk(result=chunk, rerank_score=0.9)],
        )
        agent, _ = _make_agent(
            tmp_path,
            gateway_response="Fact one [[chunk:real-chunk]]. Fact two [[chunk:fake-chunk]].",
            hybrid_result=hybrid,
        )
        state = asyncio.run(agent.run("What is the pump pressure?", "s10", "public"))

        assert len(state["citations"]) == 1
        assert state["citations"][0].chunk_id == "real-chunk"
        assert "[[chunk:fake-chunk]]" not in state["draft_answer"]
        assert "fake-chunk" not in state["draft_answer"]

    def test_no_citations_produces_no_sources_section(self, tmp_path):
        agent, _ = _make_agent(
            tmp_path, gateway_response="A plain answer with no citations."
        )
        state = asyncio.run(agent.run("What is the pump pressure?", "s11", "public"))

        assert state["citations"] == []
        assert "Sources:" not in state["draft_answer"]

    def test_duplicate_citation_markers_deduped(self, tmp_path):
        chunk = _search_result(chunk_id="c1", text="info")
        hybrid = HybridSearchResult(
            ranked_chunks=[RankedChunk(result=chunk, rerank_score=0.9)],
        )
        agent, _ = _make_agent(
            tmp_path,
            gateway_response="First [[chunk:c1]]. Also [[chunk:c1]] again.",
            hybrid_result=hybrid,
        )
        state = asyncio.run(agent.run("q", "s12", "public"))
        assert len(state["citations"]) == 1


class TestKnowledgeBrainAgentSessionPersistence:
    def test_run_persists_turn_to_history_repo(self, tmp_path):
        agent, history_store = _make_agent(tmp_path, gateway_response="An answer.")
        asyncio.run(agent.run("A question", "session-a", "public"))

        assert "session-a" in history_store
        messages = history_store["session-a"]
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        assert messages[0].content == "A question"
        assert messages[1].role == MessageRole.ASSISTANT
        assert messages[1].content == "An answer."

    def test_second_turn_sees_first_turn_history(self, tmp_path):
        agent, history_store = _make_agent(tmp_path, gateway_response="Second answer.")
        asyncio.run(agent.run("First question", "session-b", "public"))
        asyncio.run(agent.run("Second question", "session-b", "public"))

        messages = history_store["session-b"]
        assert len(messages) == 4
        assert messages[0].content == "First question"
        assert messages[2].content == "Second question"


# ---------------------------------------------------------------------------
# Integration test — real Redis, multi-turn state accumulation
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_multi_turn_state_accumulates_via_redis(tmp_path):
    """Roadmap acceptance test: run a multi-turn conversation and verify
    state accumulates across turns via a real Redis-backed session."""
    from app.application.knowledge_brain.knowledge_brain_agent import (
        KnowledgeBrainAgent,
    )
    from app.infrastructure.chat.redis_history_repository import (
        RedisChatHistoryRepository,
    )
    from app.infrastructure.di.container import container

    session_id = f"m9-integration-{uuid.uuid4()}"
    history_repo = RedisChatHistoryRepository(container.get_redis)

    graphrag_engine = MagicMock()

    async def _retrieve(*a, **kw):
        return HybridSearchResult()

    graphrag_engine.retrieve = _retrieve

    entity_extractor = MagicMock()
    entity_extractor.extract.return_value = []
    kg_traversal = MagicMock()

    call_count = {"n": 0}
    gateway = MagicMock()

    async def _generate(messages, max_tokens):
        call_count["n"] += 1
        # Assert the second call's message list already contains turn 1.
        if call_count["n"] == 2:
            joined = " ".join(m["content"] for m in messages)
            assert "first turn question" in joined
        return f"answer #{call_count['n']}", 5, 5

    gateway.generate = _generate

    agent = KnowledgeBrainAgent(
        graphrag_engine=graphrag_engine,
        entity_extractor=entity_extractor,
        kg_traversal=kg_traversal,
        model_gateway=gateway,
        history_repo=history_repo,
        prompt_path=_make_prompt_file(tmp_path),
    )

    try:
        state1 = asyncio.run(agent.run("first turn question", session_id, "public"))
        state2 = asyncio.run(agent.run("second turn question", session_id, "public"))

        assert state1["draft_answer"] == "answer #1"
        assert state2["draft_answer"] == "answer #2"

        history = history_repo.get_history(session_id)
        assert len(history) == 4
        assert history[0].content == "first turn question"
        assert history[2].content == "second turn question"
    finally:
        history_repo.clear_session(session_id)
