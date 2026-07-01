"""MaintenanceBrainAgent — LangGraph state machine for the Maintenance
sub-brain (M10, ADR-007). Reuses the Knowledge Brain (M9) pattern: return-
value-based step counting, per-node try/except with error_flag fallback,
and conditional edges that skip straight to format_response on error.

Graph:
    classify_maintenance_query --(asset_tag found)--> retrieve_asset_context
    classify_maintenance_query --(no asset_tag)------> synthesize_guidance
    retrieve_asset_context --> retrieve_work_orders --> synthesize_guidance
    synthesize_guidance --> format_response --> END

    Any node -> format_response directly whenever error_flag becomes True.

Citation validation (the same [[chunk:<id>]] marker convention as M9) is
folded into format_response rather than a separate graph node, since the
M10 checklist specifies exactly five nodes: classify_maintenance_query,
retrieve_asset_context, retrieve_work_orders, synthesize_guidance,
format_response.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml  # type: ignore[import-untyped]
from langgraph.graph import END, StateGraph

from app.domain.chat.interfaces import IChatHistoryRepository, IModelGateway
from app.domain.chat.models import ChatMessage, Citation, MessageRole
from app.domain.extraction.interfaces import IEntityExtractor
from app.domain.graphrag.interfaces import IGraphRAGEngine
from app.domain.maintenance_brain.interfaces import (
    IFailureHistoryRepository,
    IMaintenanceBrainAgent,
    IWorkOrderRepository,
)
from app.domain.maintenance_brain.models import (
    FailureRecord,
    MaintenanceAgentState,
    WorkOrder,
)
from app.domain.search.models import SearchResult

from ai.agents.maintenance_brain.tools import (
    extract_asset_tag_tool,
    failure_history_search,
    maintenance_schedule_query,
    oem_manual_lookup,
    work_order_lookup,
)

logger = logging.getLogger(__name__)

MAX_STEPS = 10
_CITATION_PATTERN = re.compile(r"\[\[chunk:([^\]]+)\]\]")
_WO_ID_PATTERN = re.compile(r"\bWO-\d+\b", re.I)


class StepLimitExceededError(Exception):
    """Raised when the agent exceeds its configured max step count."""


class MaintenanceBrainAgent(IMaintenanceBrainAgent):
    def __init__(
        self,
        graphrag_engine: IGraphRAGEngine,
        entity_extractor: IEntityExtractor,
        work_order_repo: IWorkOrderRepository,
        failure_history_repo: IFailureHistoryRepository,
        model_gateway: IModelGateway,
        history_repo: IChatHistoryRepository,
        prompt_path: Path,
        max_steps: int = MAX_STEPS,
        top_k: int = 5,
        max_tokens: int = 2048,
        session_ttl_seconds: int = 3600,
    ) -> None:
        self._graphrag = graphrag_engine
        self._entity_extractor = entity_extractor
        self._work_order_repo = work_order_repo
        self._failure_history_repo = failure_history_repo
        self._gateway = model_gateway
        self._history = history_repo
        self._prompt = _load_prompt(prompt_path)
        self._max_steps = max_steps
        self._top_k = top_k
        self._max_tokens = max_tokens
        self._session_ttl = session_ttl_seconds
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self, query: str, session_id: str, user_role: str
    ) -> MaintenanceAgentState:
        initial: MaintenanceAgentState = {
            "query": query,
            "session_id": session_id,
            "user_role": user_role,
            "asset_tag": None,
            "work_orders": [],
            "failure_history": [],
            "retrieved_chunks": [],
            "draft_answer": "",
            "citations": [],
            "step_count": 0,
            "error_flag": False,
        }
        try:
            final_state: MaintenanceAgentState = await self._graph.ainvoke(initial)
        except StepLimitExceededError as exc:
            logger.error("Maintenance Brain step limit exceeded: %s", exc)
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
        graph = StateGraph(MaintenanceAgentState)
        graph.add_node("classify_maintenance_query", self._classify_maintenance_query)
        graph.add_node("retrieve_asset_context", self._retrieve_asset_context)
        graph.add_node("retrieve_work_orders", self._retrieve_work_orders)
        graph.add_node("synthesize_guidance", self._synthesize_guidance)
        graph.add_node("format_response", self._format_response)

        graph.set_entry_point("classify_maintenance_query")
        graph.add_conditional_edges(
            "classify_maintenance_query",
            self._route_after_classification,
            {
                "retrieve": "retrieve_asset_context",
                "uncertain": "synthesize_guidance",
                "error": "format_response",
            },
        )
        graph.add_conditional_edges(
            "retrieve_asset_context",
            _error_or(default="retrieve_work_orders"),
            {
                "error": "format_response",
                "retrieve_work_orders": "retrieve_work_orders",
            },
        )
        graph.add_conditional_edges(
            "retrieve_work_orders",
            _error_or(default="synthesize_guidance"),
            {"error": "format_response", "synthesize_guidance": "synthesize_guidance"},
        )
        graph.add_conditional_edges(
            "synthesize_guidance",
            _error_or(default="format_response"),
            {"error": "format_response", "format_response": "format_response"},
        )
        graph.add_edge("format_response", END)
        return graph.compile()

    def _check_step_limit(self, state: MaintenanceAgentState) -> int:
        """Returns the incremented step count. LangGraph only merges a
        node's *returned* dict into its managed state — mutating `state`
        in place has no effect — so every node must include this value
        in its own return dict (see M9's KnowledgeBrainAgent for the same
        lesson learned)."""
        new_count = state["step_count"] + 1
        if new_count > self._max_steps:
            raise StepLimitExceededError(
                f"STEP_LIMIT_EXCEEDED: exceeded {self._max_steps} steps "
                f"(session={state['session_id']})"
            )
        return new_count

    def _route_after_classification(self, state: MaintenanceAgentState) -> str:
        if state["error_flag"]:
            return "error"
        return "retrieve" if state["asset_tag"] else "uncertain"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _classify_maintenance_query(
        self, state: MaintenanceAgentState
    ) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            asset_tag = extract_asset_tag_tool(self._entity_extractor, state["query"])
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Maintenance Brain node executed",
                extra={
                    "node": "classify_maintenance_query",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "asset_tag": asset_tag,
                    "session_id": state["session_id"],
                },
            )
            return {"asset_tag": asset_tag, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Maintenance Brain classify_maintenance_query failed: %s",
                exc,
                extra={
                    "node": "classify_maintenance_query",
                    "session_id": state["session_id"],
                },
            )
            return {"error_flag": True, "step_count": step_count}

    async def _retrieve_asset_context(
        self, state: MaintenanceAgentState
    ) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            asset_tag = state["asset_tag"]
            failure_history: List[FailureRecord] = failure_history_search(
                self._failure_history_repo, asset_tag
            )
            hybrid = await oem_manual_lookup(
                self._graphrag, state["query"], state["user_role"], self._top_k
            )
            retrieved_chunks: List[SearchResult] = [
                rc.result for rc in hybrid.ranked_chunks
            ]

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Maintenance Brain node executed",
                extra={
                    "node": "retrieve_asset_context",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "asset_tag": asset_tag,
                    "failure_records_found": len(failure_history),
                    "manual_chunks_found": len(retrieved_chunks),
                    "session_id": state["session_id"],
                },
            )
            return {
                "failure_history": failure_history,
                "retrieved_chunks": retrieved_chunks,
                "step_count": step_count,
            }
        except Exception as exc:
            logger.error(
                "Maintenance Brain retrieve_asset_context failed — degrading to partial answer: %s",
                exc,
                extra={
                    "node": "retrieve_asset_context",
                    "session_id": state["session_id"],
                },
            )
            return {"error_flag": True, "step_count": step_count}

    def _retrieve_work_orders(self, state: MaintenanceAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            asset_tag = state["asset_tag"]
            wo_match = _WO_ID_PATTERN.search(state["query"])
            if wo_match:
                work_orders: List[WorkOrder] = work_order_lookup(
                    self._work_order_repo, wo_id=wo_match.group(0).upper()
                )
            else:
                work_orders = maintenance_schedule_query(
                    self._work_order_repo, asset_tag
                )

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Maintenance Brain node executed",
                extra={
                    "node": "retrieve_work_orders",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "asset_tag": asset_tag,
                    "work_orders_found": len(work_orders),
                    "session_id": state["session_id"],
                },
            )
            return {"work_orders": work_orders, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Maintenance Brain retrieve_work_orders failed — degrading to partial answer: %s",
                exc,
                extra={
                    "node": "retrieve_work_orders",
                    "session_id": state["session_id"],
                },
            )
            return {"error_flag": True, "step_count": step_count}

    async def _synthesize_guidance(
        self, state: MaintenanceAgentState
    ) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            if not state["asset_tag"]:
                user_content = self._prompt.get("uncertain_template", "{query}").format(
                    query=state["query"]
                )
            else:
                user_content = self._prompt.get("user_template", "{query}").format(
                    asset_tag=state["asset_tag"],
                    work_orders_block=_format_work_orders(state["work_orders"]),
                    failure_history_block=_format_failure_history(
                        state["failure_history"]
                    ),
                    context_blocks=_format_context_blocks(state["retrieved_chunks"])
                    or "(no matching OEM manual content found)",
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
                "Maintenance Brain node executed",
                extra={
                    "node": "synthesize_guidance",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "asset_tag": state["asset_tag"],
                    "session_id": state["session_id"],
                },
            )
            return {"draft_answer": text, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Maintenance Brain synthesize_guidance failed — degrading to partial answer: %s",
                exc,
                extra={
                    "node": "synthesize_guidance",
                    "session_id": state["session_id"],
                },
            )
            return {"error_flag": True, "step_count": step_count}

    def _format_response(self, state: MaintenanceAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            by_chunk_id = {c.chunk_id: c for c in state["retrieved_chunks"]}
            seen: set = set()
            citations: List[Citation] = []
            for match in _CITATION_PATTERN.finditer(state["draft_answer"]):
                chunk_id = match.group(1)
                if chunk_id in by_chunk_id and chunk_id not in seen:
                    seen.add(chunk_id)
                    sr = by_chunk_id[chunk_id]
                    citations.append(
                        Citation(
                            chunk_id=sr.chunk_id,
                            document_title=sr.document_title,
                            page_number=sr.page_number,
                            chunk_text_excerpt=sr.text[:200],
                            score=round(sr.score, 4),
                            storage_key=sr.document_id,
                        )
                    )

            footnote_of = {c.chunk_id: i + 1 for i, c in enumerate(citations)}

            def _replace(match: "re.Match[str]") -> str:
                chunk_id = match.group(1)
                return f"[{footnote_of[chunk_id]}]" if chunk_id in footnote_of else ""

            rendered = _CITATION_PATTERN.sub(_replace, state["draft_answer"])

            if citations:
                lines = ["", "**Manual Sources:**"]
                for i, c in enumerate(citations, start=1):
                    page_str = f"p.{c.page_number}" if c.page_number else "p.?"
                    lines.append(f"{i}. {c.document_title}, {page_str}")
                rendered = rendered.rstrip() + "\n" + "\n".join(lines)

            if state["error_flag"]:
                if not rendered.strip():
                    rendered = (
                        "I was unable to fully process this maintenance request due "
                        "to an internal issue. Please try rephrasing your question."
                    )
                else:
                    rendered += (
                        "\n\n_Note: this response may be incomplete — an internal "
                        "step failed while processing your request._"
                    )

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Maintenance Brain node executed",
                extra={
                    "node": "format_response",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "asset_tag": state["asset_tag"],
                    "session_id": state["session_id"],
                },
            )
            return {
                "draft_answer": rendered,
                "citations": citations,
                "step_count": step_count,
            }
        except Exception as exc:
            logger.error(
                "Maintenance Brain format_response failed: %s",
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

    # ------------------------------------------------------------------
    # Session persistence (Redis, shared with M5/M9's chat history)
    # ------------------------------------------------------------------

    def _persist_turn(
        self, session_id: str, query: str, state: MaintenanceAgentState
    ) -> None:
        user_msg = ChatMessage(role=MessageRole.USER, content=query)
        assistant_msg = ChatMessage(
            role=MessageRole.ASSISTANT, content=state["draft_answer"]
        )
        self._history.append_messages(
            session_id, [user_msg, assistant_msg], self._session_ttl
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _error_or(default: str):
    def _selector(state: MaintenanceAgentState) -> str:
        return "error" if state["error_flag"] else default

    return _selector


def _format_context_blocks(chunks: List[SearchResult]) -> str:
    blocks = []
    for c in chunks:
        page_str = f"p.{c.page_number}" if c.page_number else "p.?"
        blocks.append(
            f"[chunk_id: {c.chunk_id} | {c.document_title}, {page_str}]\n{c.text}"
        )
    return "\n\n---\n\n".join(blocks)


def _format_work_orders(work_orders: List[WorkOrder]) -> str:
    if not work_orders:
        return "(no open work orders found for this asset)"
    lines = []
    for wo in work_orders:
        sched = wo.scheduled_date.isoformat() if wo.scheduled_date else "unscheduled"
        lines.append(
            f"- {wo.wo_id} [{wo.priority}] {wo.description} "
            f"(status={wo.status}, scheduled={sched})"
        )
    return "\n".join(lines)


def _format_failure_history(failure_history: List[FailureRecord]) -> str:
    if not failure_history:
        return "(no failure history found for this asset)"
    lines = []
    for f in failure_history:
        lines.append(
            f"- {f.failure_code}: {f.description}"
            + (f" (severity={f.severity})" if f.severity else "")
        )
    return "\n".join(lines)


def _load_prompt(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
