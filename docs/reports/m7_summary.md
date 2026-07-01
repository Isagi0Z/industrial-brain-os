# M7 Summary — Entity & Relation Extraction Pipeline

**Milestone**: M7
**Status**: ✅ Complete
**Date**: 2026-07-01

## Delivered

### Domain Layer
- `ExtractedEntity`, `ExtractedRelation`, `ExtractionResult` — pure dataclasses
- `IEntityExtractor`, `IRelationExtractor`, `IEntityResolver`, `IKGWriter` — domain interfaces

### Application Layer
- `ExtractionUseCase.run_for_document()` — orchestrates the full pipeline:
  chunk loading → entity extraction → entity resolution → ontology validation → relation extraction → ontology validation → Neo4j write → job status updates

### Infrastructure Layer
- `SpacyEntityExtractor` — `en_core_web_sm` + `EntityRuler` with industrial tag patterns; maps 30+ prefixes to Equipment/Sensor/Asset ontology types
- `LevenshteinEntityResolver` — `rapidfuzz` Levenshtein distance ≤ 2 on tag numbers; keeps shorter canonical form
- `LLMRelationExtractor` — loads `relation_extraction.yaml` (ADR-020), calls `IModelGateway.generate()`, parses JSON array, strips markdown fences
- `Neo4jKGWriter` — idempotent `MERGE` for entity nodes, `HAS_CHUNK` relationship, entity-entity relation edges with confidence/tentative properties

### Prompt Engineering (ADR-020)
- `ai/prompts/relation_extraction.yaml` — system prompt + extraction template; defines 17 allowed relation types; expects JSON array output

### Worker Integration
- `IngestionWorker` — third step added: `asyncio.run(extraction_use_case.run_for_document())`
- `JobStatus` — `KG_EXTRACTING` (93%) and `KG_POPULATED` (97%) added; `JOB_PROGRESS` updated
- `DIContainer.get_extraction_use_case()` — wires `SpacyEntityExtractor`, `LevenshteinEntityResolver`, `LLMRelationExtractor`, `Neo4jKGWriter`, `OntologyValidatorService`

## Files Created

```
backend/app/domain/extraction/__init__.py
backend/app/domain/extraction/models.py
backend/app/domain/extraction/interfaces.py
backend/app/application/extraction/__init__.py
backend/app/application/extraction/extraction_use_case.py
backend/app/infrastructure/extraction/__init__.py
backend/app/infrastructure/extraction/spacy_entity_extractor.py
backend/app/infrastructure/extraction/levenshtein_entity_resolver.py
backend/app/infrastructure/extraction/llm_relation_extractor.py
backend/app/infrastructure/extraction/neo4j_kg_writer.py
backend/ai/prompts/relation_extraction.yaml
backend/tests/test_extraction.py
docs/walkthroughs/m7_walkthrough.md
docs/verification/m7_verification.md
docs/reports/m7_summary.md
```

## Files Modified

```
backend/app/domain/document/constants.py
backend/app/infrastructure/document/worker.py
backend/app/infrastructure/di/container.py
backend/app/infrastructure/config/settings.py
docs/implementation_roadmap.md
```

## Test Results

- **29 new M7 tests** — all pass
- **85 unit tests total** (5 files) — all pass per-file
- **103 total unit+integration tests** — 102 pass, 1 integration test skipped (Docker not running)

## Engineering Bible Compliance

- §18 Knowledge Graph Standards — all edges validated against ontology YAML before write ✅
- §29 Error Handling — `OntologyViolationError` used for rejected nodes/relations ✅
- ADR-013 IModelGateway — LLM interface used, no concrete client in domain ✅
- ADR-020 PromptOps — relation_extraction.yaml in version control ✅
- ADR-001 Thread safety — `asyncio.run()` used in worker daemon thread ✅
- Confidence threshold 0.6 — tentative flag applied, not data loss ✅
- MERGE idempotence — duplicate document uploads safe ✅
