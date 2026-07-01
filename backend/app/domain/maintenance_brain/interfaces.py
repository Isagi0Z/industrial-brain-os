"""Maintenance Brain domain interfaces (ADR-013 — domain-agnostic, infra-free)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.maintenance_brain.models import (
    FailureRecord,
    MaintenanceAgentState,
    WorkOrder,
)


class IWorkOrderRepository(ABC):
    @abstractmethod
    def find_by_wo_id(self, wo_id: str) -> Optional[WorkOrder]:
        """Look up a single work order by its id."""

    @abstractmethod
    def find_by_asset_tag(self, asset_tag: str) -> List[WorkOrder]:
        """Return all work orders (any status) for an asset."""

    @abstractmethod
    def find_open_by_asset_tag(self, asset_tag: str) -> List[WorkOrder]:
        """Return open work orders for an asset, sorted by scheduled_date ascending."""


class IFailureHistoryRepository(ABC):
    @abstractmethod
    def search_by_asset_tag(self, asset_tag: str) -> List[FailureRecord]:
        """Return (Equipment)-[:EXHIBITS]->(FailureMode) records for an asset."""


class IMaintenanceBrainAgent(ABC):
    @abstractmethod
    async def run(
        self, query: str, session_id: str, user_role: str
    ) -> MaintenanceAgentState:
        """Execute the full agent graph for one query and return the final state."""
