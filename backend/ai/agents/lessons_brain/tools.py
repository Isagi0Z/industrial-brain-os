"""Lessons Learned Brain tool registry (M13).

Thin, independently-testable wrappers around domain interfaces, kept
separate from the LangGraph state machine definition
(app/application/lessons_brain/lessons_brain_agent.py), matching the
pattern established for the Knowledge (M9), Maintenance (M10), Compliance
(M11), and RCA (M12) brains.
"""

from __future__ import annotations

from typing import List

from app.domain.chat.interfaces import IModelGateway
from app.domain.maintenance_brain.interfaces import IFailureHistoryRepository
from app.domain.maintenance_brain.models import FailureRecord
from app.domain.search.interfaces import IEmbeddingService, IVectorRepository
from app.domain.search.models import SearchResult

LESSONS_LEARNED_COLLECTION = "lessons_learned"


def failure_pattern_match(
    failure_history_repo: IFailureHistoryRepository, asset_tag: str
) -> List[FailureRecord]:
    """(Equipment)-[:EXHIBITS]->(FailureMode) records for an asset — reuses
    M10's Neo4jFailureHistoryRepository (M6/M7 ontology, ADR-010) so
    incident ingestion links to real, already-known failure modes rather
    than guessing failure codes from free text."""
    if not asset_tag:
        return []
    return failure_history_repo.search_by_asset_tag(asset_tag)


def find_similar_lessons(
    embedding_service: IEmbeddingService,
    vector_repo: IVectorRepository,
    description: str,
    role_scope: str,
    limit: int,
) -> List[SearchResult]:
    """Semantic search of the `lessons_learned` Qdrant collection — used both
    at ingestion time (pattern detection: is this a recurring failure?) and
    by the /chat endpoint (answering questions about past incidents)."""
    if not description or not description.strip():
        return []
    vector = embedding_service.embed_one(description)
    return vector_repo.search(LESSONS_LEARNED_COLLECTION, vector, role_scope, limit)


async def generate_lesson_summary(
    model_gateway: IModelGateway,
    prompt: dict,
    asset_tag: str,
    incident_description: str,
    root_cause: str,
    corrective_actions: List[str],
    max_tokens: int,
) -> str:
    """Ask the LLM for a one-to-two sentence proactive-warning summary."""
    user_content = prompt.get("user_template", "{incident_description}").format(
        asset_tag=asset_tag,
        incident_description=incident_description,
        root_cause=root_cause,
        corrective_actions="; ".join(corrective_actions) or "(none recorded)",
    )
    messages = [
        {"role": "system", "content": prompt.get("system", "")},
        {"role": "user", "content": user_content},
    ]
    text, _, _ = await model_gateway.generate(messages, max_tokens)
    return text.strip()


async def synthesize_chat_answer(
    model_gateway: IModelGateway,
    prompt: dict,
    query: str,
    lessons_block: str,
    max_tokens: int,
) -> str:
    """Ask the LLM to answer a question grounded in retrieved past lessons."""
    user_content = prompt.get("user_template", "{query}").format(
        query=query,
        lessons_block=lessons_block or "(no matching historical lessons found)",
    )
    messages = [
        {"role": "system", "content": prompt.get("system", "")},
        {"role": "user", "content": user_content},
    ]
    text, _, _ = await model_gateway.generate(messages, max_tokens)
    return text.strip()
