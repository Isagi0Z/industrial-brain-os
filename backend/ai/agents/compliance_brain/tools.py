"""Compliance Brain tool registry (M11).

Thin, independently-testable wrappers around domain interfaces, kept
separate from the LangGraph state machine definition
(app/application/compliance_brain/compliance_brain_agent.py), matching the
pattern established for the Knowledge Brain (M9) and Maintenance Brain
(M10).
"""

from __future__ import annotations

import dataclasses
from typing import Any, List, Optional

from ai.agents.common.json_parse import (
    try_bracket_extract,
    try_direct,
    try_strip_fences,
)
from app.domain.chat.interfaces import IModelGateway
from app.domain.compliance_brain.models import (
    ComplianceGap,
    ComplianceGapReport,
    GapSeverity,
)
from app.domain.graphrag.interfaces import IGraphRAGEngine
from app.domain.graphrag.models import HybridSearchResult

# Document titles are matched case-insensitively against these keywords as a
# stand-in for a real document_category filter — the same limitation
# documented for M10's oem_manual_lookup applies here: no write path in
# this codebase populates DocumentClassification.category or indexes it
# into Qdrant, so "document_category = Regulation/SOP" cannot yet be
# enforced at the retrieval layer itself. See
# docs/verification/m11_verification.md.
_REGULATION_KEYWORDS = (
    "regulation",
    "osha",
    "cfr",
    "code of federal",
    "standard",
    "ansi",
    "iso ",
    "api rp",
    "nfpa",
    "epa",
)
_PROCEDURE_KEYWORDS = (
    "sop",
    "procedure",
    "work instruction",
    "standard operating procedure",
    "checklist",
    "instructions",
)


def _looks_like_regulation(document_title: str) -> bool:
    lowered = document_title.lower()
    return any(keyword in lowered for keyword in _REGULATION_KEYWORDS)


def _looks_like_procedure(document_title: str) -> bool:
    lowered = document_title.lower()
    return any(keyword in lowered for keyword in _PROCEDURE_KEYWORDS)


async def regulation_lookup(
    graphrag_engine: IGraphRAGEngine,
    query: str,
    role_scope: str,
    top_k: int,
) -> HybridSearchResult:
    """Full hybrid retrieval (M8) filtered to chunks that look like
    regulatory content, via a document-title keyword heuristic."""
    result = await graphrag_engine.retrieve(query, role_scope, top_k)
    filtered = [
        rc
        for rc in result.ranked_chunks
        if _looks_like_regulation(rc.result.document_title)
    ]
    return dataclasses.replace(result, ranked_chunks=filtered)


async def procedure_lookup(
    graphrag_engine: IGraphRAGEngine,
    query: str,
    role_scope: str,
    top_k: int,
) -> HybridSearchResult:
    """Full hybrid retrieval (M8) filtered to chunks that look like SOP /
    procedure content, via a document-title keyword heuristic."""
    result = await graphrag_engine.retrieve(query, role_scope, top_k)
    filtered = [
        rc
        for rc in result.ranked_chunks
        if _looks_like_procedure(rc.result.document_title)
    ]
    return dataclasses.replace(result, ranked_chunks=filtered)


async def compliance_gap_detector(
    model_gateway: IModelGateway,
    prompt: dict,
    regulation_text: str,
    procedure_text: str,
    regulation_query: str,
    procedure_query: str,
    max_tokens: int,
) -> ComplianceGapReport:
    """Sends regulation + procedure text to the LLM with a structured gap-
    detection prompt (ai/prompts/compliance_brain/gap_detection.yaml), then
    parses and validates the response into ComplianceGapReport — never
    trusted as free text (Engineering Bible §33)."""
    user_content = prompt.get(
        "user_template", "{regulation_text}\n{procedure_text}"
    ).format(
        regulation_text=regulation_text or "(no regulation text found)",
        procedure_text=procedure_text or "(no procedure text found)",
    )
    messages = [
        {"role": "system", "content": prompt.get("system", "")},
        {"role": "user", "content": user_content},
    ]
    text, _, _ = await model_gateway.generate(messages, max_tokens)
    gaps = _parse_gap_response(text)
    return ComplianceGapReport(
        regulation_query=regulation_query,
        procedure_query=procedure_query,
        gaps=gaps,
    )


# ---------------------------------------------------------------------------
# JSON parsing (same multi-strategy approach as M7's llm_relation_extractor)
# ---------------------------------------------------------------------------


def _parse_gap_response(text: str) -> List[ComplianceGap]:
    text = text.strip()
    raw = try_direct(text) or try_bracket_extract(text) or try_strip_fences(text)
    if raw is None or not isinstance(raw, list):
        return []

    gaps: List[ComplianceGap] = []
    for item in raw:
        gap = _item_to_gap(item)
        if gap is not None:
            gaps.append(gap)
    return gaps


def _item_to_gap(item: Any) -> Optional[ComplianceGap]:
    if not isinstance(item, dict):
        return None
    try:
        return ComplianceGap(
            regulation_clause=str(item["regulation_clause"]),
            procedure_gap=str(item["procedure_gap"]),
            severity=GapSeverity(str(item["severity"]).upper()),
        )
    except (KeyError, TypeError, ValueError):
        return None
