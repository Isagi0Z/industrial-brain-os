from __future__ import annotations

import logging
from typing import Dict

from app.domain.ontology.interfaces import IOntologyValidator
from app.domain.ontology.models import OntologySchema, OntologyViolationError

logger = logging.getLogger(__name__)


class OntologyValidatorService(IOntologyValidator):
    """Pure domain service — validates nodes and relations against the ontology schema."""

    def __init__(self, schema: OntologySchema) -> None:
        self._schema = schema
        # Pre-build a set of allowed triples for O(1) lookup.
        self._allowed_triples: frozenset[tuple[str, str, str]] = frozenset(
            (r.source_type, r.relation_type, r.target_type)
            for r in schema.allowed_relations
        )

    def validate_node(self, node_type: str, properties: Dict[str, object]) -> None:
        spec = self._schema.get_node_type(node_type)
        missing = [p for p in spec.required_properties if p not in properties]
        if missing:
            raise OntologyViolationError(
                node_type,
                f"missing required properties: {missing}",
            )
        logger.debug("Ontology node validation passed: %s", node_type)

    def validate_relation(
        self, source_type: str, relation_type: str, target_type: str
    ) -> None:
        triple = (source_type, relation_type, target_type)
        if triple not in self._allowed_triples:
            raise OntologyViolationError(
                f"{source_type}-[{relation_type}]->{target_type}",
                "relationship type not defined in ontology",
            )
        logger.debug(
            "Ontology relation validation passed: %s -[%s]-> %s",
            source_type,
            relation_type,
            target_type,
        )

    def get_schema(self) -> OntologySchema:
        return self._schema
