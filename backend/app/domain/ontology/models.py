from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


class OntologyViolationError(Exception):
    """Raised when a node or relationship violates the Industrial Ontology."""

    def __init__(self, node_type: str, violation: str) -> None:
        self.node_type = node_type
        self.violation = violation
        super().__init__(f"Ontology violation [{node_type}]: {violation}")


@dataclass
class NodeTypeSpec:
    name: str
    required_properties: List[str] = field(default_factory=list)
    optional_properties: List[str] = field(default_factory=list)


@dataclass
class RelationSpec:
    source_type: str
    relation_type: str
    target_type: str


@dataclass
class OntologySchema:
    version: str
    node_types: Dict[str, NodeTypeSpec]
    allowed_relations: List[RelationSpec]

    def get_node_type(self, name: str) -> NodeTypeSpec:
        if name not in self.node_types:
            raise OntologyViolationError(
                name, f"node type '{name}' is not defined in the ontology"
            )
        return self.node_types[name]
