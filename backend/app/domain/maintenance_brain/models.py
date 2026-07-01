"""Maintenance Brain domain models (M10 — LangGraph agent, reuses the M9
Knowledge Brain pattern with maintenance-specific state and tools).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, TypedDict

from app.domain.chat.models import Citation
from app.domain.search.models import SearchResult


@dataclass
class WorkOrder:
    wo_id: str
    asset_tag: str
    description: str
    status: str
    priority: str
    scheduled_date: Optional[date] = None
    completed_date: Optional[date] = None


@dataclass
class FailureRecord:
    """One (Equipment)-[:EXHIBITS]->(FailureMode) edge from Neo4j (M6/M7 ontology)."""

    failure_code: str
    description: str
    severity: Optional[str] = None
    typical_cause: Optional[str] = None


class MaintenanceAgentState(TypedDict):
    query: str
    session_id: str
    user_role: str
    asset_tag: Optional[str]
    work_orders: List[WorkOrder]
    failure_history: List[FailureRecord]
    retrieved_chunks: List[SearchResult]
    draft_answer: str
    citations: List[Citation]
    step_count: int
    error_flag: bool
