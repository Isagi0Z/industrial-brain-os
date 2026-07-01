"""RCA Brain domain models (M12 — LangGraph agent with human-in-the-loop
5-Whys and Fishbone (Ishikawa) workflows).

RCAReport is a Pydantic model (like M11's ComplianceGapReport) because the
LLM-generated root-cause analysis is parsed and validated against a schema
rather than trusted as free text (Engineering Bible §33). The rest of the
session state uses plain dataclasses / TypedDict, matching M9/M10/M11.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

from app.domain.chat.models import Citation
from app.domain.search.models import SearchResult


class RCAStatus(str, Enum):
    AWAITING_INPUT = "AWAITING_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FishboneCategory(str, Enum):
    """The six Ishikawa (6M) categories."""

    EQUIPMENT = "Equipment"
    METHOD = "Method"
    MATERIAL = "Material"
    MAN = "Man"
    ENVIRONMENT = "Environment"
    MEASUREMENT = "Measurement"


@dataclass
class WhyStep:
    """One rung of the 5-Whys ladder: a suggested 'why?' and the human's answer."""

    question: str
    answer: Optional[str] = None


class RCAReport(BaseModel):
    problem_statement: str
    root_cause: str
    contributing_factors: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    evidence_citations: List[str] = Field(default_factory=list)
    # Fishbone (Ishikawa) analysis: category name -> list of candidate causes.
    fishbone: Dict[str, List[str]] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RCASession:
    """Durable RCA session record (persisted to Postgres `rca_sessions` and,
    for the live working state, to a Redis-backed store enabling resume)."""

    session_id: str
    asset_tag: str
    incident_description: str
    status: RCAStatus
    whys: List[WhyStep] = field(default_factory=list)
    report: Optional[RCAReport] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RCAAgentState(TypedDict):
    """State threaded through the LangGraph 5-Whys graph for a single turn."""

    session_id: str
    asset_tag: str
    incident_description: str
    user_role: str
    whys: List[WhyStep]
    failure_patterns: List[str]
    incident_history: List[str]
    is_complete: bool
    next_why: str
    fishbone: Dict[str, List[str]]
    report: Optional[RCAReport]
    citations: List[Citation]
    evidence_chunks: List[SearchResult]
    step_count: int
    error_flag: bool
