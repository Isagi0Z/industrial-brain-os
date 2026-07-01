# M7 Verification Report

## Quality Gate Results

| Gate | Tool | Result |
|------|------|--------|
| Formatting | black | ✅ Pass |
| Lint | ruff | ✅ Pass (11 auto-fixed, 0 remaining) |
| Type check | mypy | ✅ Pass (0 issues) |
| Unit tests | pytest | ✅ 29/29 M7 tests passed |
| All unit tests | pytest (per-file) | ✅ 85 tests across 5 files |
| TS type check | tsc --noEmit | ✅ No errors (no frontend changes) |

## New Tests (test_extraction.py — 29 tests)

| Class | Test | Covers |
|-------|------|--------|
| `TestLevenshteinEntityResolver` | `test_identical_tags_deduplicated` | same tag → merged |
| | `test_distance_1_same_type_deduplicated` | distance=1 → merged |
| | `test_distance_3_not_merged` | large distance → not merged |
| | `test_different_types_not_merged` | different types → not merged |
| | `test_empty_input` | empty list → empty |
| | `test_untagged_entities_pass_through` | no tag_number → pass through |
| | `test_canonical_form_kept` | shorter tag kept as canonical |
| | `test_large_distance_not_merged` | P-001 vs V-999 → not merged |
| `TestSpacyEntityExtractor` | `test_extracts_industrial_tag_as_equipment` | P- prefix → Equipment |
| | `test_extracts_sensor_tag` | PT- prefix → Sensor |
| | `test_empty_chunk_returns_empty` | empty text → [] |
| | `test_chunk_id_set_on_entities` | entity.chunk_id == chunk.id |
| | `test_sensor_has_measurement_type` | FT- → measurement_type=flow |
| `TestLLMRelationExtractor` | `test_parses_valid_relation_json` | JSON array → ExtractedRelation |
| | `test_returns_empty_on_invalid_json` | non-JSON → [] |
| | `test_strips_markdown_fences` | ```json fences stripped |
| | `test_single_entity_skips_extraction` | < 2 entities → no LLM call |
| `TestExtractionModels` | `test_extracted_entity_defaults` | dataclass defaults |
| | `test_extracted_relation_default_confidence` | confidence=1.0 default |
| | `test_extraction_result_empty_lists` | empty entity/relation lists |
| `TestExtractionUseCase` | `test_no_chunks_advances_to_completed` | no chunks → COMPLETED |
| | `test_entities_without_tag_number_skipped` | untagged entities skipped |
| | `test_valid_entity_written_to_kg` | tagged entity → KG write |
| | `test_relation_below_threshold_gets_tentative_flag` | confidence<0.6 → tentative=True |
| | `test_ontology_violation_skips_relation` | INVALID_REL → not written |
| `TestJobStatusEnum` | `test_kg_extracting_present` | KG_EXTRACTING in enum |
| | `test_kg_populated_present` | KG_POPULATED in enum |
| | `test_kg_extracting_value` | value == "KG_EXTRACTING" |
| | `test_kg_populated_value` | value == "KG_POPULATED" |

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
```

## Files Modified

```
backend/app/domain/document/constants.py      — +KG_EXTRACTING, +KG_POPULATED in JobStatus; JOB_PROGRESS updated
backend/app/infrastructure/document/worker.py — added extraction step (asyncio.run) after embed_document
backend/app/infrastructure/di/container.py    — wired ExtractionUseCase + all components; updated IngestionWorker
backend/app/infrastructure/config/settings.py — +SPACY_MODEL, +KG_CONFIDENCE_THRESHOLD, +RELATION_EXTRACTION_PROMPT_FILE
docs/implementation_roadmap.md               — M7 checklist all [x]; commit SHA TBD
```

## Architecture Compliance

- Clean Architecture: domain → application → infrastructure; no framework in domain ✅
- ADR-020 PromptOps: relation_extraction.yaml version-controlled, never hardcoded ✅
- ADR-013 IModelGateway: LLMRelationExtractor uses IModelGateway, no concrete LLM client in domain ✅
- ADR-001 blocking calls: asyncio.run() in IngestionWorker thread ✅
- Engineering Bible §18: no ad-hoc relations; all validated against ontology YAML ✅
- Engineering Bible §29: OntologyViolationError used for rejected entities/relations ✅
- OntologyValidatorService called before every Neo4j write ✅
- Confidence < 0.6 → tentative=True on relation ✅
- Neo4j MERGE: idempotent writes, no duplicate nodes or edges ✅

## Pre-existing Known Issues (NOT M7)

- `test_integration_index_and_semantic_search` fails when Docker/Qdrant not running — pre-existing from M4
- 4 setup errors (PermissionError on Windows temp dir) occur only in combined test runs — pre-existing OS issue
