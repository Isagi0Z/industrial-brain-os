"""RCABrainAgent — LangGraph state machine for the RCA sub-brain (M12,
ADR-007). Reuses the Knowledge (M9) / Maintenance (M10) / Compliance (M11)
pattern: return-value-based step counting, per-node try/except with
error_flag fallback, and conditional edges that skip on error.

Two workflows, one compiled graph:

    define_problem --> decide
        decide (not complete) --> suggest_why --> [interrupt_before] human_confirm --> END
        decide (complete)     --> identify_root_cause --> generate_report --> END

Human-in-the-loop 5-Whys spans multiple HTTP requests. Rather than relying
on LangGraph's in-process checkpointer for cross-request durability (the
official langgraph-checkpoint-redis needs the RedisJSON module, which the
plain redis:7.2-alpine deployment lacks — and an in-process MemorySaver
would violate Engineering Bible §28's stateless-service rule), the durable
session working-state lives in a Redis-backed store (IRCASessionStateStore)
and the audit record + final report in Postgres (IRCASessionRepository).
The graph is still compiled with `interrupt_before=["human_confirm"]` and a
MemorySaver so the 5-Whys pause point is a real LangGraph interrupt: each
`start_session` / `advance_session` call invokes the graph, which runs up
to and pauses before human_confirm (returning the suggested why), or runs
the root-cause/report path to completion.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.application.agents.base import (
    BaseBrainAgent,
    CITATION_PATTERN as _CITATION_PATTERN,
    StepLimitExceededError,
    load_prompt,
)
from app.domain.chat.interfaces import IModelGateway
from app.domain.chat.models import Citation
from app.domain.graphrag.interfaces import IGraphRAGEngine
from app.domain.maintenance_brain.interfaces import IFailureHistoryRepository
from app.domain.rca_brain.interfaces import (
    IIncidentHistoryRepository,
    IRCABrainAgent,
    IRCASessionRepository,
    IRCASessionStateStore,
)
from app.domain.rca_brain.models import (
    RCAAgentState,
    RCAReport,
    RCASession,
    RCAStatus,
    WhyStep,
)
from app.domain.search.models import SearchResult

from ai.agents.rca_brain.tools import (
    failure_pattern_search,
    fishbone_analysis,
    incident_history_search,
    parse_report_object,
    suggest_next_why,
)

logger = logging.getLogger(__name__)

MAX_STEPS = 10


class RCABrainAgent(BaseBrainAgent, IRCABrainAgent):
    def __init__(
        self,
        graphrag_engine: IGraphRAGEngine,
        model_gateway: IModelGateway,
        failure_history_repo: IFailureHistoryRepository,
        incident_repo: IIncidentHistoryRepository,
        session_repo: IRCASessionRepository,
        state_store: IRCASessionStateStore,
        suggest_why_prompt_path: Path,
        generate_report_prompt_path: Path,
        fishbone_prompt_path: Path,
        max_steps: int = MAX_STEPS,
        max_whys: int = 5,
        top_k: int = 5,
        incident_history_limit: int = 5,
        max_tokens: int = 2048,
        session_ttl_seconds: int = 3600,
    ) -> None:
        self._graphrag = graphrag_engine
        self._gateway = model_gateway
        self._failure_history_repo = failure_history_repo
        self._incident_repo = incident_repo
        self._session_repo = session_repo
        self._state_store = state_store
        self._suggest_prompt = load_prompt(suggest_why_prompt_path)
        self._report_prompt = load_prompt(generate_report_prompt_path)
        self._fishbone_prompt = load_prompt(fishbone_prompt_path)
        self._max_steps = max_steps
        self._max_whys = max_whys
        self._top_k = top_k
        self._incident_history_limit = incident_history_limit
        self._max_tokens = max_tokens
        self._session_ttl = session_ttl_seconds
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def start_session(
        self,
        session_id: str,
        asset_tag: str,
        incident_description: str,
        user_role: str,
    ) -> RCASession:
        session = RCASession(
            session_id=session_id,
            asset_tag=asset_tag,
            incident_description=incident_description,
            status=RCAStatus.AWAITING_INPUT,
            whys=[],
        )
        self._session_repo.create(session)

        state = await self._run_turn(session, user_role, is_complete=False)
        if state["error_flag"]:
            session.status = RCAStatus.FAILED
        else:
            session.whys.append(WhyStep(question=state["next_why"], answer=None))

        self._state_store.save(session, self._session_ttl)
        self._session_repo.update(session)
        return session

    async def advance_session(
        self, session_id: str, human_answer: str, user_role: str
    ) -> RCASession:
        session = self._state_store.load(session_id)
        if session is None:
            # No live working state to resume (expired, or never started in
            # this Redis). Fall back to the Postgres audit record so the
            # caller gets a coherent status rather than a crash.
            persisted = self._session_repo.get(session_id)
            if persisted is None:
                raise KeyError(f"RCA session not found: {session_id}")
            persisted.status = RCAStatus.FAILED
            return persisted

        if session.status == RCAStatus.COMPLETED:
            return session

        # Record the human's answer against the most recent open 'why'.
        if session.whys and session.whys[-1].answer is None:
            session.whys[-1].answer = human_answer

        answered = [w for w in session.whys if w.answer is not None]
        is_complete = len(answered) >= self._max_whys

        state = await self._run_turn(session, user_role, is_complete=is_complete)

        if state["error_flag"]:
            session.status = RCAStatus.FAILED
        elif is_complete:
            session.report = state["report"]
            session.status = RCAStatus.COMPLETED
        else:
            session.whys.append(WhyStep(question=state["next_why"], answer=None))
            session.status = RCAStatus.AWAITING_INPUT

        self._session_repo.update(session)
        if session.status == RCAStatus.COMPLETED:
            self._state_store.delete(session_id)
        else:
            self._state_store.save(session, self._session_ttl)
        return session

    async def _run_turn(
        self, session: RCASession, user_role: str, is_complete: bool
    ) -> RCAAgentState:
        initial: RCAAgentState = {
            "session_id": session.session_id,
            "asset_tag": session.asset_tag,
            "incident_description": session.incident_description,
            "user_role": user_role,
            "whys": session.whys,
            "failure_patterns": [],
            "incident_history": [],
            "is_complete": is_complete,
            "next_why": "",
            "fishbone": {},
            "report": None,
            "citations": [],
            "evidence_chunks": [],
            "step_count": 0,
            "error_flag": False,
        }
        # Fresh thread per turn: cross-request continuity is provided by the
        # durable session state, not the in-process checkpointer.
        cfg = {
            "configurable": {"thread_id": f"{session.session_id}:{len(session.whys)}"}
        }
        try:
            await self._graph.ainvoke(initial, cfg)
            snapshot = await self._graph.aget_state(cfg)
            return snapshot.values  # type: ignore[return-value]
        except StepLimitExceededError as exc:
            logger.error("RCA Brain step limit exceeded: %s", exc)
            failed = dict(initial)
            failed["error_flag"] = True
            return failed  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(RCAAgentState)
        graph.add_node("define_problem", self._define_problem)
        graph.add_node("suggest_why", self._suggest_why)
        graph.add_node("human_confirm", self._human_confirm)
        graph.add_node("identify_root_cause", self._identify_root_cause)
        graph.add_node("generate_report", self._generate_report)

        graph.set_entry_point("define_problem")
        graph.add_conditional_edges(
            "define_problem",
            self._route_after_define,
            {
                "suggest": "suggest_why",
                "report": "identify_root_cause",
                "error": END,
            },
        )
        graph.add_edge("suggest_why", "human_confirm")
        graph.add_edge("human_confirm", END)
        graph.add_conditional_edges(
            "identify_root_cause",
            self._error_or(default="generate_report"),
            {"error": END, "generate_report": "generate_report"},
        )
        graph.add_edge("generate_report", END)
        return graph.compile(
            checkpointer=MemorySaver(), interrupt_before=["human_confirm"]
        )

    def _route_after_define(self, state: RCAAgentState) -> str:
        if state["error_flag"]:
            return "error"
        return "report" if state["is_complete"] else "suggest"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _define_problem(self, state: RCAAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            failures = failure_pattern_search(
                self._failure_history_repo, state["asset_tag"]
            )
            incidents = incident_history_search(
                self._incident_repo,
                state["incident_description"],
                self._incident_history_limit,
            )
            failure_lines = [
                f"{f.failure_code}: {f.description}"
                + (f" (severity={f.severity})" if f.severity else "")
                for f in failures
            ]
            incident_lines = [
                f"{wo.wo_id}: {wo.description} (status={wo.status})" for wo in incidents
            ]
            logger.info(
                "RCA Brain node executed",
                extra={
                    "node": "define_problem",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "asset_tag": state["asset_tag"],
                    "failure_patterns_found": len(failure_lines),
                    "incidents_found": len(incident_lines),
                    "session_id": state["session_id"],
                },
            )
            return {
                "failure_patterns": failure_lines,
                "incident_history": incident_lines,
                "step_count": step_count,
            }
        except Exception as exc:
            logger.error(
                "RCA Brain define_problem failed: %s",
                exc,
                extra={"node": "define_problem", "session_id": state["session_id"]},
            )
            return {"error_flag": True, "step_count": step_count}

    async def _suggest_why(self, state: RCAAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            next_why = await suggest_next_why(
                self._gateway,
                self._suggest_prompt,
                state["incident_description"],
                state["asset_tag"],
                _format_whys(state["whys"]),
                "\n".join(state["failure_patterns"]),
                "\n".join(state["incident_history"]),
                self._max_tokens,
            )
            logger.info(
                "RCA Brain node executed",
                extra={
                    "node": "suggest_why",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "why_index": len(state["whys"]) + 1,
                    "session_id": state["session_id"],
                },
            )
            return {"next_why": next_why, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "RCA Brain suggest_why failed: %s",
                exc,
                extra={"node": "suggest_why", "session_id": state["session_id"]},
            )
            return {"error_flag": True, "step_count": step_count}

    def _human_confirm(self, state: RCAAgentState) -> Dict[str, Any]:
        # Human-in-the-loop boundary. `interrupt_before` pauses the graph
        # before this node, so its body only runs on an (unused) resume path;
        # it is intentionally a no-op that just advances the step counter.
        return {"step_count": state["step_count"] + 1}

    async def _identify_root_cause(self, state: RCAAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            hybrid = await self._graphrag.retrieve(
                f"{state['incident_description']} root cause {state['asset_tag']}",
                state["user_role"],
                self._top_k,
            )
            evidence_chunks: List[SearchResult] = [
                rc.result for rc in hybrid.ranked_chunks
            ]
            fishbone = await fishbone_analysis(
                self._graphrag,
                self._gateway,
                self._fishbone_prompt,
                state["incident_description"],
                state["asset_tag"],
                state["user_role"],
                self._top_k,
                self._max_tokens,
            )
            logger.info(
                "RCA Brain node executed",
                extra={
                    "node": "identify_root_cause",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "evidence_chunks": len(evidence_chunks),
                    "fishbone_categories": len(fishbone),
                    "session_id": state["session_id"],
                },
            )
            return {
                "evidence_chunks": evidence_chunks,
                "fishbone": fishbone,
                "step_count": step_count,
            }
        except Exception as exc:
            logger.error(
                "RCA Brain identify_root_cause failed: %s",
                exc,
                extra={
                    "node": "identify_root_cause",
                    "session_id": state["session_id"],
                },
            )
            return {"error_flag": True, "step_count": step_count}

    async def _generate_report(self, state: RCAAgentState) -> Dict[str, Any]:
        t0 = time.monotonic()
        step_count = self._check_step_limit(state)
        try:
            evidence_chunks = state["evidence_chunks"]
            by_chunk_id = {c.chunk_id: c for c in evidence_chunks}
            failure_codes = {
                line.split(":", 1)[0] for line in state["failure_patterns"]
            }

            evidence_block = (
                "\n\n".join(
                    f"[chunk_id: {c.chunk_id}] {c.text}" for c in evidence_chunks
                )
                or "(no evidence chunks retrieved)"
            )

            user_content = self._report_prompt.get(
                "user_template", "{whys_block}"
            ).format(
                incident_description=state["incident_description"],
                asset_tag=state["asset_tag"],
                whys_block=_format_whys(state["whys"]),
                failure_patterns="\n".join(state["failure_patterns"]) or "(none)",
                evidence_block=evidence_block,
            )
            messages = [
                {"role": "system", "content": self._report_prompt.get("system", "")},
                {"role": "user", "content": user_content},
            ]
            text, _, _ = await self._gateway.generate(messages, self._max_tokens)
            obj = parse_report_object(text)

            fishbone = state["fishbone"]

            if obj is None:
                report = RCAReport(
                    problem_statement=state["incident_description"],
                    root_cause="Root cause could not be determined from the available evidence.",
                    fishbone=fishbone,
                )
                citations: List[Citation] = []
            else:
                validated_citations, citation_objs = _validate_citations(
                    obj.get("evidence_citations", []),
                    by_chunk_id,
                    failure_codes,
                )
                report = RCAReport(
                    problem_statement=state["incident_description"],
                    root_cause=str(obj.get("root_cause", "")),
                    contributing_factors=[
                        str(x) for x in obj.get("contributing_factors", [])
                    ],
                    recommended_actions=[
                        str(x) for x in obj.get("recommended_actions", [])
                    ],
                    evidence_citations=validated_citations,
                    fishbone=fishbone,
                )
                citations = citation_objs

            logger.info(
                "RCA Brain node executed",
                extra={
                    "node": "generate_report",
                    "step": step_count,
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                    "contributing_factors": len(report.contributing_factors),
                    "recommended_actions": len(report.recommended_actions),
                    "session_id": state["session_id"],
                },
            )
            return {"report": report, "citations": citations, "step_count": step_count}
        except Exception as exc:
            logger.error(
                "RCA Brain generate_report failed: %s",
                exc,
                extra={"node": "generate_report", "session_id": state["session_id"]},
            )
            return {"error_flag": True, "step_count": step_count}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _format_whys(whys: List[WhyStep]) -> str:
    if not whys:
        return ""
    lines = []
    for i, w in enumerate(whys, start=1):
        answer = w.answer if w.answer is not None else "(awaiting answer)"
        lines.append(f"Why {i}: {w.question}\n  Answer: {answer}")
    return "\n".join(lines)


def _validate_citations(
    raw_citations: List[Any],
    by_chunk_id: Dict[str, Any],
    failure_codes: set,
) -> tuple:
    """Keep only citations that reference a real evidence chunk_id or a known
    failure code; drop hallucinated references. Returns (validated_strings,
    Citation objects for chunk-backed ones)."""
    validated: List[str] = []
    citation_objs: List[Citation] = []
    seen: set = set()
    for raw in raw_citations:
        s = str(raw)
        match = _CITATION_PATTERN.search(s)
        if match:
            chunk_id = match.group(1)
            if chunk_id in by_chunk_id and chunk_id not in seen:
                seen.add(chunk_id)
                sr = by_chunk_id[chunk_id]
                validated.append(s)
                citation_objs.append(
                    Citation(
                        chunk_id=sr.chunk_id,
                        document_title=sr.document_title,
                        page_number=sr.page_number,
                        chunk_text_excerpt=sr.text[:200],
                        score=round(sr.score, 4),
                        storage_key=sr.document_id,
                    )
                )
        elif s in failure_codes and s not in seen:
            seen.add(s)
            validated.append(s)
    return validated, citation_objs
