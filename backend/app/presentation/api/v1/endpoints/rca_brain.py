"""RCA Brain Agent API (M12) — session-based, multi-turn Root Cause Analysis
endpoint. A request with no `session_id` starts a new 5-Whys session; a
request with a `session_id` and `answer` advances the human-in-the-loop
analysis. When the whys chain is deep enough, the response carries the
completed structured RCAReport (root cause, fishbone, recommended actions).
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.domain.auth.models import User
from app.domain.rca_brain.interfaces import IRCABrainAgent
from app.domain.rca_brain.models import RCASession
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/brain/rca", tags=["RCA Brain"])
logger = logging.getLogger(__name__)

_DEFAULT_ROLE_SCOPE = "public"


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class RCASessionRequest(BaseModel):
    # Start a new session: provide asset_tag + incident_description.
    # Advance an existing session: provide session_id + answer.
    session_id: Optional[str] = Field(default=None, max_length=128)
    asset_tag: Optional[str] = Field(default=None, max_length=128)
    incident_description: Optional[str] = Field(default=None, max_length=4000)
    answer: Optional[str] = Field(default=None, max_length=4000)


class WhyStepOut(BaseModel):
    question: str
    answer: Optional[str]


class RCAReportOut(BaseModel):
    problem_statement: str
    root_cause: str
    contributing_factors: List[str]
    recommended_actions: List[str]
    evidence_citations: List[str]
    fishbone: Dict[str, List[str]]
    generated_at: str


class RCASessionResponse(BaseModel):
    session_id: str
    asset_tag: str
    incident_description: str
    status: str
    whys: List[WhyStepOut]
    next_why: Optional[str]
    report: Optional[RCAReportOut]


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------


def _get_agent() -> IRCABrainAgent:
    return container.get_rca_brain_agent()


def _resolve_role_scope(user: User) -> str:
    return user.roles[0].name if user.roles else _DEFAULT_ROLE_SCOPE


def _to_response(session: RCASession) -> RCASessionResponse:
    # The "next why" awaiting a human answer is the last why with answer=None.
    next_why: Optional[str] = None
    if session.whys and session.whys[-1].answer is None:
        next_why = session.whys[-1].question

    report_out: Optional[RCAReportOut] = None
    if session.report is not None:
        report_out = RCAReportOut(
            problem_statement=session.report.problem_statement,
            root_cause=session.report.root_cause,
            contributing_factors=session.report.contributing_factors,
            recommended_actions=session.report.recommended_actions,
            evidence_citations=session.report.evidence_citations,
            fishbone=session.report.fishbone,
            generated_at=session.report.generated_at.isoformat(),
        )

    return RCASessionResponse(
        session_id=session.session_id,
        asset_tag=session.asset_tag,
        incident_description=session.incident_description,
        status=session.status.value,
        whys=[WhyStepOut(question=w.question, answer=w.answer) for w in session.whys],
        next_why=next_why,
        report=report_out,
    )


# ------------------------------------------------------------------
# POST /api/v1/brain/rca/session
# ------------------------------------------------------------------


@router.post("/session", response_model=RCASessionResponse)
async def rca_session(
    body: RCASessionRequest,
    current_user: User = Depends(get_current_user),
    agent: IRCABrainAgent = Depends(_get_agent),
) -> RCASessionResponse:
    role_scope = _resolve_role_scope(current_user)

    if body.session_id is None:
        # Start a new RCA session.
        if not body.asset_tag or not body.incident_description:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="asset_tag and incident_description are required to start a session",
            )
        new_id = str(uuid.uuid4())
        session = await agent.start_session(
            session_id=new_id,
            asset_tag=body.asset_tag,
            incident_description=body.incident_description,
            user_role=role_scope,
        )
        return _to_response(session)

    # Advance an existing session with the human's answer.
    if body.answer is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="answer is required to advance a session",
        )
    try:
        session = await agent.advance_session(
            session_id=body.session_id,
            human_answer=body.answer,
            user_role=role_scope,
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RCA session not found: {body.session_id}",
        )
    return _to_response(session)
