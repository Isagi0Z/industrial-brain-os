"""Incident ingestion API (M13) — feeds the Lessons Learned Brain's
LangGraph ingestion pipeline (analyze_incident -> extract_patterns ->
link_to_ontology -> store_lesson -> generate_summary). The resulting
LessonLearned node/embedding becomes searchable both by
`POST /api/v1/brain/lessons/chat` and by the Knowledge Brain's proactive
warning detector.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.application.lessons_brain.lessons_brain_agent import IncidentProcessingError
from app.domain.auth.models import User
from app.domain.lessons_brain.interfaces import ILessonsLearnedBrainAgent
from app.domain.lessons_brain.models import Incident
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/incidents", tags=["Lessons Learned Brain"])
logger = logging.getLogger(__name__)

_DEFAULT_ROLE_SCOPE = "public"


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class IncidentCreateRequest(BaseModel):
    asset_tag: str = Field(..., min_length=1, max_length=128)
    incident_date: date
    description: str = Field(..., min_length=1, max_length=4000)
    root_cause: str = Field(..., min_length=1, max_length=4000)
    corrective_actions: List[str] = Field(default_factory=list)
    severity: str = Field(default="MEDIUM", max_length=32)
    role_scope: Optional[str] = Field(default=None, max_length=64)


class IncidentResponse(BaseModel):
    lesson_id: str
    asset_tag: str
    incident_date: str
    description: str
    root_cause: str
    corrective_actions: List[str]
    severity: str
    summary: str
    equipment_linked: bool
    failure_modes_linked: List[str]
    created_at: str


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------


def _get_agent() -> ILessonsLearnedBrainAgent:
    return container.get_lessons_brain_agent()


def _resolve_role_scope(user: User) -> str:
    return user.roles[0].name if user.roles else _DEFAULT_ROLE_SCOPE


# ------------------------------------------------------------------
# POST /api/v1/incidents
# ------------------------------------------------------------------


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: IncidentCreateRequest,
    current_user: User = Depends(get_current_user),
    agent: ILessonsLearnedBrainAgent = Depends(_get_agent),
) -> IncidentResponse:
    role_scope = body.role_scope or _resolve_role_scope(current_user)
    incident = Incident(
        asset_tag=body.asset_tag,
        incident_date=body.incident_date,
        description=body.description,
        root_cause=body.root_cause,
        corrective_actions=body.corrective_actions,
        severity=body.severity,
        role_scope=role_scope,
    )
    try:
        lesson = await agent.ingest_incident(incident)
    except IncidentProcessingError as exc:
        logger.error("Incident ingestion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Incident processing failed; please retry.",
        )

    return IncidentResponse(
        lesson_id=lesson.lesson_id,
        asset_tag=lesson.asset_tag,
        incident_date=lesson.incident_date.isoformat(),
        description=lesson.description,
        root_cause=lesson.root_cause,
        corrective_actions=lesson.corrective_actions,
        severity=lesson.severity,
        summary=lesson.summary,
        equipment_linked=lesson.equipment_linked,
        failure_modes_linked=lesson.failure_modes_linked,
        created_at=lesson.created_at.isoformat(),
    )
