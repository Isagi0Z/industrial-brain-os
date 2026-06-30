"""Unit tests for M6 — Industrial Ontology Schema & Validator.

No external services (Neo4j, file I/O beyond tmp_path) are used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.ontology.models import (
    NodeTypeSpec,
    OntologySchema,
    OntologyViolationError,
    RelationSpec,
)
from app.domain.ontology.validator import OntologyValidatorService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_schema() -> OntologySchema:
    return OntologySchema(
        version="1.0",
        node_types={
            "Equipment": NodeTypeSpec(
                name="Equipment",
                required_properties=["tag_number", "equipment_class"],
                optional_properties=["manufacturer", "status"],
            ),
            "Sensor": NodeTypeSpec(
                name="Sensor",
                required_properties=["tag_number", "measurement_type"],
                optional_properties=["unit"],
            ),
            "FailureMode": NodeTypeSpec(
                name="FailureMode",
                required_properties=["failure_code", "description"],
                optional_properties=["severity"],
            ),
            "Document": NodeTypeSpec(
                name="Document",
                required_properties=["source_id", "title", "document_type"],
                optional_properties=[],
            ),
        },
        allowed_relations=[
            RelationSpec("Sensor", "MONITORS", "Equipment"),
            RelationSpec("Equipment", "EXHIBITS", "FailureMode"),
            RelationSpec("Document", "REFERENCES", "Equipment"),
        ],
    )


def _make_validator() -> OntologyValidatorService:
    return OntologyValidatorService(_make_schema())


# ---------------------------------------------------------------------------
# OntologyValidatorService — node validation
# ---------------------------------------------------------------------------


def test_validate_node_accepts_valid_node():
    v = _make_validator()
    v.validate_node(
        "Equipment",
        {"tag_number": "P-101", "equipment_class": "Pump"},
    )


def test_validate_node_accepts_node_with_optional_fields():
    v = _make_validator()
    v.validate_node(
        "Equipment",
        {
            "tag_number": "P-101",
            "equipment_class": "Pump",
            "manufacturer": "ACME",
        },
    )


def test_validate_node_rejects_missing_required_property():
    v = _make_validator()
    with pytest.raises(OntologyViolationError) as exc_info:
        v.validate_node("Equipment", {"tag_number": "P-101"})
    assert "equipment_class" in exc_info.value.violation
    assert exc_info.value.node_type == "Equipment"


def test_validate_node_rejects_all_missing_required_properties():
    v = _make_validator()
    with pytest.raises(OntologyViolationError) as exc_info:
        v.validate_node("Equipment", {})
    assert "tag_number" in exc_info.value.violation
    assert "equipment_class" in exc_info.value.violation


def test_validate_node_rejects_unknown_node_type():
    v = _make_validator()
    with pytest.raises(OntologyViolationError) as exc_info:
        v.validate_node("UnknownType", {"some_prop": "value"})
    assert "UnknownType" in str(exc_info.value)


def test_validate_node_raises_ontology_violation_error_subclass():
    v = _make_validator()
    with pytest.raises(OntologyViolationError):
        v.validate_node("Asset", {"tag_number": "A-001"})


# ---------------------------------------------------------------------------
# OntologyValidatorService — relation validation
# ---------------------------------------------------------------------------


def test_validate_relation_accepts_valid_relation():
    v = _make_validator()
    v.validate_relation("Sensor", "MONITORS", "Equipment")


def test_validate_relation_accepts_all_defined_relations():
    v = _make_validator()
    v.validate_relation("Equipment", "EXHIBITS", "FailureMode")
    v.validate_relation("Document", "REFERENCES", "Equipment")


def test_validate_relation_rejects_wrong_source():
    v = _make_validator()
    with pytest.raises(OntologyViolationError):
        v.validate_relation("Equipment", "MONITORS", "Sensor")


def test_validate_relation_rejects_wrong_target():
    v = _make_validator()
    with pytest.raises(OntologyViolationError):
        v.validate_relation("Sensor", "MONITORS", "FailureMode")


def test_validate_relation_rejects_unknown_relation_type():
    v = _make_validator()
    with pytest.raises(OntologyViolationError):
        v.validate_relation("Equipment", "INVENTS", "Sensor")


def test_validate_relation_rejects_ad_hoc_relation():
    v = _make_validator()
    with pytest.raises(OntologyViolationError):
        v.validate_relation("Document", "LOVES", "Equipment")


# ---------------------------------------------------------------------------
# OntologyViolationError structure (Engineering Bible §29)
# ---------------------------------------------------------------------------


def test_violation_error_has_node_type_and_violation_fields():
    err = OntologyViolationError(
        "Equipment", "missing required properties: ['tag_number']"
    )
    assert err.node_type == "Equipment"
    assert "tag_number" in err.violation
    assert isinstance(err, Exception)


def test_violation_error_message_contains_both_fields():
    err = OntologyViolationError("Sensor", "illegal relation")
    msg = str(err)
    assert "Sensor" in msg
    assert "illegal relation" in msg


# ---------------------------------------------------------------------------
# get_schema round-trip
# ---------------------------------------------------------------------------


def test_get_schema_returns_loaded_schema():
    v = _make_validator()
    schema = v.get_schema()
    assert schema.version == "1.0"
    assert "Equipment" in schema.node_types
    assert len(schema.allowed_relations) == 3


# ---------------------------------------------------------------------------
# YAML loader — validates actual ontology YAML (CI build gate)
# ---------------------------------------------------------------------------


def test_ontology_yaml_validates_against_json_schema():
    """The actual ontology YAML must pass JSON Schema validation.

    This test acts as the CI build gate: a malformed ontology YAML fails here.
    """
    from app.infrastructure.ontology.yaml_loader import load_ontology

    repo_root = Path(__file__).parents[2]
    ontology_path = repo_root / "ontology" / "industrial_ontology.yaml"

    schema = load_ontology(ontology_path)

    assert schema.version == "1.0"
    assert len(schema.node_types) == 11
    assert len(schema.allowed_relations) >= 10


def test_ontology_yaml_has_all_required_node_types():
    from app.infrastructure.ontology.yaml_loader import load_ontology

    repo_root = Path(__file__).parents[2]
    ontology_path = repo_root / "ontology" / "industrial_ontology.yaml"
    schema = load_ontology(ontology_path)

    required_types = {
        "Asset",
        "Equipment",
        "Sensor",
        "FailureMode",
        "Procedure",
        "Document",
        "Maintenance",
        "Inspection",
        "Regulation",
        "Personnel",
        "Process",
    }
    assert required_types == set(schema.node_types.keys())


def test_ontology_yaml_relation_types_are_subset_of_allowed():
    from app.infrastructure.ontology.yaml_loader import load_ontology

    repo_root = Path(__file__).parents[2]
    ontology_path = repo_root / "ontology" / "industrial_ontology.yaml"
    schema = load_ontology(ontology_path)

    allowed_relation_names = {r.relation_type for r in schema.allowed_relations}
    expected = {
        "MONITORS",
        "IS_PART_OF",
        "EXHIBITS",
        "REFERENCES",
        "PERFORMED_BY",
        "REQUIRES",
        "INDICATES_FAILURE_OF",
    }
    assert expected <= allowed_relation_names


def test_yaml_loader_rejects_invalid_yaml(tmp_path: Path):
    from app.infrastructure.ontology.yaml_loader import load_ontology

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("this_is_not_valid_ontology: true\n", encoding="utf-8")

    with pytest.raises((ValueError, KeyError, Exception)):
        load_ontology(bad_yaml)


def test_yaml_loader_rejects_missing_node_types(tmp_path: Path):
    from app.infrastructure.ontology.yaml_loader import load_ontology

    bad_yaml = tmp_path / "missing.yaml"
    bad_yaml.write_text(
        "version: '1.0'\nallowed_relations: []\n",
        encoding="utf-8",
    )
    with pytest.raises((ValueError, Exception)):
        load_ontology(bad_yaml)
