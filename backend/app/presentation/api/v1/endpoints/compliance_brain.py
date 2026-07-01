"""Compliance Brain Agent API (M11) — LangGraph-orchestrated compliance
gap-detection endpoint. Reuses the Knowledge Brain (M9) / Maintenance
Brain (M10) request/response shape, with the addition of the structured
gap report so a UI can render it as its own panel alongside the generated
evidence summary.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.domain.auth.models import User
from app.domain.compliance_brain.interfaces import IComplianceBrainAgent
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/brain/compliance", tags=["Compliance Brain"])
logger = logging.getLogger(__name__)

_DEFAULT_ROLE_SCOPE = "public"


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class ComplianceBrainChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1, max_length=128)


class CitationOut(BaseModel):
    chunk_id: str
    document_title: str
    page_number: Optional[int]
    chunk_text_excerpt: str
    score: float
    storage_key: Optional[str]


class ComplianceGapOut(BaseModel):
    regulation_clause: str
    procedure_gap: str
    severity: str


class ComplianceGapReportOut(BaseModel):
    regulation_query: str
    procedure_query: str
    gaps: List[ComplianceGapOut]
    has_critical_gaps: bool
    generated_at: str


class ComplianceBrainChatResponse(BaseModel):
    answer: str
    gap_report: Optional[ComplianceGapReportOut]
    citations: List[CitationOut]
    session_id: str
    error_flag: bool
    step_count: int


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------


def _get_agent() -> IComplianceBrainAgent:
    return container.get_compliance_brain_agent()


def _resolve_role_scope(user: User) -> str:
    return user.roles[0].name if user.roles else _DEFAULT_ROLE_SCOPE


# ------------------------------------------------------------------
# POST /api/v1/brain/compliance/chat
# ------------------------------------------------------------------


@router.post("/chat", response_model=ComplianceBrainChatResponse)
async def compliance_brain_chat(
    body: ComplianceBrainChatRequest,
    current_user: User = Depends(get_current_user),
    agent: IComplianceBrainAgent = Depends(_get_agent),
) -> ComplianceBrainChatResponse:
    role_scope = _resolve_role_scope(current_user)
    state = await agent.run(
        query=body.query,
        session_id=body.session_id,
        user_role=role_scope,
    )
    gap_report = state["gap_report"]
    return ComplianceBrainChatResponse(
        answer=state["draft_answer"],
        gap_report=(
            ComplianceGapReportOut(
                regulation_query=gap_report.regulation_query,
                procedure_query=gap_report.procedure_query,
                gaps=[
                    ComplianceGapOut(
                        regulation_clause=g.regulation_clause,
                        procedure_gap=g.procedure_gap,
                        severity=g.severity.value,
                    )
                    for g in gap_report.gaps
                ],
                has_critical_gaps=gap_report.has_critical_gaps,
                generated_at=gap_report.generated_at.isoformat(),
            )
            if gap_report is not None
            else None
        ),
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
