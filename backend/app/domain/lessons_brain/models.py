"""Lessons Learned Brain domain models (M13 — LangGraph agent for incident
ingestion + proactive warning knowledge, reusing the M9-M12 pattern).

Incident is the raw input from `POST /api/v1/incidents`. LessonLearned is
the durable record (Neo4j node + Qdrant embedding) derived from it.
LessonsAgentState is the single state object threaded through the
ingestion LangGraph (analyze_incident -> extract_patterns ->
link_to_ontology -> store_lesson -> generate_summary).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional, TypedDict


@dataclass
class Incident:
    """Raw incident report submitted to POST /api/v1/incidents."""

    asset_tag: str
    incident_date: date
    description: str
    root_cause: str
    corrective_actions: List[str] = field(default_factory=list)
    severity: str = "MEDIUM"
    role_scope: str = "public"


@dataclass
class LessonLearned:
    """Durable lesson record — Neo4j is the source of truth; the
    `description` text is embedded and upserted to the Qdrant
    `lessons_learned` collection (keyed by lesson_id) for semantic
    similarity search."""

    lesson_id: str
    asset_tag: str
    incident_date: date
    description: str
    root_cause: str
    corrective_actions: List[str]
    severity: str
    role_scope: str = "public"
    summary: str = ""
    equipment_linked: bool = False
    failure_modes_linked: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LessonLinkResult:
    """What the Neo4j write actually managed to link — reported back rather
    than assumed, since Equipment/FailureMode nodes may not yet exist in
    the graph for a given incident."""

    equipment_linked: bool
    failure_modes_linked: List[str]


class LessonsAgentState(TypedDict):
    """State threaded through the incident-ingestion LangGraph."""

    incident: Incident
    similar_lesson_summaries: List[str]
    failure_mode_candidates: List[str]
    lesson_id: str
    summary: str
    link_result: Optional[LessonLinkResult]
    lesson: Optional[LessonLearned]
    step_count: int
    error_flag: bool
