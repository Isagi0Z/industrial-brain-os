"""RCA Brain tool registry (M12).

Thin, independently-testable wrappers around domain interfaces, kept
separate from the LangGraph state machine definition
(app/application/rca_brain/rca_brain_agent.py), matching the pattern
established for the Knowledge (M9), Maintenance (M10), and Compliance (M11)
brains.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from app.domain.chat.interfaces import IModelGateway
from app.domain.graphrag.interfaces import IGraphRAGEngine
from app.domain.maintenance_brain.interfaces import IFailureHistoryRepository
from app.domain.maintenance_brain.models import FailureRecord, WorkOrder
from app.domain.rca_brain.interfaces import IIncidentHistoryRepository
from app.domain.rca_brain.models import FishboneCategory

_STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "has",
        "have",
        "had",
        "this",
        "that",
        "it",
        "its",
        "failure",
        "failed",
        "issue",
        "problem",
    }
)


def extract_keywords(text: str, limit: int = 6) -> List[str]:
    """Pull the salient terms from an incident description for incident-history
    matching (drops stop words and short tokens; preserves industrial tags)."""
    tokens = re.findall(r"[A-Za-z0-9\-]+", text.lower())
    seen: set = set()
    keywords: List[str] = []
    for t in tokens:
        if len(t) <= 2 or t in _STOP_WORDS or t in seen:
            continue
        seen.add(t)
        keywords.append(t)
        if len(keywords) >= limit:
            break
    return keywords


def failure_pattern_search(
    failure_history_repo: IFailureHistoryRepository, asset_tag: str
) -> List[FailureRecord]:
    """(Equipment)-[:EXHIBITS]->(FailureMode) records for an asset (reuses
    M10's Neo4jFailureHistoryRepository — M6/M7 ontology, ADR-010)."""
    if not asset_tag:
        return []
    return failure_history_repo.search_by_asset_tag(asset_tag)


def incident_history_search(
    incident_repo: IIncidentHistoryRepository, incident_description: str, limit: int
) -> List[WorkOrder]:
    """Historical work orders whose description resembles the incident."""
    keywords = extract_keywords(incident_description)
    if not keywords:
        return []
    return incident_repo.search_by_keywords(keywords, limit)


async def suggest_next_why(
    model_gateway: IModelGateway,
    prompt: dict,
    incident_description: str,
    asset_tag: str,
    whys_block: str,
    failure_patterns: str,
    incident_history: str,
    max_tokens: int,
) -> str:
    """Ask the LLM for the next 'why?' in the 5-Whys chain."""
    user_content = prompt.get("user_template", "{incident_description}").format(
        incident_description=incident_description,
        asset_tag=asset_tag,
        failure_patterns=failure_patterns or "(none found)",
        incident_history=incident_history or "(none found)",
        whys_block=whys_block or "(this is the first why)",
    )
    messages = [
        {"role": "system", "content": prompt.get("system", "")},
        {"role": "user", "content": user_content},
    ]
    text, _, _ = await model_gateway.generate(messages, max_tokens)
    return text.strip()


async def fishbone_analysis(
    graphrag_engine: IGraphRAGEngine,
    model_gateway: IModelGateway,
    prompt: dict,
    incident_description: str,
    asset_tag: str,
    role_scope: str,
    top_k: int,
    max_tokens: int,
) -> Dict[str, List[str]]:
    """Run one branch per Ishikawa (6M) category CONCURRENTLY: each branch
    retrieves category-relevant document chunks (GraphRAG, M8) and asks the
    LLM to list candidate causes for that category."""

    async def _branch(category: FishboneCategory) -> tuple:
        try:
            hybrid = await graphrag_engine.retrieve(
                f"{incident_description} {category.value}", role_scope, top_k
            )
            evidence = (
                "\n".join(rc.result.text for rc in hybrid.ranked_chunks)
                or "(no evidence)"
            )
            user_content = prompt.get("user_template", "{category}").format(
                incident_description=incident_description,
                asset_tag=asset_tag,
                category=category.value,
                evidence_block=evidence,
            )
            messages = [
                {"role": "system", "content": prompt.get("system", "")},
                {"role": "user", "content": user_content},
            ]
            text, _, _ = await model_gateway.generate(messages, max_tokens)
            causes = _parse_string_array(text)
            return category.value, causes
        except Exception:
            return category.value, []

    results = await asyncio.gather(*[_branch(c) for c in FishboneCategory])
    return {name: causes for name, causes in results}


# ---------------------------------------------------------------------------
# JSON parsing (same multi-strategy approach as M7 / M11)
# ---------------------------------------------------------------------------


def parse_report_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract a single JSON OBJECT (the RCA report) from an LLM response."""
    text = text.strip()
    raw = _try_direct(text) or _try_brace_extract(text) or _try_strip_fences(text)
    if isinstance(raw, dict):
        return raw
    return None


def _parse_string_array(text: str) -> List[str]:
    text = text.strip()
    raw = _try_direct(text) or _try_bracket_extract(text) or _try_strip_fences(text)
    if isinstance(raw, list):
        return [str(x) for x in raw if isinstance(x, (str, int, float))]
    return []


def _try_direct(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _try_bracket_extract(text: str) -> Optional[Any]:
    return _balanced_extract(text, "[", "]")


def _try_brace_extract(text: str) -> Optional[Any]:
    return _balanced_extract(text, "{", "}")


def _balanced_extract(text: str, open_ch: str, close_ch: str) -> Optional[Any]:
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _try_strip_fences(text: str) -> Optional[Any]:
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
