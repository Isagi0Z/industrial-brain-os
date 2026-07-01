# M7 Walkthrough — Entity & Relation Extraction Pipeline

## Overview

M7 implements a two-pass knowledge graph extraction pipeline that runs automatically
at the end of every document ingestion job. After embedding (M4), the worker calls
`ExtractionUseCase.run_for_document()` which:

1. Loads all `DocumentChunk` rows for the document.
2. For each chunk — runs spaCy NER + EntityRuler to extract industrial entities.
3. Resolves near-duplicate entities with Levenshtein distance ≤ 2.
4. Validates each entity against the ontology (from M6) before accepting it.
5. Calls the LLM via `IModelGateway` to extract relations between resolved entities.
6. Validates each relation against the ontology allowed-relations list.
7. Marks relations with confidence < 0.6 as `{tentative: true}`.
8. Writes all valid entities and relations to Neo4j via idempotent `MERGE` statements.
9. Advances job status: `INDEXED → KG_EXTRACTING → KG_POPULATED → COMPLETED`.

## Architecture

```
IngestionWorker
    │
    ├─ parse_document()       (M3) QUEUED → CHUNKED
    ├─ embed_document()       (M4) CHUNKED → INDEXED
    └─ run_for_document()     (M7) INDEXED → KG_EXTRACTING → KG_POPULATED → COMPLETED
            │
            ├─ SpacyEntityExtractor          (infrastructure)
            │      en_core_web_sm + EntityRuler
            │
            ├─ LevenshteinEntityResolver     (infrastructure)
            │      rapidfuzz distance ≤ 2
            │
            ├─ OntologyValidatorService      (domain, M6)
            │      validate_node() before each entity
            │
            ├─ LLMRelationExtractor          (infrastructure)
            │      IModelGateway + relation_extraction.yaml
            │
            ├─ OntologyValidatorService
            │      validate_relation() before each edge
            │
            └─ Neo4jKGWriter                 (infrastructure)
                   MERGE entity nodes
                   MERGE HAS_CHUNK relationship
                   MERGE entity-entity relations
```

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/extraction/models.py`, `domain/extraction/interfaces.py` |
| Application | `application/extraction/extraction_use_case.py` |
| Infrastructure | `infrastructure/extraction/spacy_entity_extractor.py`, `levenshtein_entity_resolver.py`, `llm_relation_extractor.py`, `neo4j_kg_writer.py` |
| Prompt | `ai/prompts/relation_extraction.yaml` |

## Entity Extraction

### Industrial Tag Patterns (EntityRuler)

```
Pattern: [A-Z]{1,4}-\d+     → e.g. P-101, VLV-202, PT-100, FT-300
Pattern: [A-Z]{1,4}\d{3,}   → e.g. TE001, LT100
```

### Prefix → Ontology Type Mapping

| Prefixes | Ontology Type | Measurement Type |
|----------|--------------|------------------|
| PT, PI, PIC | Sensor | pressure |
| TE, TI, TIC | Sensor | temperature |
| FT, FI, FIC, FE | Sensor | flow |
| LT, LI, LIC | Sensor | level |
| AT, AIC | Sensor | analytical |
| P, PMP | Equipment | — |
| V, VLV, XV, CV | Equipment | — |
| E, EX, HX | Equipment | — |
| TK, T | Equipment | — |
| C, K, M, R, AG | Equipment | — |
| UNIT, TRAIN | Asset | — |

### spaCy Default NER → Ontology Type

| spaCy Label | Ontology Type |
|------------|--------------|
| PERSON | Personnel |
| ORG, FAC | Asset |
| PRODUCT | Equipment |
| LOC, GPE | Process |
| WORK_OF_ART | Document |

## Entity Resolution

`LevenshteinEntityResolver` groups entities by type and merges those whose tag
numbers are within Levenshtein distance ≤ 2. The shorter (more canonical) form
is kept. Different entity types are never merged.

Example:
```
P-101  (Equipment)  +  P-1O1  (Equipment)  →  P-101  (distance=1)
PT-100 (Sensor)    +  PT-100 (Equipment)  →  kept separate (different types)
```

## Relation Extraction

`LLMRelationExtractor` sends the chunk text + resolved entity list to the
LLM (via the same `IModelGateway` used by the chat copilot). The prompt is
loaded from `ai/prompts/relation_extraction.yaml` (ADR-020: version-controlled
PromptOps).

Expected LLM output:
```json
[
  {"source_tag": "PT-100", "source_type": "Sensor",
   "relation_type": "MONITORS",
   "target_tag": "P-101", "target_type": "Equipment",
   "confidence": 0.92}
]
```

Any relation_type not in the ontology's allowed list is rejected with a debug log.
Relations with confidence < 0.6 are accepted but written with `{tentative: true}`.

## Neo4j Schema After M7

New node types written at ingestion time:
```cypher
MERGE (n:Equipment {tag_number: $tag}) SET n += $props
MERGE (n:Sensor {tag_number: $tag}) SET n += $props
MERGE (n:Asset {tag_number: $tag}) SET n += $props

MERGE (d:Document {source_id: $doc_id})
MERGE (c:DocumentChunk {chunk_id: $chunk_id})
MERGE (d)-[:HAS_CHUNK]->(c)
MERGE (c)-[:MENTIONS]->(e)

MERGE (s:Sensor {tag_number: $src})-[r:MONITORS]->(t:Equipment {tag_number: $tgt})
SET r += {confidence: 0.92}
```

## Configuration

| Setting | Default |
|---------|---------|
| `SPACY_MODEL` | `en_core_web_sm` |
| `KG_CONFIDENCE_THRESHOLD` | `0.6` |
| `RELATION_EXTRACTION_PROMPT_FILE` | `ai/prompts/relation_extraction.yaml` |

## Job Status Flow

```
QUEUED → EXTRACTING → EXTRACTED → PARSING → CHUNKED → EMBEDDING
→ INDEXED → KG_EXTRACTING → KG_POPULATED → COMPLETED
```

New states added in M7:
- `KG_EXTRACTING` (93% progress): entity + relation extraction running
- `KG_POPULATED` (97% progress): all valid entities/relations written to Neo4j
