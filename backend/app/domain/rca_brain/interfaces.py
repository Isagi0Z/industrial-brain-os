"""RCA Brain domain interfaces (ADR-013 — domain-agnostic, infra-free)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.maintenance_brain.models import WorkOrder
from app.domain.rca_brain.models import RCASession


class IIncidentHistoryRepository(ABC):
    @abstractmethod
    def search_by_keywords(self, keywords: List[str], limit: int) -> List[WorkOrder]:
        """Return historical work orders whose description matches any keyword."""


class IRCASessionRepository(ABC):
    """Durable Postgres record of an RCA session (audit trail + final report)."""

    @abstractmethod
    def create(self, session: RCASession) -> None:
        """Insert a new session row (status AWAITING_INPUT)."""

    @abstractmethod
    def update(self, session: RCASession) -> None:
        """Update status and the (possibly complete) report JSON for a session."""

    @abstractmethod
    def get(self, session_id: str) -> Optional[RCASession]:
        """Load a session by id, or None if it does not exist."""


class IRCASessionStateStore(ABC):
    """Redis-backed live working-state store enabling resume after human input.

    Distinct from IRCASessionRepository: this holds the transient in-progress
    5-Whys state keyed by session_id so a subsequent HTTP request can resume
    the analysis without the service holding it in process memory (Engineering
    Bible §28 — stateless services)."""

    @abstractmethod
    def save(self, session: RCASession, ttl_seconds: int) -> None:
        """Persist the live session working state."""

    @abstractmethod
    def load(self, session_id: str) -> Optional[RCASession]:
        """Return the live session working state, or None on miss."""

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Remove the live working state (e.g. once the report is complete)."""


class IRCABrainAgent(ABC):
    @abstractmethod
    async def start_session(
        self,
        session_id: str,
        asset_tag: str,
        incident_description: str,
        user_role: str,
    ) -> RCASession:
        """Begin a new RCA session: gather evidence and suggest the first 'why'."""

    @abstractmethod
    async def advance_session(
        self, session_id: str, human_answer: str, user_role: str
    ) -> RCASession:
        """Record the human's answer and either suggest the next 'why' or,
        once deep enough, synthesize the root cause and generate the report."""
