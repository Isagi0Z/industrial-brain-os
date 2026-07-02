"""KnowledgeBrainAgent — LangGraph state machine for the Knowledge sub-brain (M9, ADR-007).

Graph:
    route_query --(document_search|entity_lookup|procedural)--> retrieve_context
    route_query --(unknown)--------------------------------------> synthesize_answer
    retrieve_context --> synthesize_answer --> validate_citations --> format_response --> END

    Any node -> format_response directly whenever error_flag becomes True
    (a tool/gateway exception is caught inside the node, not raised).

route_query's classification lives in `_classify_intent`, a pure function of
the query text with no side effects. It is called both by the conditional
edge selector attached to route_query (to decide the next node) and again
inside retrieve_context (to decide whether to run the full GraphRAGEngine
hybrid pipeline or a cheaper direct entity/graph lookup) — cheap and
deterministic, so recomputing it is preferable to adding a field to
AgentState that isn't in the M9 checklist's specified schema.

Step limit (Engineering Bible §21): `_check_step_limit` runs first in every
node, incrementing `step_count`. Exceeding `max_steps` raises
StepLimitExceededError, which aborts the graph run distinctly from a normal
tool failure (which sets error_flag and continues to format_response).

M13 addition: an optional `warning_detector` (Lessons Learned Brain) is
checked in `_format_response` — the one node every path (including error
paths) always reaches — and, above the similarity threshold, its warning is
prepended to the rendered answer. This is a value-add on top of the M9
graph, not a new branch: a detector failure is caught and logged exactly
like every other node's tool call, and never blocks the underlying answer.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List

from langgraph.graph import END, StateGraph
from starlette.concurrency import run_in_threadpool

from app.application.agents.base import (
    BaseBrainAgent,
    StepLimitExceededError,
    format_context_blocks as _format_context_blocks,
    load_prompt,
    render_citations,
    validate_chunk_citations,
)
from app.domain.chat.interfaces import IChatHistoryRepository, IModelGateway
from app.domain.extraction.interfaces import IEntityExtractor
from app.domain.graphrag.interfaces import IGraphRAGEngine, IKGTraversalService
from app.domain.graphrag.models import HybridSearchResult, KGPath
from app.domain.knowledge_brain.interfaces import IKnowledgeBrainAgent
from app.domain.knowledge_brain.models import AgentState
from app.domain.lessons_brain.interfaces import IProactiveWarningDetector
from app.domain.search.models import SearchResult

from ai.agents.knowledge_brain.tools import (
    entity_lookup_tool,
    graph_search_tool,
    semantic_search_tool,
)

logger = logging.getLogger(__name__)

MAX_STEPS = 10
_PROCEDURAL_KEYWORDS = re.compile(
    r"\b(how to|how do i|steps to|procedure|instructions|walk me through)\b", re.I
)


class KnowledgeBrainAgent(BaseBrainAgent, IKnowledgeBrainAgent):
    def __init__(
        self,
        graphrag_engine: IGraphRAGEngine,
        entity_extractor: IEntityExtractor,
        kg_traversal: IKGTraversalService,
        model_gateway: IModelGateway,
        history_repo: IChatHistoryRepository,
        prompt_path: Path,
        max_steps: int = MAX_STEPS,
        top_k: int = 5,
        kg_depth: int = 2,
        kg_limit: int = 50,
        max_tokens: int = 2048,
        session_ttl_seconds: int = 3600,
        warning_detector: IProactiveWarningDetector | None = None,
    ) -> None:
        self._graphrag = graphrag_engine
        self._entity_extractor = entity_extractor
        self._kg_traversal = kg_traversal
        self._gateway = model_gateway
        self._history = history_repo
        self._prompt = load_prompt(prompt_path)
        self._max_steps = max_steps
        self._top_k = top_k
        self._kg_depth = kg_depth
        self._kg_limit = kg_limit
        self._max_tokens = max_tokens
        self._session_ttl = session_ttl_seconds
        self._warning_detector = warning_detector
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, query: str, session_id: str, user_role: str) -> AgentState:
        initial: AgentState = {
            "query": query,
            "session_id": session_id,
            "user_role": user_role,
            "retrieved_chunks": [],
            "kg_paths": [],
            "draft_answer": "",
            "citations": [],
            "step_count": 0,
            "error_flag": False,
            "proactive_warning": None,
        }
        try:
            final_state: AgentState = await self._graph.ainvoke(initial)
        except StepLimitExceededError as exc:
            logger.error("Knowledge Brain step limit exceeded: %s", exc)
            final_state = dict(initial)  # type: ignore[assignment]
            final_state["error_flag"] = True
            final_state["draft_answer"] = (
                "STEP_LIMIT_EXCEEDED: this request could not be completed "
                "within the allowed number of processing steps."
            )

        self._persist_turn(session_id, query, final_state)
        return final_state

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("route_query", self._route_query)
        graph.add_node("retrieve_context", self._retrieve_context)
        graph.add_node("synthesize_answer", self._synthesize_answer)
        graph.add_node("validate_citations", self._validate_citations)
        graph.add_node("format_response", self._format_response)

        graph.set_entry_point("route_query")
        graph.add_conditional_edges(
            "route_query",
            self._route_after_classification,
            {
                "retrieve": "retrieve_context",
                "uncertain": "synthesize_answer",
                "error": "format_response",
            },
        )
        graph.add_conditional_edges(
            "retrieve_context",
            self._error_or(default="synthesize_answer"),
            {"error": "format_response", "synthesize_answer": "synthesize_answer"},
        )
        graph.add_conditional_edges(
            "synthesize_answer",
            self._error_or(default="validate_citations"),
            {"error": "format_response", "validate_citations": "validate_citations"},
        )
        graph.add_edge("validate_citations", "format_response")
        graph.add_edge("format_response", END)
        return graph.compile()

    def _route_after_classification(self, state: AgentState) -> str:
        if state["error_flag"]:
            return "error"
        intent = _classify_intent(state["query"])
        return "uncertain" if intent == "unknown" else "retrieve"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _route_query(self, state: AgentState) -> Dict[str, Any]:
        """Classification happens in `_route_after_classification` (the
        conditional edge attached to this node) — this node itself only
        enforces the step limit and logs the routing decision."""
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        intent = _classify_intent(state["query"])
        logger.info(
            "Knowledge Brain node executed",
            extra={
                "node": "route_query",
                "step": step_count,
                "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                "intent": intent,
                "session_id": state["session_id"],
            },
        )
        return {"step_count": step_count}

    async def _retrieve_context(self, state: AgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            intent = _classify_intent(state["query"])
            if intent == "entity_lookup":
                entities = entity_lookup_tool(self._entity_extractor, state["query"])
                tags = [e.tag_number for e in entities if e.tag_number]
                kg_paths = graph_search_tool(
                    self._kg_traversal, tags, self._kg_depth, self._kg_limit
                )
                retrieved_chunks: List[SearchResult] = []
            else:
                hybrid: HybridSearchResult = await semantic_search_tool(
                    self._graphrag, state["query"], state["user_role"], self._top_k
                )
                retrieved_chunks = [rc.result for rc in hybrid.ranked_chunks]
                kg_paths = hybrid.kg_paths

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Knowledge Brain node executed",
                extra={
                    "node": "retrieve_context",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "intent": intent,
                    "chunks_found": len(retrieved_chunks),
                    "kg_paths_found": len(kg_paths),
                    "session_id": state["session_id"],
                },
            )
            return {
                "retrieved_chunks": retrieved_chunks,
                "kg_paths": kg_paths,
                "step_count": step_count,
            }
        except Exception as exc:
            logger.error(
                "Knowledge Brain retrieve_context failed — degrading to partial answer: %s",
                exc,
                extra={"node": "retrieve_context", "session_id": state["session_id"]},
            )
            return {"error_flag": True, "step_count": step_count}

    async def _synthesize_answer(self, state: AgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            intent = _classify_intent(state["query"])
            if intent == "unknown":
                user_content = self._prompt.get("uncertain_template", "{query}").format(
                    query=state["query"]
                )
            else:
                context_blocks = _format_context_blocks(state["retrieved_chunks"])
                kg_markdown = _format_kg_markdown(state["kg_paths"])
                user_content = self._prompt.get("user_template", "{query}").format(
                    context_blocks=context_blocks
                    or "(no matching document chunks found)",
                    kg_markdown=kg_markdown or "(no related graph relationships found)",
                    query=state["query"],
                )

            messages: List[dict] = [
                {"role": "system", "content": self._prompt.get("system", "")}
            ]
            for msg in self._history.get_history(state["session_id"]):
                messages.append({"role": msg.role.value, "content": msg.content})
            messages.append({"role": "user", "content": user_content})

            text, _, _ = await self._gateway.generate(messages, self._max_tokens)

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Knowledge Brain node executed",
                extra={
                    "node": "synthesize_answer",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "session_id": state["session_id"],
                },
            )
            return {"draft_answer": text, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Knowledge Brain synthesize_answer failed — degrading to partial answer: %s",
                exc,
                extra={"node": "synthesize_answer", "session_id": state["session_id"]},
            )
            return {"error_flag": True, "step_count": step_count}

    def _validate_citations(self, state: AgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        if state["error_flag"]:
            return {"step_count": step_count}
        try:
            citations = validate_chunk_citations(
                state["draft_answer"], state["retrieved_chunks"]
            )

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Knowledge Brain node executed",
                extra={
                    "node": "validate_citations",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "citations_kept": len(citations),
                    "session_id": state["session_id"],
                },
            )
            return {"citations": citations, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Knowledge Brain validate_citations failed: %s",
                exc,
                extra={"node": "validate_citations", "session_id": state["session_id"]},
            )
            return {"error_flag": True, "step_count": step_count}

    async def _format_response(self, state: AgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            rendered = render_citations(state["draft_answer"], state["citations"])

            if state["error_flag"]:
                if not rendered.strip():
                    rendered = (
                        "I was unable to fully process this request due to an "
                        "internal issue. Please try rephrasing your question."
                    )
                else:
                    rendered += (
                        "\n\n_Note: this response may be incomplete — an internal "
                        "step failed while processing your request._"
                    )

            warning = await self._detect_proactive_warning(state)
            if warning is not None:
                rendered = (
                    f"⚠️ **Lessons Learned Warning** ({warning.incident_date}, "
                    f"asset {warning.asset_tag}, similarity {warning.similarity_score}): "
                    f"{warning.lesson_summary}\n\n" + rendered
                )

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Knowledge Brain node executed",
                extra={
                    "node": "format_response",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "session_id": state["session_id"],
                    "proactive_warning": warning is not None,
                },
            )
            return {
                "draft_answer": rendered,
                "proactive_warning": warning,
                "step_count": step_count,
            }
        except Exception as exc:
            logger.error(
                "Knowledge Brain format_response failed: %s",
                exc,
                extra={"node": "format_response", "session_id": state["session_id"]},
            )
            fallback = state.get("draft_answer") or (
                "An internal error occurred while formatting the response."
            )
            return {
                "draft_answer": fallback,
                "error_flag": True,
                "step_count": step_count,
            }

    async def _detect_proactive_warning(self, state: AgentState):
        """M13 — never lets a detector failure affect the underlying answer."""
        if self._warning_detector is None:
            return None
        try:
            return await run_in_threadpool(
                self._warning_detector.detect, state["query"], state["user_role"]
            )
        except Exception as exc:
            logger.warning(
                "Proactive warning detection failed: %s",
                exc,
                extra={"session_id": state["session_id"]},
            )
            return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _classify_intent(query: str) -> str:
    """document_search | entity_lookup | procedural | unknown — pure,
    deterministic, no LLM call (cheaper and more testable than an
    LLM-based router for this first sub-brain)."""
    stripped = query.strip()
    if not stripped:
        return "unknown"
    if re.search(r"\b[A-Z]{1,4}-\d+[A-Z]?\b", stripped) or re.search(
        r"\b[A-Z]{1,4}\d{3,}[A-Z]?\b", stripped
    ):
        return "entity_lookup"
    if _PROCEDURAL_KEYWORDS.search(stripped):
        return "procedural"
    return "document_search"


def _format_kg_markdown(kg_paths: List[KGPath]) -> str:
    if not kg_paths:
        return ""
    lines = ["| Source | Relation | Target |", "| --- | --- | --- |"]
    for p in kg_paths:
        lines.append(
            f"| {p.source_type}:{p.source_tag} | {p.relation_type} "
            f"| {p.target_type}:{p.target_tag} |"
        )
    return "\n".join(lines)
