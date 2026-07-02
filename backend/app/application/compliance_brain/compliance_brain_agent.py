"""ComplianceBrainAgent — LangGraph state machine for the Compliance
sub-brain (M11, ADR-007). Reuses the Knowledge Brain (M9) / Maintenance
Brain (M10) pattern: return-value-based step counting, per-node
try/except with error_flag fallback, and conditional edges that skip
straight to format_report on error.

Graph:
    identify_regulation_scope --> retrieve_procedures --> detect_gaps
        --> generate_evidence --> format_report --> END

    Any node -> format_report directly whenever error_flag becomes True.

Unlike the Knowledge/Maintenance Brains, there is no "uncertain intent"
branch here — an empty retrieval result (no matching regulation or
procedure found) is a normal, reportable outcome for a compliance check,
not a classification failure, so it flows through detect_gaps and
generate_evidence like any other case (both handle empty context
gracefully via their prompts).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from app.application.agents.base import (
    BaseBrainAgent,
    StepLimitExceededError,
    format_context_blocks as _format_context_blocks,
    load_prompt,
    render_citations,
    validate_chunk_citations,
)
from app.domain.chat.interfaces import IChatHistoryRepository, IModelGateway
from app.domain.compliance_brain.interfaces import (
    IComplianceBrainAgent,
    IComplianceReportRepository,
)
from app.domain.compliance_brain.models import ComplianceAgentState, ComplianceGapReport
from app.domain.graphrag.interfaces import IGraphRAGEngine
from app.domain.search.models import SearchResult

from ai.agents.compliance_brain.tools import (
    compliance_gap_detector,
    procedure_lookup,
    regulation_lookup,
)

logger = logging.getLogger(__name__)

MAX_STEPS = 10


class ComplianceBrainAgent(BaseBrainAgent, IComplianceBrainAgent):
    def __init__(
        self,
        graphrag_engine: IGraphRAGEngine,
        model_gateway: IModelGateway,
        report_repo: IComplianceReportRepository,
        history_repo: IChatHistoryRepository,
        gap_detection_prompt_path: Path,
        evidence_prompt_path: Path,
        max_steps: int = MAX_STEPS,
        top_k: int = 5,
        max_tokens: int = 2048,
        session_ttl_seconds: int = 3600,
    ) -> None:
        self._graphrag = graphrag_engine
        self._gateway = model_gateway
        self._report_repo = report_repo
        self._history = history_repo
        self._gap_prompt = load_prompt(gap_detection_prompt_path)
        self._evidence_prompt = load_prompt(evidence_prompt_path)
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
    ) -> ComplianceAgentState:
        initial: ComplianceAgentState = {
            "query": query,
            "session_id": session_id,
            "user_role": user_role,
            "regulation_chunks": [],
            "procedure_chunks": [],
            "gap_report": None,
            "draft_answer": "",
            "citations": [],
            "step_count": 0,
            "error_flag": False,
        }
        try:
            final_state: ComplianceAgentState = await self._graph.ainvoke(initial)
        except StepLimitExceededError as exc:
            logger.error("Compliance Brain step limit exceeded: %s", exc)
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
        graph = StateGraph(ComplianceAgentState)
        graph.add_node("identify_regulation_scope", self._identify_regulation_scope)
        graph.add_node("retrieve_procedures", self._retrieve_procedures)
        graph.add_node("detect_gaps", self._detect_gaps)
        graph.add_node("generate_evidence", self._generate_evidence)
        graph.add_node("format_report", self._format_report)

        graph.set_entry_point("identify_regulation_scope")
        graph.add_conditional_edges(
            "identify_regulation_scope",
            self._error_or(default="retrieve_procedures"),
            {"error": "format_report", "retrieve_procedures": "retrieve_procedures"},
        )
        graph.add_conditional_edges(
            "retrieve_procedures",
            self._error_or(default="detect_gaps"),
            {"error": "format_report", "detect_gaps": "detect_gaps"},
        )
        graph.add_conditional_edges(
            "detect_gaps",
            self._error_or(default="generate_evidence"),
            {"error": "format_report", "generate_evidence": "generate_evidence"},
        )
        graph.add_conditional_edges(
            "generate_evidence",
            self._error_or(default="format_report"),
            {"error": "format_report", "format_report": "format_report"},
        )
        graph.add_edge("format_report", END)
        return graph.compile()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _identify_regulation_scope(
        self, state: ComplianceAgentState
    ) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            hybrid = await regulation_lookup(
                self._graphrag, state["query"], state["user_role"], self._top_k
            )
            regulation_chunks: List[SearchResult] = [
                rc.result for rc in hybrid.ranked_chunks
            ]

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Compliance Brain node executed",
                extra={
                    "node": "identify_regulation_scope",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "regulation_chunks_found": len(regulation_chunks),
                    "session_id": state["session_id"],
                },
            )
            return {"regulation_chunks": regulation_chunks, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Compliance Brain identify_regulation_scope failed — degrading to partial answer: %s",
                exc,
                extra={
                    "node": "identify_regulation_scope",
                    "session_id": state["session_id"],
                },
            )
            return {"error_flag": True, "step_count": step_count}

    async def _retrieve_procedures(self, state: ComplianceAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            hybrid = await procedure_lookup(
                self._graphrag, state["query"], state["user_role"], self._top_k
            )
            procedure_chunks: List[SearchResult] = [
                rc.result for rc in hybrid.ranked_chunks
            ]

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Compliance Brain node executed",
                extra={
                    "node": "retrieve_procedures",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "procedure_chunks_found": len(procedure_chunks),
                    "session_id": state["session_id"],
                },
            )
            return {"procedure_chunks": procedure_chunks, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Compliance Brain retrieve_procedures failed — degrading to partial answer: %s",
                exc,
                extra={
                    "node": "retrieve_procedures",
                    "session_id": state["session_id"],
                },
            )
            return {"error_flag": True, "step_count": step_count}

    async def _detect_gaps(self, state: ComplianceAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            regulation_text = _format_context_blocks(state["regulation_chunks"])
            procedure_text = _format_context_blocks(state["procedure_chunks"])

            gap_report: ComplianceGapReport = await compliance_gap_detector(
                self._gateway,
                self._gap_prompt,
                regulation_text,
                procedure_text,
                regulation_query=state["query"],
                procedure_query=state["query"],
                max_tokens=self._max_tokens,
            )

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Compliance Brain node executed",
                extra={
                    "node": "detect_gaps",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "gaps_found": len(gap_report.gaps),
                    "has_critical_gaps": gap_report.has_critical_gaps,
                    "session_id": state["session_id"],
                },
            )
            return {"gap_report": gap_report, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Compliance Brain detect_gaps failed — degrading to partial answer: %s",
                exc,
                extra={"node": "detect_gaps", "session_id": state["session_id"]},
            )
            return {"error_flag": True, "step_count": step_count}

    async def _generate_evidence(self, state: ComplianceAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            gap_report = state["gap_report"]
            has_context = bool(state["regulation_chunks"] or state["procedure_chunks"])

            if not has_context:
                user_content = self._evidence_prompt.get(
                    "no_context_template", "{query}"
                ).format(query=state["query"])
            else:
                user_content = self._evidence_prompt.get(
                    "user_template", "{query}"
                ).format(
                    gaps_block=_format_gaps(gap_report),
                    regulation_context=_format_context_blocks(
                        state["regulation_chunks"]
                    )
                    or "(no matching regulation content found)",
                    procedure_context=_format_context_blocks(state["procedure_chunks"])
                    or "(no matching procedure content found)",
                    query=state["query"],
                )

            messages: List[dict] = [
                {"role": "system", "content": self._evidence_prompt.get("system", "")}
            ]
            for msg in self._history.get_history(state["session_id"]):
                messages.append({"role": msg.role.value, "content": msg.content})
            messages.append({"role": "user", "content": user_content})

            text, _, _ = await self._gateway.generate(messages, self._max_tokens)

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Compliance Brain node executed",
                extra={
                    "node": "generate_evidence",
                    "step": step_count,
                    "duration_ms": duration_ms,
                    "session_id": state["session_id"],
                },
            )
            return {"draft_answer": text, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "Compliance Brain generate_evidence failed — degrading to partial answer: %s",
                exc,
                extra={"node": "generate_evidence", "session_id": state["session_id"]},
            )
            return {"error_flag": True, "step_count": step_count}

    def _format_report(self, state: ComplianceAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            citations = validate_chunk_citations(
                state["draft_answer"],
                state["regulation_chunks"] + state["procedure_chunks"],
            )
            rendered = render_citations(
                state["draft_answer"], citations, sources_header="**Sources:**"
            )

            gap_report = state["gap_report"]
            if gap_report and gap_report.gaps:
                rendered = _format_gap_table(gap_report) + "\n\n" + rendered

            if state["error_flag"]:
                if not rendered.strip():
                    rendered = (
                        "I was unable to fully process this compliance request due "
                        "to an internal issue. Please try rephrasing your question."
                    )
                else:
                    rendered += (
                        "\n\n_Note: this response may be incomplete — an internal "
                        "step failed while processing your request._"
                    )

            if gap_report is not None:
                try:
                    self._report_repo.save(
                        state["session_id"], state["query"], gap_report
                    )
                except Exception as exc:
                    logger.warning(
                        "Compliance report persistence failed: %s",
                        exc,
                        extra={"session_id": state["session_id"]},
                    )

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Compliance Brain node executed",
                extra={
                    "node": "format_report",
                    "step": step_count,
                    "duration_ms": duration_ms,
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
                "Compliance Brain format_report failed: %s",
                exc,
                extra={"node": "format_report", "session_id": state["session_id"]},
            )
            fallback = state.get("draft_answer") or (
                "An internal error occurred while formatting the response."
            )
            return {
                "draft_answer": fallback,
                "error_flag": True,
                "step_count": step_count,
            }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _format_gaps(gap_report: Optional[ComplianceGapReport]) -> str:
    if not gap_report or not gap_report.gaps:
        return "(no gaps identified)"
    lines = []
    for g in gap_report.gaps:
        lines.append(
            f"- [{g.severity.value}] {g.regulation_clause} -> {g.procedure_gap}"
        )
    return "\n".join(lines)


def _format_gap_table(gap_report: ComplianceGapReport) -> str:
    lines = [
        "**Compliance Gap Report**",
        "",
        "| Regulation Clause | Procedure Gap | Severity |",
        "| --- | --- | --- |",
    ]
    for g in gap_report.gaps:
        lines.append(
            f"| {g.regulation_clause} | {g.procedure_gap} | {g.severity.value} |"
        )
    return "\n".join(lines)
