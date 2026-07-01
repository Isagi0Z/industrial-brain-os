"""Maintenance Brain Agent API (M10) — LangGraph-orchestrated maintenance
Q&A endpoint. Reuses the Knowledge Brain (M9) request/response shape, with
the addition of the extracted asset_tag, open work orders, and failure
history so a UI can render structured maintenance context alongside the
generated guidance text.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.domain.auth.models import User
from app.domain.maintenance_brain.interfaces import IMaintenanceBrainAgent
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/brain/maintenance", tags=["Maintenance Brain"])
logger = logging.getLogger(__name__)

_DEFAULT_ROLE_SCOPE = "public"


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class MaintenanceBrainChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1, max_length=128)


class CitationOut(BaseModel):
    chunk_id: str
    document_title: str
    page_number: Optional[int]
    chunk_text_excerpt: str
    score: float
    storage_key: Optional[str]


class WorkOrderOut(BaseModel):
    wo_id: str
    asset_tag: str
    description: str
    status: str
    priority: str
    scheduled_date: Optional[str]
    completed_date: Optional[str]


class FailureRecordOut(BaseModel):
    failure_code: str
    description: str
    severity: Optional[str]
    typical_cause: Optional[str]


class MaintenanceBrainChatResponse(BaseModel):
    answer: str
    asset_tag: Optional[str]
    work_orders: List[WorkOrderOut]
    failure_history: List[FailureRecordOut]
    citations: List[CitationOut]
    session_id: str
    error_flag: bool
    step_count: int


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------


def _get_agent() -> IMaintenanceBrainAgent:
    return container.get_maintenance_brain_agent()


def _resolve_role_scope(user: User) -> str:
    return user.roles[0].name if user.roles else _DEFAULT_ROLE_SCOPE


# ------------------------------------------------------------------
# POST /api/v1/brain/maintenance/chat
# ------------------------------------------------------------------


@router.post("/chat", response_model=MaintenanceBrainChatResponse)
async def maintenance_brain_chat(
    body: MaintenanceBrainChatRequest,
    current_user: User = Depends(get_current_user),
    agent: IMaintenanceBrainAgent = Depends(_get_agent),
) -> MaintenanceBrainChatResponse:
    role_scope = _resolve_role_scope(current_user)
    state = await agent.run(
        query=body.query,
        session_id=body.session_id,
        user_role=role_scope,
    )
    return MaintenanceBrainChatResponse(
        answer=state["draft_answer"],
        asset_tag=state["asset_tag"],
        work_orders=[
            WorkOrderOut(
                wo_id=wo.wo_id,
                asset_tag=wo.asset_tag,
                description=wo.description,
                status=wo.status,
                priority=wo.priority,
                scheduled_date=(
                    wo.scheduled_date.isoformat() if wo.scheduled_date else None
                ),
                completed_date=(
                    wo.completed_date.isoformat() if wo.completed_date else None
                ),
            )
            for wo in state["work_orders"]
        ],
        failure_history=[
            FailureRecordOut(
                failure_code=f.failure_code,
                description=f.description,
                severity=f.severity,
                typical_cause=f.typical_cause,
            )
            for f in state["failure_history"]
        ],
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
