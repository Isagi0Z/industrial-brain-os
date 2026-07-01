"""Compliance Brain domain models (M11 — LangGraph agent, reuses the M9/M10
pattern with a Pydantic-enforced structured output for gap detection).

ComplianceGap/ComplianceGapReport are Pydantic models rather than plain
dataclasses (unlike WorkOrder/FailureRecord in M10) because the roadmap
explicitly requires the LLM's gap-detection output be validated against a
schema rather than trusted as free text (Engineering Bible §33 — explicit
data validation schemas for all inputs, applied here at the LLM-output
boundary). Pydantic is already a project dependency (pydantic-settings);
using it directly in the domain layer keeps a single representation
instead of a dataclass+pydantic pair with conversion boilerplate, and it
is a validation library, not a web/ORM framework — ADR-013 prohibits
FastAPI/SQLAlchemy in domain, not Pydantic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, TypedDict

from pydantic import BaseModel, Field

from app.domain.chat.models import Citation
from app.domain.search.models import SearchResult


class GapSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class ComplianceGap(BaseModel):
    regulation_clause: str
    procedure_gap: str
    severity: GapSeverity


class ComplianceGapReport(BaseModel):
    regulation_query: str
    procedure_query: str
    gaps: List[ComplianceGap] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_critical_gaps(self) -> bool:
        return any(g.severity == GapSeverity.CRITICAL for g in self.gaps)


class ComplianceAgentState(TypedDict):
    query: str
    session_id: str
    user_role: str
    regulation_chunks: List[SearchResult]
    procedure_chunks: List[SearchResult]
    gap_report: Optional[ComplianceGapReport]
    draft_answer: str
    citations: List[Citation]
    step_count: int
    error_flag: bool
