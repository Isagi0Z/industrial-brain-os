"""Unit tests for M13 — Lessons Learned Brain Agent (LangGraph incident
ingestion + proactive warning detection).

Mocks the embedding service, vector repository, Neo4j lesson repository,
failure-history repository, ontology validator, and LLM gateway — matching
the mocking style established in test_rca_brain.py.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domain.document.constants import ChunkType
from app.domain.lessons_brain.models import Incident, LessonLearned, LessonLinkResult
from app.domain.maintenance_brain.models import FailureRecord
from app.domain.ontology.models import OntologyViolationError
from app.domain.search.models import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search_result(
    chunk_id: str = "lesson-1", text: str = "bearing seized"
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        document_id="P-102A",
        document_title="P-102A",
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=None,
        parent_section_header=None,
        bbox_json=None,
        score=0.93,
        role_scope="public",
    )


def _make_prompt_files(tmp_path):
    summary = (
        "system: |\n  Write a proactive warning summary. TOKEN_SUMMARY\n"
        "user_template: |\n  {asset_tag} {incident_description} {root_cause}"
        " {corrective_actions}\n"
    )
    chat = (
        "system: |\n  Answer from lessons only. TOKEN_CHAT\n"
        "user_template: |\n  {query} {lessons_block}\n"
    )
    sp = tmp_path / "generate_summary.yaml"
    sp.write_text(summary, encoding="utf-8")
    cp = tmp_path / "chat_answer.yaml"
    cp.write_text(chat, encoding="utf-8")
    return sp, cp


def _make_agent(
    tmp_path,
    failure_records=None,
    similar_hits=None,
    summary_text="Bearing seized due to lubrication failure.",
    ontology_raises: bool = False,
    link_result=None,
):
    from app.application.lessons_brain.lessons_brain_agent import (
        LessonsLearnedBrainAgent,
    )

    embedding_service = MagicMock()
    embedding_service.embed_one.return_value = [0.1] * 1024

    vector_repo = MagicMock()
    vector_repo.search.return_value = similar_hits or []

    lesson_repo = MagicMock()
    lesson_repo.create.return_value = link_result or LessonLinkResult(
        equipment_linked=True, failure_modes_linked=["FM-BRG-01"]
    )

    failure_history_repo = MagicMock()
    failure_history_repo.search_by_asset_tag.return_value = failure_records or []

    ontology_validator = MagicMock()
    if ontology_raises:
        ontology_validator.validate_node.side_effect = OntologyViolationError(
            "LessonLearned", "missing required properties"
        )

    gateway = MagicMock()

    async def _generate(messages, max_tokens):
        system = messages[0]["content"]
        if "TOKEN_SUMMARY" in system:
            return summary_text, 5, 5
        return "Answer grounded in lessons.", 5, 5

    gateway.generate = _generate

    history_repo = MagicMock()

    sp, cp = _make_prompt_files(tmp_path)

    agent = LessonsLearnedBrainAgent(
        embedding_service=embedding_service,
        vector_repo=vector_repo,
        lesson_repo=lesson_repo,
        failure_history_repo=failure_history_repo,
        ontology_validator=ontology_validator,
        model_gateway=gateway,
        history_repo=history_repo,
        generate_summary_prompt_path=sp,
        chat_prompt_path=cp,
    )
    return agent, {
        "embedding_service": embedding_service,
        "vector_repo": vector_repo,
        "lesson_repo": lesson_repo,
        "failure_history_repo": failure_history_repo,
        "ontology_validator": ontology_validator,
        "history_repo": history_repo,
    }


def _incident(**overrides) -> Incident:
    defaults = dict(
        asset_tag="P-102A",
        incident_date=date(2026, 5, 10),
        description="Pump P-102A bearing seized during startup",
        root_cause="Inadequate lubrication interval",
        corrective_actions=["Replace bearing", "Reinstate PM schedule"],
        severity="HIGH",
        role_scope="public",
    )
    defaults.update(overrides)
    return Incident(**defaults)


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class TestDomainModels:
    def test_incident_defaults(self):
        i = _incident()
        assert i.severity == "HIGH"
        assert i.role_scope == "public"

    def test_lesson_learned_defaults(self):
        lesson = LessonLearned(
            lesson_id="l1",
            asset_tag="P-102A",
            incident_date=date(2026, 5, 10),
            description="d",
            root_cause="rc",
            corrective_actions=[],
            severity="HIGH",
        )
        assert lesson.summary == ""
        assert lesson.equipment_linked is False
        assert lesson.failure_modes_linked == []


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_failure_pattern_match_delegates(self):
        from ai.agents.lessons_brain.tools import failure_pattern_match

        repo = MagicMock()
        recs = [FailureRecord(failure_code="FM-BRG-01", description="bearing wear")]
        repo.search_by_asset_tag.return_value = recs
        assert failure_pattern_match(repo, "P-102A") == recs

    def test_failure_pattern_match_empty_tag(self):
        from ai.agents.lessons_brain.tools import failure_pattern_match

        repo = MagicMock()
        assert failure_pattern_match(repo, "") == []
        repo.search_by_asset_tag.assert_not_called()

    def test_find_similar_lessons_embeds_and_searches(self):
        from ai.agents.lessons_brain.tools import (
            LESSONS_LEARNED_COLLECTION,
            find_similar_lessons,
        )

        embedding_service = MagicMock()
        embedding_service.embed_one.return_value = [0.2] * 1024
        vector_repo = MagicMock()
        vector_repo.search.return_value = [_search_result()]

        results = find_similar_lessons(
            embedding_service, vector_repo, "bearing seized", "public", 3
        )
        assert results == [_search_result()]
        vector_repo.search.assert_called_once_with(
            LESSONS_LEARNED_COLLECTION, [0.2] * 1024, "public", 3
        )

    def test_find_similar_lessons_empty_description(self):
        from ai.agents.lessons_brain.tools import find_similar_lessons

        embedding_service = MagicMock()
        vector_repo = MagicMock()
        assert (
            find_similar_lessons(embedding_service, vector_repo, "", "public", 3) == []
        )
        embedding_service.embed_one.assert_not_called()

    def test_generate_lesson_summary_calls_gateway(self, tmp_path):
        from ai.agents.lessons_brain.tools import generate_lesson_summary

        gateway = MagicMock()

        async def _gen(messages, mt):
            assert "P-102A" in messages[1]["content"]
            return "summary text", 5, 5

        gateway.generate = _gen
        prompt = {
            "system": "s",
            "user_template": "{asset_tag} {incident_description} {root_cause} {corrective_actions}",
        }
        result = asyncio.run(
            generate_lesson_summary(
                gateway, prompt, "P-102A", "bearing seized", "no lube", ["replace"], 100
            )
        )
        assert result == "summary text"


# ---------------------------------------------------------------------------
# Incident ingestion graph
# ---------------------------------------------------------------------------


class TestIngestion:
    def test_ingest_incident_success(self, tmp_path):
        agent, mocks = _make_agent(tmp_path)
        lesson = asyncio.run(agent.ingest_incident(_incident()))

        assert lesson.asset_tag == "P-102A"
        assert lesson.equipment_linked is True
        assert lesson.failure_modes_linked == ["FM-BRG-01"]
        assert lesson.summary == "Bearing seized due to lubrication failure."

        mocks["embedding_service"].embed_one.assert_called()
        mocks["vector_repo"].upsert.assert_called_once()
        mocks["lesson_repo"].create.assert_called_once()
        mocks["lesson_repo"].update_summary.assert_called_once()

    def test_ingest_incident_reuses_m10_failure_history(self, tmp_path):
        records = [FailureRecord(failure_code="FM-BRG-01", description="wear")]
        agent, mocks = _make_agent(tmp_path, failure_records=records)
        asyncio.run(agent.ingest_incident(_incident()))

        mocks["failure_history_repo"].search_by_asset_tag.assert_called_once_with(
            "P-102A"
        )
        # candidate codes derived from M10 reuse must reach lesson_repo.create
        _, kwargs = mocks["lesson_repo"].create.call_args
        called_args = mocks["lesson_repo"].create.call_args[0]
        assert called_args[1] == ["FM-BRG-01"]

    def test_ingest_incident_ontology_violation_raises(self, tmp_path):
        from app.application.lessons_brain.lessons_brain_agent import (
            IncidentProcessingError,
        )

        agent, mocks = _make_agent(tmp_path, ontology_raises=True)
        with pytest.raises(IncidentProcessingError):
            asyncio.run(agent.ingest_incident(_incident()))
        mocks["lesson_repo"].create.assert_not_called()

    def test_ingest_incident_step_limit_raises(self, tmp_path):
        from app.application.lessons_brain.lessons_brain_agent import (
            IncidentProcessingError,
        )

        agent, _ = _make_agent(tmp_path)
        agent._max_steps = 1
        agent._graph = agent._build_graph()
        with pytest.raises(IncidentProcessingError):
            asyncio.run(agent.ingest_incident(_incident()))

    def test_ingest_incident_summary_failure_degrades_gracefully(self, tmp_path):
        agent, mocks = _make_agent(tmp_path)

        async def _boom(messages, max_tokens):
            raise RuntimeError("LLM unavailable")

        agent._gateway.generate = _boom
        lesson = asyncio.run(agent.ingest_incident(_incident()))
        # Lesson is still stored even though summary generation failed.
        assert lesson is not None
        assert lesson.summary == ""
        mocks["lesson_repo"].create.assert_called_once()


# ---------------------------------------------------------------------------
# Chat endpoint logic
# ---------------------------------------------------------------------------


class TestChat:
    def test_chat_returns_answer_and_citations(self, tmp_path):
        agent, mocks = _make_agent(tmp_path, similar_hits=[_search_result()])
        result = asyncio.run(agent.chat("Why did P-102A fail?", "sess-1", "public"))

        assert result["error_flag"] is False
        assert result["answer"] == "Answer grounded in lessons."
        assert len(result["citations"]) == 1
        assert result["citations"][0].chunk_id == "lesson-1"
        mocks["history_repo"].append_messages.assert_called_once()

    def test_chat_no_matches_still_answers(self, tmp_path):
        agent, _ = _make_agent(tmp_path, similar_hits=[])
        result = asyncio.run(agent.chat("Unrelated question", "sess-2", "public"))
        assert result["error_flag"] is False
        assert result["citations"] == []

    def test_chat_degrades_on_gateway_failure(self, tmp_path):
        agent, _ = _make_agent(tmp_path)

        async def _boom(messages, max_tokens):
            raise RuntimeError("LLM unavailable")

        agent._gateway.generate = _boom
        result = asyncio.run(agent.chat("query", "sess-3", "public"))
        assert result["error_flag"] is True
        assert "unable" in result["answer"].lower()


# ---------------------------------------------------------------------------
# Proactive warning detector (M13 knowledge-cliff mitigation)
# ---------------------------------------------------------------------------


class TestProactiveWarningDetector:
    def _make_detector(self, hit_score=0.9, lesson=None, threshold=0.85):
        from app.infrastructure.lessons.proactive_warning_detector import (
            ProactiveWarningDetector,
        )

        embedding_service = MagicMock()
        embedding_service.embed_one.return_value = [0.1] * 1024
        vector_repo = MagicMock()
        vector_repo.search.return_value = (
            [_search_result(chunk_id="lesson-42")] if hit_score else []
        )
        if vector_repo.search.return_value:
            vector_repo.search.return_value[0].score = hit_score

        lesson_repo = MagicMock()
        lesson_repo.get.return_value = lesson

        detector = ProactiveWarningDetector(
            embedding_service, vector_repo, lesson_repo, similarity_threshold=threshold
        )
        return detector, lesson_repo

    def test_detects_warning_above_threshold(self):
        lesson = LessonLearned(
            lesson_id="lesson-42",
            asset_tag="P-102A",
            incident_date=date(2026, 5, 10),
            description="bearing seized",
            root_cause="no lube",
            corrective_actions=["replace bearing"],
            severity="HIGH",
            summary="Bearing seized due to lubrication failure.",
        )
        detector, lesson_repo = self._make_detector(hit_score=0.92, lesson=lesson)
        warning = detector.detect("pump P-102A making noise", "public")

        assert warning is not None
        assert warning.warning_type == "LESSONS_LEARNED"
        assert warning.lesson_summary == "Bearing seized due to lubrication failure."
        assert warning.similarity_score == 0.92
        assert warning.asset_tag == "P-102A"
        lesson_repo.get.assert_called_once_with("lesson-42")

    def test_below_threshold_returns_none(self):
        detector, lesson_repo = self._make_detector(hit_score=0.5, lesson=None)
        warning = detector.detect("unrelated query", "public")
        assert warning is None
        lesson_repo.get.assert_not_called()

    def test_no_hits_returns_none(self):
        detector, _ = self._make_detector(hit_score=None)
        warning = detector.detect("query", "public")
        assert warning is None

    def test_empty_query_returns_none(self):
        detector, _ = self._make_detector(hit_score=0.9)
        assert detector.detect("", "public") is None
        assert detector.detect("   ", "public") is None

    def test_detector_failure_degrades_to_none(self):
        embedding_service = MagicMock()
        embedding_service.embed_one.side_effect = RuntimeError("model unavailable")
        vector_repo = MagicMock()
        lesson_repo = MagicMock()

        from app.infrastructure.lessons.proactive_warning_detector import (
            ProactiveWarningDetector,
        )

        detector = ProactiveWarningDetector(embedding_service, vector_repo, lesson_repo)
        assert detector.detect("query", "public") is None


# ---------------------------------------------------------------------------
# Roadmap demo acceptance test (mocked infra):
# "ingest a bearing failure incident, then query about pump P-102A —
# verify warning appears"
# ---------------------------------------------------------------------------


class TestDemoScenario:
    def test_ingest_then_detect_warning_end_to_end(self, tmp_path):
        from app.infrastructure.lessons.proactive_warning_detector import (
            ProactiveWarningDetector,
        )

        agent, mocks = _make_agent(tmp_path)
        lesson = asyncio.run(agent.ingest_incident(_incident()))

        # Wire a detector against the SAME (mocked) lesson_repo the agent
        # stored into, simulating the shared Neo4j backing store.
        mocks["lesson_repo"].get.return_value = lesson
        mocks["vector_repo"].search.return_value = [
            _search_result(chunk_id=lesson.lesson_id)
        ]
        mocks["vector_repo"].search.return_value[0].score = 0.9

        detector = ProactiveWarningDetector(
            mocks["embedding_service"], mocks["vector_repo"], mocks["lesson_repo"]
        )
        warning = detector.detect("pump P-102A bearing making noise again", "public")

        assert warning is not None
        assert warning.asset_tag == "P-102A"
        assert warning.lesson_id == lesson.lesson_id
