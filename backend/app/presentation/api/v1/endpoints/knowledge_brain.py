"""Knowledge Brain Agent API (M9) — LangGraph-orchestrated Q&A endpoint.

Distinct from /api/v1/chat (M5/M8): this endpoint routes through the full
KnowledgeBrainAgent state machine (route_query -> retrieve_context ->
synthesize_answer -> validate_citations -> format_response) rather than the
simpler direct GraphRAG-then-generate flow used by ChatUseCase.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.domain.auth.models import User
from app.domain.knowledge_brain.interfaces import IKnowledgeBrainAgent
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/brain/knowledge", tags=["Knowledge Brain"])
logger = logging.getLogger(__name__)

_DEFAULT_ROLE_SCOPE = "public"


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class KnowledgeBrainChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1, max_length=128)


class CitationOut(BaseModel):
    chunk_id: str
    document_title: str
    page_number: Optional[int]
    chunk_text_excerpt: str
    score: float
    storage_key: Optional[str]


class KnowledgeBrainChatResponse(BaseModel):
    answer: str
    citations: List[CitationOut]
    session_id: str
    error_flag: bool
    step_count: int


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------


def _get_agent() -> IKnowledgeBrainAgent:
    return container.get_knowledge_brain_agent()


def _resolve_role_scope(user: User) -> str:
    return user.roles[0].name if user.roles else _DEFAULT_ROLE_SCOPE


# ------------------------------------------------------------------
# POST /api/v1/brain/knowledge/chat
# ------------------------------------------------------------------


@router.post("/chat", response_model=KnowledgeBrainChatResponse)
async def knowledge_brain_chat(
    body: KnowledgeBrainChatRequest,
    current_user: User = Depends(get_current_user),
    agent: IKnowledgeBrainAgent = Depends(_get_agent),
) -> KnowledgeBrainChatResponse:
    role_scope = _resolve_role_scope(current_user)
    state = await agent.run(
        query=body.query,
        session_id=body.session_id,
        user_role=role_scope,
    )
    return KnowledgeBrainChatResponse(
        answer=state["draft_answer"],
        citations=[
            CitationOut(
                chunk_id=c.chunk_id,
                document_title=c.document_title,
                page_number=c.page_number,
                chunk_text_excerpt=c.chunk_text_excerpt,
                score=c.score,
                storage_key=c.storage_key,
            )
            for c in state["citations"]
        ],
        session_id=state["session_id"],
        error_flag=state["error_flag"],
        step_count=state["step_count"],
    )
