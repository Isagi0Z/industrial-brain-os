"""Compliance Brain domain interfaces (ADR-013 — domain-agnostic, infra-free)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.compliance_brain.models import ComplianceAgentState, ComplianceGapReport


class IComplianceReportRepository(ABC):
    @abstractmethod
    def save(self, session_id: str, query: str, report: ComplianceGapReport) -> str:
        """Persist a gap report for the audit trail. Returns the new report id."""


class IComplianceBrainAgent(ABC):
    @abstractmethod
    async def run(
        self, query: str, session_id: str, user_role: str
    ) -> ComplianceAgentState:
        """Execute the full agent graph for one query and return the final state."""
