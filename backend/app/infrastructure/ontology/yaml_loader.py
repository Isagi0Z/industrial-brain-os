from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import yaml

try:
    import jsonschema

    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False

from app.domain.ontology.models import NodeTypeSpec, OntologySchema, RelationSpec

logger = logging.getLogger(__name__)

# Meta-schema: describes what a valid industrial_ontology.yaml must look like.
_ONTOLOGY_META_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["version", "node_types", "allowed_relations"],
    "additionalProperties": True,
    "properties": {
        "version": {"type": "string"},
        "description": {"type": "string"},
        "node_types": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {
                "type": "object",
                "required": ["required_properties"],
                "properties": {
                    "required_properties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "optional_properties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "allowed_relations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source", "relation", "target"],
                "properties": {
                    "source": {"type": "string"},
                    "relation": {"type": "string"},
                    "target": {"type": "string"},
                },
            },
        },
    },
}


def load_ontology(path: Path) -> OntologySchema:
    """Load and validate an ontology YAML file, returning an OntologySchema."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if _JSONSCHEMA_AVAILABLE:
        try:
            jsonschema.validate(instance=raw, schema=_ONTOLOGY_META_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise ValueError(
                f"Ontology YAML failed JSON Schema validation: {exc.message}"
            ) from exc
    else:
        logger.warning("jsonschema not installed — skipping ontology schema validation")

    node_types = {
        name: NodeTypeSpec(
            name=name,
            required_properties=list(spec.get("required_properties") or []),
            optional_properties=list(spec.get("optional_properties") or []),
        )
        for name, spec in raw["node_types"].items()
    }

    allowed_relations = [
        RelationSpec(
            source_type=r["source"],
            relation_type=r["relation"],
            target_type=r["target"],
        )
        for r in raw["allowed_relations"]
    ]

    schema = OntologySchema(
        version=str(raw["version"]),
        node_types=node_types,
        allowed_relations=allowed_relations,
    )

    logger.info(
        "Ontology loaded: version=%s node_types=%d relations=%d",
        schema.version,
        len(schema.node_types),
        len(schema.allowed_relations),
    )
    return schema
