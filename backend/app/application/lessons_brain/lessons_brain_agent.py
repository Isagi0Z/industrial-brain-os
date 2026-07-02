"""LessonsLearnedBrainAgent — LangGraph state machine for the Lessons
Learned sub-brain (M13, ADR-007). Reuses the Knowledge (M9) / Maintenance
(M10) / Compliance (M11) / RCA (M12) pattern: return-value-based step
counting, per-node try/except with error_flag fallback, and conditional
edges that skip straight to END on error.

Incident ingestion graph (POST /api/v1/incidents):

    analyze_incident --> extract_patterns --> link_to_ontology
        --> store_lesson --> generate_summary --> END

`chat()` is a separate, non-graph entry point for
`POST /api/v1/brain/lessons/chat` — a direct semantic search of the
`lessons_learned` Qdrant collection followed by one LLM synthesis call,
deliberately simpler than the Knowledge Brain's full GraphRAG pipeline
since this sub-brain only ever answers from the lessons collection
(Engineering Bible §1 — keep it simple).
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping

from langgraph.graph import END, StateGraph

from app.application.agents.base import (
    BaseBrainAgent,
    StepLimitExceededError,
    load_prompt,
)
from app.domain.chat.interfaces import IChatHistoryRepository, IModelGateway
from app.domain.chat.models import ChatMessage, Citation, MessageRole
from app.domain.lessons_brain.interfaces import (
    ILessonRepository,
    ILessonsLearnedBrainAgent,
)
from app.domain.lessons_brain.models import (
    Incident,
    LessonLearned,
    LessonsAgentState,
)
from app.domain.maintenance_brain.interfaces import IFailureHistoryRepository
from app.domain.ontology.interfaces import IOntologyValidator
from app.domain.ontology.models import OntologyViolationError
from app.domain.search.interfaces import IEmbeddingService, IVectorRepository

from ai.agents.lessons_brain.tools import (
    LESSONS_LEARNED_COLLECTION,
    failure_pattern_match,
    find_similar_lessons,
    generate_lesson_summary,
    synthesize_chat_answer,
)

logger = logging.getLogger(__name__)

MAX_STEPS = 10


class IncidentProcessingError(Exception):
    """Raised when the ingestion graph fails to produce a stored lesson."""


class LessonsLearnedBrainAgent(BaseBrainAgent, ILessonsLearnedBrainAgent):
    def __init__(
        self,
        embedding_service: IEmbeddingService,
        vector_repo: IVectorRepository,
        lesson_repo: ILessonRepository,
        failure_history_repo: IFailureHistoryRepository,
        ontology_validator: IOntologyValidator,
        model_gateway: IModelGateway,
        history_repo: IChatHistoryRepository,
        generate_summary_prompt_path: Path,
        chat_prompt_path: Path,
        max_steps: int = MAX_STEPS,
        similar_lessons_limit: int = 3,
        chat_top_k: int = 5,
        max_tokens: int = 2048,
        session_ttl_seconds: int = 3600,
    ) -> None:
        self._embedding_service = embedding_service
        self._vector_repo = vector_repo
        self._lesson_repo = lesson_repo
        self._failure_history_repo = failure_history_repo
        self._ontology_validator = ontology_validator
        self._gateway = model_gateway
        self._history = history_repo
        self._summary_prompt = load_prompt(generate_summary_prompt_path)
        self._chat_prompt = load_prompt(chat_prompt_path)
        self._max_steps = max_steps
        self._similar_lessons_limit = similar_lessons_limit
        self._chat_top_k = chat_top_k
        self._max_tokens = max_tokens
        self._session_ttl = session_ttl_seconds
        # The lessons_learned collection is created once at application
        # startup by infra_init.py (M1 pattern) — not here.
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def ingest_incident(self, incident: Incident) -> LessonLearned:
        initial: LessonsAgentState = {
            "incident": incident,
            "similar_lesson_summaries": [],
            "failure_mode_candidates": [],
            "lesson_id": str(uuid.uuid4()),
            "summary": "",
            "link_result": None,
            "lesson": None,
            "step_count": 0,
            "error_flag": False,
        }
        try:
            final_state: LessonsAgentState = await self._graph.ainvoke(initial)
        except StepLimitExceededError as exc:
            logger.error("Lessons Brain step limit exceeded: %s", exc)
            raise IncidentProcessingError(str(exc)) from exc

        if final_state["error_flag"] or final_state["lesson"] is None:
            raise IncidentProcessingError(
                f"Incident ingestion failed for asset_tag={incident.asset_tag}"
            )
        return final_state["lesson"]

    async def chat(self, query: str, session_id: str, user_role: str) -> dict:
        error_flag = False
        citations: List[Citation] = []
        try:
            hits = find_similar_lessons(
                self._embedding_service,
                self._vector_repo,
                query,
                user_role,
                self._chat_top_k,
            )
            lessons_block = "\n\n---\n\n".join(
                f"[lesson_id: {h.chunk_id} | asset: {h.document_id}]\n{h.text}"
                for h in hits
            )
            citations = [
                Citation(
                    chunk_id=h.chunk_id,
                    document_title=h.document_title,
                    page_number=None,
                    chunk_text_excerpt=h.text[:200],
                    score=round(h.score, 4),
                    storage_key=h.document_id,
                )
                for h in hits
            ]
            answer = await synthesize_chat_answer(
                self._gateway, self._chat_prompt, query, lessons_block, self._max_tokens
            )
        except Exception as exc:
            logger.error(
                "Lessons Brain chat failed: %s", exc, extra={"session_id": session_id}
            )
            error_flag = True
            answer = (
                "I was unable to search historical lessons due to an internal "
                "issue. Please try again."
            )

        self._history.append_messages(
            session_id,
            [
                ChatMessage(role=MessageRole.USER, content=query),
                ChatMessage(role=MessageRole.ASSISTANT, content=answer),
            ],
            self._session_ttl,
        )
        return {
            "answer": answer,
            "citations": citations,
            "session_id": session_id,
            "error_flag": error_flag,
            "step_count": 1,
        }

    # ------------------------------------------------------------------
    # Graph construction (incident ingestion)
    # ------------------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(LessonsAgentState)
        graph.add_node("analyze_incident", self._analyze_incident)
        graph.add_node("extract_patterns", self._extract_patterns)
        graph.add_node("link_to_ontology", self._link_to_ontology)
        graph.add_node("store_lesson", self._store_lesson)
        graph.add_node("generate_summary", self._generate_summary)

        graph.set_entry_point("analyze_incident")
        graph.add_conditional_edges(
            "analyze_incident",
            self._error_or(default="extract_patterns"),
            {"error": END, "extract_patterns": "extract_patterns"},
        )
        graph.add_conditional_edges(
            "extract_patterns",
            self._error_or(default="link_to_ontology"),
            {"error": END, "link_to_ontology": "link_to_ontology"},
        )
        graph.add_conditional_edges(
            "link_to_ontology",
            self._error_or(default="store_lesson"),
            {"error": END, "store_lesson": "store_lesson"},
        )
        graph.add_conditional_edges(
            "store_lesson",
            self._error_or(default="generate_summary"),
            {"error": END, "generate_summary": "generate_summary"},
        )
        graph.add_edge("generate_summary", END)
        return graph.compile()

    def _step_limit_context(self, state: Mapping[str, Any]) -> str:
        # The ingestion state has no session_id, so the step-limit message
        # keys on the incident's asset_tag (byte-identical to pre-refactor).
        return f"asset_tag={state['incident'].asset_tag}"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _analyze_incident(self, state: LessonsAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            incident = state["incident"]
            matches = failure_pattern_match(
                self._failure_history_repo, incident.asset_tag
            )
            failure_codes = [m.failure_code for m in matches]
            logger.info(
                "Lessons Brain node executed",
                extra={
                    "node": "analyze_incident",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "asset_tag": incident.asset_tag,
                    "failure_mode_candidates": len(failure_codes),
                },
            )
            return {
                "failure_mode_candidates": failure_codes,
                "step_count": step_count,
            }
        except Exception as exc:
            logger.error("Lessons Brain analyze_incident failed: %s", exc)
            return {"error_flag": True, "step_count": step_count}

    def _extract_patterns(self, state: LessonsAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            incident = state["incident"]
            similar = find_similar_lessons(
                self._embedding_service,
                self._vector_repo,
                incident.description,
                incident.role_scope,
                self._similar_lessons_limit,
            )
            summaries = [h.text for h in similar]
            logger.info(
                "Lessons Brain node executed",
                extra={
                    "node": "extract_patterns",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "similar_lessons_found": len(summaries),
                    "asset_tag": incident.asset_tag,
                },
            )
            return {"similar_lesson_summaries": summaries, "step_count": step_count}
        except Exception as exc:
            logger.error("Lessons Brain extract_patterns failed: %s", exc)
            return {"error_flag": True, "step_count": step_count}

    def _link_to_ontology(self, state: LessonsAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            incident = state["incident"]
            self._ontology_validator.validate_node(
                "LessonLearned",
                {
                    "lesson_id": state["lesson_id"],
                    "asset_tag": incident.asset_tag,
                    "incident_date": incident.incident_date.isoformat(),
                    "description": incident.description,
                },
            )
            self._ontology_validator.validate_relation(
                "LessonLearned", "RELATED_TO", "Equipment"
            )
            self._ontology_validator.validate_relation(
                "LessonLearned", "REFERENCES", "FailureMode"
            )
            logger.info(
                "Lessons Brain node executed",
                extra={
                    "node": "link_to_ontology",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "asset_tag": incident.asset_tag,
                },
            )
            return {"step_count": step_count}
        except OntologyViolationError as exc:
            logger.error("Lessons Brain ontology violation: %s", exc)
            return {"error_flag": True, "step_count": step_count}
        except Exception as exc:
            logger.error("Lessons Brain link_to_ontology failed: %s", exc)
            return {"error_flag": True, "step_count": step_count}

    def _store_lesson(self, state: LessonsAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            incident = state["incident"]
            lesson = LessonLearned(
                lesson_id=state["lesson_id"],
                asset_tag=incident.asset_tag,
                incident_date=incident.incident_date,
                description=incident.description,
                root_cause=incident.root_cause,
                corrective_actions=list(incident.corrective_actions),
                severity=incident.severity,
                role_scope=incident.role_scope,
            )

            vector = self._embedding_service.embed_one(incident.description)
            self._vector_repo.upsert(
                LESSONS_LEARNED_COLLECTION,
                lesson.lesson_id,
                vector,
                {
                    "document_id": lesson.lesson_id,
                    "document_title": lesson.asset_tag,
                    "chunk_type": "paragraph",
                    "text": incident.description,
                    "role_scope": lesson.role_scope,
                },
            )

            link_result = self._lesson_repo.create(
                lesson, state["failure_mode_candidates"]
            )
            lesson.equipment_linked = link_result.equipment_linked
            lesson.failure_modes_linked = link_result.failure_modes_linked

            logger.info(
                "Lessons Brain node executed",
                extra={
                    "node": "store_lesson",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "lesson_id": lesson.lesson_id,
                    "equipment_linked": link_result.equipment_linked,
                    "failure_modes_linked": len(link_result.failure_modes_linked),
                },
            )
            return {
                "lesson": lesson,
                "link_result": link_result,
                "step_count": step_count,
            }
        except Exception as exc:
            logger.error("Lessons Brain store_lesson failed: %s", exc)
            return {"error_flag": True, "step_count": step_count}

    async def _generate_summary(self, state: LessonsAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            incident = state["incident"]
            lesson = state["lesson"]
            summary = await generate_lesson_summary(
                self._gateway,
                self._summary_prompt,
                incident.asset_tag,
                incident.description,
                incident.root_cause,
                incident.corrective_actions,
                self._max_tokens,
            )
            self._lesson_repo.update_summary(state["lesson_id"], summary)
            if lesson is not None:
                lesson.summary = summary

            logger.info(
                "Lessons Brain node executed",
                extra={
                    "node": "generate_summary",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "lesson_id": state["lesson_id"],
                },
            )
            return {"summary": summary, "lesson": lesson, "step_count": step_count}
        except Exception as exc:
            # A failed summary is not fatal — the lesson is already durably
            # stored (Neo4j + Qdrant) by store_lesson; degrade gracefully by
            # keeping the lesson with an empty summary rather than failing
            # the whole ingestion.
            logger.warning("Lessons Brain generate_summary failed: %s", exc)
            return {"step_count": step_count}
