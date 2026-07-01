"""Knowledge Brain domain interfaces (ADR-013 — domain-agnostic, infra-free)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.knowledge_brain.models import AgentState


class IKnowledgeBrainAgent(ABC):
    @abstractmethod
    async def run(self, query: str, session_id: str, user_role: str) -> AgentState:
        """Execute the full agent graph for one query and return the final state."""
