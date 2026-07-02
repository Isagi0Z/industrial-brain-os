"""Lessons Learned Brain domain interfaces (ADR-013 — domain-agnostic,
infra-free)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.chat.models import ProactiveWarning
from app.domain.lessons_brain.models import LessonLearned, LessonLinkResult


class ILessonRepository(ABC):
    """Neo4j-backed persistence for LessonLearned nodes and their
    RELATED_TO(Equipment) / REFERENCES(FailureMode) edges (M6 ontology)."""

    @abstractmethod
    def create(
        self,
        lesson: LessonLearned,
        candidate_failure_codes: List[str],
    ) -> LessonLinkResult:
        """MERGE the LessonLearned node; attempt RELATED_TO(Equipment) (by
        lesson.asset_tag) and REFERENCES(FailureMode) (one per candidate
        code) edges against already-existing nodes, and report which of
        those attempts actually matched an existing node."""

    @abstractmethod
    def update_summary(self, lesson_id: str, summary: str) -> None:
        """Patch the `summary` property once the LLM has generated it."""

    @abstractmethod
    def get(self, lesson_id: str) -> Optional[LessonLearned]:
        """Load the canonical lesson record by id, or None if not found."""


class IProactiveWarningDetector(ABC):
    @abstractmethod
    def detect(self, query: str, role_scope: str) -> Optional[ProactiveWarning]:
        """Return a ProactiveWarning if `query` is similar (> threshold) to a
        previously ingested lesson, else None."""


class ILessonsLearnedBrainAgent(ABC):
    @abstractmethod
    async def ingest_incident(self, incident) -> LessonLearned:
        """Run the full ingestion graph and return the stored lesson."""

    @abstractmethod
    async def chat(self, query: str, session_id: str, user_role: str) -> dict:
        """Answer a question about historical lessons/incidents."""
