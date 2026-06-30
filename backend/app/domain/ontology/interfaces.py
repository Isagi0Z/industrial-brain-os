from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from app.domain.ontology.models import OntologySchema


class IOntologyValidator(ABC):
    @abstractmethod
    def validate_node(self, node_type: str, properties: Dict[str, object]) -> None:
        """Raise OntologyViolationError if node_type is unknown or required props are missing."""

    @abstractmethod
    def validate_relation(
        self, source_type: str, relation_type: str, target_type: str
    ) -> None:
        """Raise OntologyViolationError if the source→relation→target triple is not allowed."""

    @abstractmethod
    def get_schema(self) -> OntologySchema:
        """Return the loaded ontology schema."""
