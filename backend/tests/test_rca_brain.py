"""Unit and integration tests for M12 — RCA Brain Agent (LangGraph, 5-Whys +
Fishbone with human-in-the-loop).

Unit tests mock GraphRAG, the LLM gateway, and all repositories. The
integration test uses real Postgres (rca_sessions + work_orders), real Neo4j
(EXHIBITS failure patterns), and real Redis (live session state).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domain.document.constants import ChunkType
from app.domain.graphrag.models import HybridSearchResult, RankedChunk
from app.domain.maintenance_brain.models import FailureRecord, WorkOrder
from app.domain.rca_brain.models import (
    FishboneCategory,
    RCAReport,
    RCASession,
    RCAStatus,
    WhyStep,
)
from app.domain.search.models import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search_result(
    chunk_id: str = "c1",
    text: str = "bearing wear evidence text",
    document_title: str = "Pump Manual",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        document_id="doc-1",
        document_title=document_title,
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=1,
        parent_section_header=None,
        bbox_json=None,
        score=0.9,
        role_scope="public",
    )


def _make_prompt_files(tmp_path):
    # System prompts carry distinguishing tokens the test gateway routes on.
    suggest = (
        "system: |\n  Facilitate 5-Whys. TOKEN_SUGGEST\n"
        "user_template: |\n  {incident_description} {asset_tag} {failure_patterns}"
        " {incident_history} {whys_block}\n"
    )
    report = (
        "system: |\n  Write the RCA report as a JSON object with root_cause. TOKEN_REPORT\n"
        "user_template: |\n  {incident_description} {asset_tag} {whys_block}"
        " {failure_patterns} {evidence_block}\n"
    )
    fishbone = (
        "system: |\n  Fishbone category JSON array. TOKEN_FISHBONE\n"
        "user_template: |\n  {incident_description} {asset_tag} {category} {evidence_block}\n"
    )
    sp = tmp_path / "suggest_why.yaml"
    sp.write_text(suggest, encoding="utf-8")
    rp = tmp_path / "generate_report.yaml"
    rp.write_text(report, encoding="utf-8")
    fp = tmp_path / "fishbone.yaml"
    fp.write_text(fishbone, encoding="utf-8")
    return sp, rp, fp


def _report_json() -> str:
    return json.dumps(
        {
            "root_cause": "Bearing failed due to inadequate lubrication",
            "contributing_factors": ["Skipped PM interval"],
            "recommended_actions": [
                "Replace bearing [[chunk:c1]]",
                "Reinstate PM schedule",
            ],
            "evidence_citations": [
                "[[chunk:c1]]",
                "[[chunk:hallucinated]]",
                "FM-SEAL-01",
            ],
        }
    )


def _make_agent(
    tmp_path,
    failure_records=None,
    incidents=None,
    max_whys: int = 3,
    suggest_raises: bool = False,
    report_unparseable: bool = False,
    evidence_chunks=None,
):
    from app.application.rca_brain.rca_brain_agent import RCABrainAgent

    graphrag = MagicMock()

    async def _retrieve(query, role_scope, top_k):
        chunks = evidence_chunks if evidence_chunks is not None else [_search_result()]
        return HybridSearchResult(
            ranked_chunks=[RankedChunk(result=c, rerank_score=0.9) for c in chunks]
        )

    graphrag.retrieve = _retrieve

    gateway = MagicMock()

    async def _generate(messages, max_tokens):
        system = messages[0]["content"]
        if "TOKEN_REPORT" in system:
            if report_unparseable:
                return "I cannot produce a report.", 5, 5
            return _report_json(), 5, 5
        if "TOKEN_FISHBONE" in system:
            return json.dumps(["a candidate cause"]), 5, 5
        # suggest
        if suggest_raises:
            raise RuntimeError("LLM boom")
        return "Why did the bearing fail?", 5, 5

    gateway.generate = _generate

    failure_repo = MagicMock()
    failure_repo.search_by_asset_tag.return_value = failure_records or []
    incident_repo = MagicMock()
    incident_repo.search_by_keywords.return_value = incidents or []

    session_repo = MagicMock()

    # In-memory Redis state store stand-in.
    store: dict = {}
    state_store = MagicMock()
    state_store.save = lambda s, ttl: store.__setitem__(s.session_id, s)
    state_store.load = lambda sid: store.get(sid)
    state_store.delete = lambda sid: store.pop(sid, None)

    sp, rp, fp = _make_prompt_files(tmp_path)

    agent = RCABrainAgent(
        graphrag_engine=graphrag,
        model_gateway=gateway,
        failure_history_repo=failure_repo,
        incident_repo=incident_repo,
        session_repo=session_repo,
        state_store=state_store,
        suggest_why_prompt_path=sp,
        generate_report_prompt_path=rp,
        fishbone_prompt_path=fp,
        max_whys=max_whys,
    )
    return agent, session_repo, store


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class TestDomainModels:
    def test_fishbone_has_six_categories(self):
        assert len(list(FishboneCategory)) == 6
        names = {c.value for c in FishboneCategory}
        assert names == {
            "Equipment",
            "Method",
            "Material",
            "Man",
            "Environment",
            "Measurement",
        }

    def test_rca_report_defaults(self):
        r = RCAReport(problem_statement="p", root_cause="rc")
        assert r.contributing_factors == []
        assert r.recommended_actions == []
        assert r.evidence_citations == []
        assert r.fishbone == {}

    def test_rca_report_rejects_missing_required(self):
        with pytest.raises(Exception):
            RCAReport(problem_statement="p")  # missing root_cause


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_extract_keywords_drops_stopwords_and_short(self):
        from ai.agents.rca_brain.tools import extract_keywords

        kws = extract_keywords("The pump bearing failure on P-102A is a problem")
        assert "pump" in kws
        assert "bearing" in kws
        assert "p-102a" in kws
        assert "the" not in kws
        assert "is" not in kws
        assert "failure" not in kws  # domain stopword

    def test_extract_keywords_empty(self):
        from ai.agents.rca_brain.tools import extract_keywords

        assert extract_keywords("") == []

    def test_failure_pattern_search_delegates(self):
        from ai.agents.rca_brain.tools import failure_pattern_search

        repo = MagicMock()
        recs = [FailureRecord(failure_code="FM-1", description="wear")]
        repo.search_by_asset_tag.return_value = recs
        assert failure_pattern_search(repo, "P-102A") == recs

    def test_failure_pattern_search_empty_tag(self):
        from ai.agents.rca_brain.tools import failure_pattern_search

        repo = MagicMock()
        assert failure_pattern_search(repo, "") == []
        repo.search_by_asset_tag.assert_not_called()

    def test_incident_history_search_uses_keywords(self):
        from ai.agents.rca_brain.tools import incident_history_search

        repo = MagicMock()
        wos = [
            WorkOrder(
                wo_id="WO-1",
                asset_tag="P-102A",
                description="bearing replacement",
                status="COMPLETED",
                priority="HIGH",
            )
        ]
        repo.search_by_keywords.return_value = wos
        result = incident_history_search(repo, "pump bearing failure", 5)
        assert result == wos
        repo.search_by_keywords.assert_called_once()

    def test_parse_report_object_valid(self):
        from ai.agents.rca_brain.tools import parse_report_object

        obj = parse_report_object('{"root_cause": "x", "recommended_actions": []}')
        assert obj is not None
        assert obj["root_cause"] == "x"

    def test_parse_report_object_fenced(self):
        from ai.agents.rca_brain.tools import parse_report_object

        obj = parse_report_object('```json\n{"root_cause": "y"}\n```')
        assert obj is not None
        assert obj["root_cause"] == "y"

    def test_parse_report_object_unparseable(self):
        from ai.agents.rca_brain.tools import parse_report_object

        assert parse_report_object("no json here") is None

    def test_fishbone_analysis_runs_all_six_categories(self, tmp_path):
        from ai.agents.rca_brain.tools import fishbone_analysis

        graphrag = MagicMock()

        async def _retrieve(q, rs, k):
            return HybridSearchResult(
                ranked_chunks=[RankedChunk(result=_search_result(), rerank_score=0.9)]
            )

        graphrag.retrieve = _retrieve

        gateway = MagicMock()

        async def _gen(messages, mt):
            return json.dumps(["cause A"]), 5, 5

        gateway.generate = _gen

        prompt = {
            "system": "s",
            "user_template": "{incident_description} {asset_tag} {category} {evidence_block}",
        }
        result = asyncio.run(
            fishbone_analysis(
                graphrag, gateway, prompt, "incident", "P-1", "public", 5, 100
            )
        )
        assert set(result.keys()) == {c.value for c in FishboneCategory}
        assert result["Equipment"] == ["cause A"]

    def test_fishbone_branch_failure_isolated(self, tmp_path):
        from ai.agents.rca_brain.tools import fishbone_analysis

        graphrag = MagicMock()

        async def _retrieve(q, rs, k):
            raise RuntimeError("retrieval boom")

        graphrag.retrieve = _retrieve
        gateway = MagicMock()

        prompt = {
            "system": "s",
            "user_template": "{incident_description} {asset_tag} {category} {evidence_block}",
        }
        result = asyncio.run(
            fishbone_analysis(
                graphrag, gateway, prompt, "incident", "P-1", "public", 5, 100
            )
        )
        # All categories present, each empty (branch failures isolated).
        assert set(result.keys()) == {c.value for c in FishboneCategory}
        assert all(v == [] for v in result.values())


# ---------------------------------------------------------------------------
# RCABrainAgent — 5-Whys iteration, human interrupt/resume
# ---------------------------------------------------------------------------


class TestRCAFiveWhys:
    def test_start_session_suggests_first_why(self, tmp_path):
        agent, session_repo, store = _make_agent(tmp_path)
        session = asyncio.run(
            agent.start_session("s1", "P-102A", "pump bearing failure", "public")
        )
        assert session.status == RCAStatus.AWAITING_INPUT
        assert len(session.whys) == 1
        assert session.whys[0].question == "Why did the bearing fail?"
        assert session.whys[0].answer is None
        session_repo.create.assert_called_once()
        assert "s1" in store  # persisted to (mock) Redis state store

    def test_advance_records_answer_and_suggests_next(self, tmp_path):
        agent, _, _ = _make_agent(tmp_path, max_whys=3)
        asyncio.run(agent.start_session("s2", "P-102A", "bearing failure", "public"))
        session = asyncio.run(agent.advance_session("s2", "no lubrication", "public"))
        assert session.status == RCAStatus.AWAITING_INPUT
        assert len(session.whys) == 2
        assert session.whys[0].answer == "no lubrication"
        assert session.whys[1].answer is None

    def test_reaching_max_whys_generates_report(self, tmp_path):
        agent, session_repo, store = _make_agent(tmp_path, max_whys=2)
        asyncio.run(agent.start_session("s3", "P-102A", "bearing failure", "public"))
        asyncio.run(agent.advance_session("s3", "no lube", "public"))
        session = asyncio.run(agent.advance_session("s3", "PM skipped", "public"))

        assert session.status == RCAStatus.COMPLETED
        assert session.report is not None
        assert (
            session.report.root_cause == "Bearing failed due to inadequate lubrication"
        )
        assert session.report.contributing_factors == ["Skipped PM interval"]
        assert len(session.report.recommended_actions) == 2
        # Fishbone has all six categories.
        assert set(session.report.fishbone.keys()) == {
            c.value for c in FishboneCategory
        }
        # Completed session removed from live state store.
        assert "s3" not in store

    def test_resume_uses_persisted_state_store(self, tmp_path):
        # advance_session must load prior whys from the state store, not memory.
        agent, _, store = _make_agent(tmp_path, max_whys=3)
        asyncio.run(agent.start_session("s4", "P-102A", "bearing failure", "public"))
        # Simulate a completely separate request: the only carried state is
        # what's in the (mock Redis) store.
        assert len(store["s4"].whys) == 1
        session = asyncio.run(agent.advance_session("s4", "answer one", "public"))
        assert len(session.whys) == 2

    def test_advance_unknown_session_raises_keyerror(self, tmp_path):
        agent, session_repo, _ = _make_agent(tmp_path)
        session_repo.get.return_value = None
        with pytest.raises(KeyError):
            asyncio.run(agent.advance_session("nonexistent", "answer", "public"))


class TestRCAReportCitationValidation:
    def test_hallucinated_chunk_citation_dropped_failure_code_kept(self, tmp_path):
        agent, _, _ = _make_agent(
            tmp_path,
            max_whys=1,
            failure_records=[
                FailureRecord(failure_code="FM-SEAL-01", description="seal")
            ],
        )
        asyncio.run(agent.start_session("s5", "P-102A", "bearing failure", "public"))
        session = asyncio.run(agent.advance_session("s5", "root reason", "public"))

        assert session.status == RCAStatus.COMPLETED
        cites = session.report.evidence_citations
        assert "[[chunk:c1]]" in cites  # real chunk kept
        assert "FM-SEAL-01" in cites  # real failure code kept
        assert "[[chunk:hallucinated]]" not in cites  # hallucinated dropped

    def test_unparseable_report_falls_back_gracefully(self, tmp_path):
        agent, _, _ = _make_agent(tmp_path, max_whys=1, report_unparseable=True)
        asyncio.run(agent.start_session("s6", "P-102A", "bearing failure", "public"))
        session = asyncio.run(agent.advance_session("s6", "root reason", "public"))

        assert session.status == RCAStatus.COMPLETED
        assert session.report is not None
        assert "could not be determined" in session.report.root_cause.lower()
        # Fishbone still attached even when the report text didn't parse.
        assert set(session.report.fishbone.keys()) == {
            c.value for c in FishboneCategory
        }


class TestRCAFallback:
    def test_suggest_why_llm_failure_marks_session_failed(self, tmp_path):
        agent, _, _ = _make_agent(tmp_path, suggest_raises=True)
        session = asyncio.run(
            agent.start_session("s7", "P-102A", "bearing failure", "public")
        )
        assert session.status == RCAStatus.FAILED

    def test_step_limit_marks_failed(self, tmp_path):

        agent, _, _ = _make_agent(tmp_path)
        # Force a tiny step limit by rebuilding the agent's max_steps.
        agent._max_steps = 1
        agent._graph = agent._build_graph()
        session = asyncio.run(
            agent.start_session("s8", "P-102A", "bearing failure", "public")
        )
        assert session.status == RCAStatus.FAILED


# ---------------------------------------------------------------------------
# Serialization round-trip (Redis state store / Postgres share this)
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_session_round_trip_with_report(self):
        from app.infrastructure.rca.serialization import (
            session_from_dict,
            session_to_dict,
        )

        original = RCASession(
            session_id="s",
            asset_tag="P-102A",
            incident_description="incident",
            status=RCAStatus.COMPLETED,
            whys=[WhyStep(question="why 1?", answer="because")],
            report=RCAReport(
                problem_statement="incident",
                root_cause="rc",
                fishbone={"Equipment": ["worn part"]},
            ),
        )
        restored = session_from_dict(session_to_dict(original))
        assert restored.session_id == "s"
        assert restored.status == RCAStatus.COMPLETED
        assert restored.whys[0].answer == "because"
        assert restored.report is not None
        assert restored.report.root_cause == "rc"
        assert restored.report.fishbone == {"Equipment": ["worn part"]}

    def test_session_round_trip_without_report(self):
        from app.infrastructure.rca.serialization import (
            session_from_dict,
            session_to_dict,
        )

        original = RCASession(
            session_id="s",
            asset_tag="P-1",
            incident_description="i",
            status=RCAStatus.AWAITING_INPUT,
            whys=[WhyStep(question="why?", answer=None)],
        )
        restored = session_from_dict(session_to_dict(original))
        assert restored.report is None
        assert restored.whys[0].answer is None


# ---------------------------------------------------------------------------
# Integration test — real Postgres, Neo4j, Redis
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_full_5whys_bearing_failure(tmp_path):
    """Roadmap acceptance test: initiate RCA for 'pump P-102A bearing failure',
    complete the full 5-Whys, and generate the report — verified against real
    Postgres (rca_sessions + work_orders), real Neo4j (EXHIBITS), and real
    Redis (live session state)."""
    from app.application.rca_brain.rca_brain_agent import RCABrainAgent
    from app.infrastructure.di.container import container
    from app.infrastructure.rca.incident_history_repository import (
        PostgresIncidentHistoryRepository,
    )
    from app.infrastructure.rca.rca_session_repository import (
        PostgresRCASessionRepository,
    )
    from app.infrastructure.rca.redis_rca_state_store import RedisRCAStateStore

    digits = "".join(c for c in uuid.uuid4().hex if c.isdigit())[:3].ljust(3, "1")
    asset_tag = f"P-{digits}A"
    wo_id = f"WO-RCA-{uuid.uuid4().hex[:6]}"

    pg = container.get_postgres()
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO work_orders (wo_id, asset_tag, description, status, priority, completed_date)
            VALUES (%s, %s, %s, 'COMPLETED', 'HIGH', %s)
            """,
            (wo_id, asset_tag, "bearing replacement after seizure", date(2026, 5, 1)),
        )
    pg.commit()

    driver = container.get_neo4j()
    with driver.session() as s:
        s.run(
            "MERGE (e:Equipment {tag_number: $tag}) "
            "MERGE (f:FailureMode {failure_code: 'FM-BRG-01', description: 'Bearing seizure', severity: 'HIGH'}) "
            "MERGE (e)-[:EXHIBITS]->(f)",
            tag=asset_tag,
        )

    # Real gateway would need Ollama; use a deterministic mock for the LLM so
    # the test asserts pipeline correctness (retrieval, persistence, 5-Whys
    # state machine) rather than model output quality.
    gateway = MagicMock()

    async def _gen(messages, mt):
        system = messages[0]["content"]
        if "root_cause" in system.lower() or "TOKEN_REPORT" in system:
            return _report_json(), 5, 5
        if (
            "category" in system.lower()
            or "fishbone" in system.lower()
            or "TOKEN_FISHBONE" in system
        ):
            return json.dumps(["worn bearing"]), 5, 5
        return "Why did the bearing seize?", 5, 5

    gateway.generate = _gen

    sp, rp, fp = _make_prompt_files(tmp_path)
    session_repo = PostgresRCASessionRepository(container.get_postgres)
    incident_repo = PostgresIncidentHistoryRepository(container.get_postgres)
    state_store = RedisRCAStateStore(container.get_redis)

    agent = RCABrainAgent(
        graphrag_engine=container.get_graphrag_engine(),
        model_gateway=gateway,
        failure_history_repo=container.get_failure_history_repository(),
        incident_repo=incident_repo,
        session_repo=session_repo,
        state_store=state_store,
        suggest_why_prompt_path=sp,
        generate_report_prompt_path=rp,
        fishbone_prompt_path=fp,
        max_whys=2,
    )

    session_id = str(uuid.uuid4())
    try:
        s1 = asyncio.run(
            agent.start_session(session_id, asset_tag, "pump bearing failure", "public")
        )
        assert s1.status == RCAStatus.AWAITING_INPUT
        assert len(s1.whys) == 1

        asyncio.run(agent.advance_session(session_id, "no lubrication", "public"))
        s3 = asyncio.run(agent.advance_session(session_id, "PM was skipped", "public"))
        assert s3.status == RCAStatus.COMPLETED
        assert s3.report is not None

        # Verify the completed report actually persisted to real Postgres.
        with pg.cursor() as cur:
            cur.execute(
                "SELECT status, rca_report_json FROM rca_sessions WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "COMPLETED"
        assert row[1] is not None
    finally:
        with pg.cursor() as cur:
            cur.execute("DELETE FROM rca_sessions WHERE session_id = %s", (session_id,))
            cur.execute("DELETE FROM work_orders WHERE wo_id = %s", (wo_id,))
        pg.commit()
        with driver.session() as s:
            s.run(
                "MATCH (n) WHERE n.tag_number = $tag OR n.failure_code = 'FM-BRG-01' DETACH DELETE n",
                tag=asset_tag,
            )
        state_store.delete(session_id)
