# M6 Walkthrough — Industrial Ontology Schema & Neo4j Initialization

## Overview

M6 defines and enforces the Industrial Ontology in Neo4j per ADR-010 (ISO 14224 / ISO 15926 alignment). It introduces:

- A version-controlled `ontology/industrial_ontology.yaml` file covering 11 node types and 17 allowed relationships
- JSON Schema validation of that YAML (enforced at load-time and in pytest CI)
- A pure domain `OntologyValidatorService` that validates node creation and relationship creation before any Neo4j write
- Structured `OntologyViolationError` with `node_type` + `violation` fields (Engineering Bible §29)
- Neo4j constraints and indexes extended with `FailureMode.failure_code` (UNIQUE) and `Equipment.manufacturer` (INDEX)
- `GET /api/v1/ontology/schema` endpoint returning the ontology as JSON

## Architecture

```
ontology/industrial_ontology.yaml
         │
    yaml_loader.py (infrastructure)
         │  ← jsonschema validation at load time
    OntologySchema (domain model)
         │
    OntologyValidatorService (domain service)
         │
    GET /api/v1/ontology/schema (presentation)
    (future) Neo4j write services call validate_node / validate_relation
```

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/ontology/models.py`, `domain/ontology/interfaces.py`, `domain/ontology/validator.py` |
| Infrastructure | `infrastructure/ontology/yaml_loader.py`, `infrastructure/database/infra_init.py` (updated) |
| Presentation | `presentation/api/v1/endpoints/ontology.py` |
| Schema | `ontology/industrial_ontology.yaml` |

## Ontology Summary

**11 Node Types** (all ISO 14224 / ISO 15926 aligned):

| Node Type | Key Required Properties |
|-----------|------------------------|
| Asset | tag_number, name |
| Equipment | tag_number, equipment_class |
| Sensor | tag_number, measurement_type |
| FailureMode | failure_code, description |
| Procedure | procedure_id, title, procedure_type |
| Document | source_id, title, document_type |
| Maintenance | work_order_id, maintenance_type |
| Inspection | inspection_id, inspection_type |
| Regulation | regulation_id, title, issuing_body |
| Personnel | personnel_id, role |
| Process | process_id, process_name |

**17 Allowed Relationships**: MONITORS, IS_PART_OF, EXHIBITS, REFERENCES, PERFORMED_BY, REQUIRES, INDICATES_FAILURE_OF

## Neo4j Schema Changes

Added to `infra_init.py`:
- **Constraint**: `UNIQUE (n:FailureMode {failure_code})`
- **Index**: `INDEX ON :Equipment(manufacturer)`

Existing (from M1): Asset.tag_number, Equipment.tag_number, Sensor.tag_number, Document.source_id (all UNIQUE); FailureMode.failure_code, Procedure.procedure_type (indexes).

## OntologyViolationError Structure

```python
class OntologyViolationError(Exception):
    node_type: str     # e.g. "Equipment"
    violation: str     # e.g. "missing required properties: ['equipment_class']"
    message: str       # "Ontology violation [Equipment]: missing required ..."
```

## Configuration

| Setting | Default |
|---------|---------|
| `ONTOLOGY_FILE` | `ontology/industrial_ontology.yaml` |
