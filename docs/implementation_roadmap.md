# Industrial Brain OS: Master Implementation Roadmap

> **Source of truth**: This file is the master milestone tracker for the project.
> Update checkboxes as work completes. Do not modify milestone scope without an ADR.
> Architecture: `industrial_brain_architecture_v2.md` | Governance: `engineering_bible.md` | Decisions: `architecture_decision_records.md`

---

## Status Legend

| Symbol | Meaning |
| :----- | :------ |
| ✅ | Complete |
| 🔄 | In Progress |
| ⏳ | Blocked (dependency incomplete) |
| 🔲 | Not Started |

---

## Completed Baseline (Pre-Roadmap Commits)

The following work is already merged into `feature/bootstrap` as of the roadmap creation date. These are not assigned milestone numbers — they are the foundation every milestone builds on.

| Commit | What Was Built |
| :----- | :------------- |
| `3061f0a` | Repository skeleton: Clean Architecture folders, Docker Compose (PostgreSQL, Neo4j, Qdrant, Redis, MinIO), Makefile, shared packages |
| `c6b9ff6` | Auth & RBAC: JWT, user domain entities, login/register endpoints, RBAC middleware |
| `4bb9a3b` | Document Management Foundation: Document domain entities, upload/list/details UI components, document infrastructure stubs |

---

---

# MVP PHASE
> **Goal**: A working demo where a user uploads an industrial PDF, asks a question, and receives a cited answer. Every milestone in this phase independently advances toward that demo.

---

## M1 — Infrastructure Validation & Database Initialization ✅

**Phase**: MVP
**Difficulty**: Easy
**Depends on**: Baseline bootstrap commit (`3061f0a`)
**Blocks**: M2, M4, M6
**Status**: ✅ Complete
**Completion Date**: 2026-06-30
**Commit SHA**: `ca76367`

### Objective
Verify all five Docker services start healthy. Initialize PostgreSQL schema via Alembic, Qdrant collections, Neo4j constraints, and MinIO buckets so all downstream milestones have clean storage targets.

### Deliverables
- Alembic migration baseline creating all PostgreSQL tables
- Qdrant collection `document_chunks` initialized with correct vector dimensions
- Neo4j uniqueness constraints and indexes matching the Industrial Ontology
- MinIO bucket `industrial-documents` initialized with access policy
- `scripts/init_infra.sh` confirming all services are healthy before app starts
- `docker compose up` reaches full health in under 60 seconds

### Checklist
- [x] Alembic configured and `alembic init` baseline migration committed
- [x] Migration creates tables: `users`, `roles`, `documents`, `document_chunks`, `audit_logs`, `jobs`
- [x] Qdrant collection `document_chunks` created: dimension=1024, distance=Cosine, payload indexes on `document_id`, `role_scope`, `page_number`
- [x] Neo4j constraints: `UNIQUE (n:Asset {tag_number})`, `UNIQUE (n:Equipment {tag_number})`, `UNIQUE (n:Sensor {tag_number})`
- [x] Neo4j indexes: `INDEX ON :Document(source_id)`, `INDEX ON :FailureMode(failure_code)`
- [x] MinIO bucket `industrial-documents` created with private policy
- [x] MinIO bucket `processed-chunks` created for extracted text artifacts
- [x] Health check script exits 0 only when all five services respond healthy
- [x] `make db-migrate` runs migrations cleanly from a fresh state
- [x] `make db-reset` wipes and re-applies all migrations (for dev resets)
- [x] All migration files committed, no raw SQL changes applied to live schema

---

## M2 — Document Ingestion Pipeline ✅

**Phase**: MVP
**Difficulty**: Medium
**Depends on**: M1
**Blocks**: M3
**Status**: ✅ Complete
**Completion Date**: 2026-06-30
**Commit SHA**: `39cc5ad`

### Objective
Complete the document upload flow end-to-end: file received by FastAPI → validated → stored in MinIO → job record created in PostgreSQL → queued in Redis for downstream processing.

### Deliverables
- `POST /api/v1/documents/` fully wired to MinIO `industrial-documents` bucket
- `GET /api/v1/documents/{id}/status` returning `JobStatusResponse` with `progress_pct`
- PostgreSQL `jobs` table tracking ingestion state machine (`QUEUED → PROCESSING → COMPLETED → FAILED`)
- `POST /api/v1/documents/{id}/retry` re-queuing FAILED documents
- Frontend: drag-and-drop upload, status badges, auto-polling, retry button
- 13 unit tests covering all validation and success/failure paths

### Checklist
- [x] `DocumentUpload` component wired to real `POST /api/v1/documents/` endpoint
- [x] FastAPI endpoint validates MIME type: PDF, DOCX, DOC, XLSX, XLS, PNG, JPEG
- [x] File stored in MinIO `industrial-documents` bucket with key `{document_id}/v1/{filename}`
- [x] SHA-256 hash computed; duplicate detection rejects re-uploads of identical content
- [x] `documents` record created in PostgreSQL with `storage_key`, `size_bytes`, `mime_type`, `created_by`
- [x] `jobs` record created in state `QUEUED` linked to document ID
- [x] Job payload pushed to Redis `ingestion:jobs` list (RPUSH for FIFO)
- [x] Document status updated to `READY_FOR_PROCESSING` after successful queue
- [x] `GET /api/v1/documents/{id}/status` returns `status`, `progress_pct`, `error_message`
- [x] `DocumentList` component polls `/` every 5 seconds when in-progress documents exist
- [x] `POST /api/v1/documents/{id}/retry` re-queues documents with `FAILED` job status
- [x] Input validated at API boundary: file size ≤ 100 MB
- [x] Unit tests: oversized file (413), invalid MIME, duplicate SHA-256, success path, XLSX, PNG, bucket name, status endpoint, retry
- [x] No raw MinIO/Redis credentials in application code — read from environment via `config/settings.py`

---

## M3 — OCR & Layout-Aware Parsing

**Phase**: MVP
**Difficulty**: Hard
**Depends on**: M2
**Blocks**: M4

### Objective
Transform raw page extraction into semantically structured, hierarchical chunks. Apply PaddleOCR for scanned/image-heavy pages, LayoutParser for zone detection, and hierarchical chunking that keeps tables, figures, and callout blocks intact per ADR-011 and ADR-012.

### Deliverables
- Layout detection pipeline classifying each page zone: `heading`, `paragraph`, `table`, `figure`, `caption`, `footer`
- PaddleOCR applied to image-based pages and low-confidence text blocks
- Hierarchical chunking producing `DocumentChunk` entities with parent section reference
- Table cells extracted as structured JSON with row/column coordinates preserved
- Figure/schematic regions cropped and stored as separate MinIO objects
- `DocumentChunk` records persisted in PostgreSQL with full spatial metadata

### Checklist
- [x] LayoutParser configured with `lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config` (or equivalent open model) — PyMuPDF block detection used per ADR-012
- [x] Layout zones classified per page: confidence threshold ≥ 0.75 required to accept zone
- [x] Fallback: if layout confidence < 0.75, fall back to standard PyMuPDF paragraph extraction (ADR-012 mitigation)
- [x] PaddleOCR (`paddleocr --use_angle_cls true --lang en`) applied to: image-only PDFs, scanned TIFFs, figure regions
- [x] OCR output preserves spatial coordinates `(x, y, w, h)` per text line for downstream citation highlighting
- [x] Hierarchical chunker: sections → subsections → paragraphs; tables kept as single chunk; figures as single chunk
- [x] Chunk size targets: 512 tokens soft max, 768 hard max; overlap 64 tokens between adjacent paragraph chunks
- [x] `DocumentChunk` entity fields: `chunk_id`, `document_id`, `chunk_index`, `chunk_type`, `text`, `page_number`, `parent_section_header`, `bbox_json`, `token_count`
- [x] Table chunks store `table_data_json`: array of `{row, col, value}` objects
- [x] Figure chunks store `figure_storage_key` pointing to cropped image in MinIO
- [x] All `DocumentChunk` records inserted into PostgreSQL in a single transaction per document
- [x] Job state transitions: `EXTRACTED → PARSING → CHUNKED`
- [x] Cyclomatic complexity ≤ 10 per parsing function (Engineering Bible §1)
- [x] Unit tests: layout zone classifier, OCR fallback trigger, hierarchical chunker, table cell extractor
- [x] Integration test: process one sample industrial PDF end-to-end through M2→M3 and verify chunk count and structure

**Completed:** 2026-06-30 | Commit: 12ede20

---

## M4 — Embedding Pipeline & Qdrant Indexing ✅

**Phase**: MVP
**Difficulty**: Medium
**Depends on**: M3
**Blocks**: M5, M8
**Status**: ✅ Complete
**Completion Date**: 2026-06-30
**Commit SHA**: `0f05345`

### Objective
Generate dense vector embeddings from `DocumentChunk` text, batch-upsert them into Qdrant with full metadata payloads, and expose a working `/search/semantic` endpoint. Also implement BM25 keyword search for exact technical code lookup per ADR-009, Stage 1.

### Deliverables
- Embedding model integrated: `BAAI/bge-large-en-v1.5` (1024-dim) via HuggingFace `sentence-transformers`
- Qdrant batch upsert pipeline wiring `DocumentChunk` → vector point with payload
- BM25 index over chunk text with PostgreSQL persistence (`bm25_index` table, migration 003)
- `GET /api/v1/search/semantic?q=&limit=` endpoint returning ranked chunk results
- `GET /api/v1/search/keyword?q=&limit=` endpoint for BM25 keyword search
- Both endpoints enforce RBAC: results filtered by `role_scope` payload field (ADR-005 + Engineering Bible §15)

### Checklist
- [x] `sentence-transformers` model `BAAI/bge-large-en-v1.5` loaded once at startup, not per request
- [x] Embedding inference runs in thread pool via `run_in_threadpool` (ADR-001 mitigation — no blocking event loop)
- [x] Batch size: 32 chunks per embedding call; progress logged per batch
- [x] Qdrant point payload per chunk: `document_id`, `chunk_index`, `chunk_type`, `page_number`, `parent_section_header`, `role_scope`, `document_title`, `revision_date`
- [x] `role_scope` payload field populated from document metadata and used as Qdrant filter on every query
- [x] Qdrant upsert uses `upsert` (idempotent), not `insert` — safe to re-run on document re-ingestion
- [x] BM25 index built per-document at ingestion time; term frequencies stored in PostgreSQL `bm25_index` table
- [x] `/search/semantic` returns: `chunk_text`, `score`, `document_title`, `page_number`, `bbox_json`, `chunk_type`
- [x] `/search/keyword` returns same schema as semantic for uniform client consumption
- [x] Both endpoints: `limit` default=10, max=50; scores normalized 0–1
- [x] Both endpoints validated with RBAC middleware — unauthenticated requests return 401
- [x] No `Any` typing in embedding service or Qdrant client wrapper (Engineering Bible §8)
- [x] Job state transitions: `CHUNKED → EMBEDDING → INDEXED`
- [x] Unit tests: embedding service, Qdrant client wrapper, BM25 indexer, RBAC filter logic
- [x] Integration test: index 5 chunks, run semantic query, verify top-1 result is correct chunk

---

## M5 — Basic Chat API & Copilot UI ✅

**Phase**: MVP
**Difficulty**: Medium
**Depends on**: M4
**Blocks**: M9 (agents extend this endpoint)
**Status**: ✅ Complete
**Completion Date**: 2026-06-30
**Commit SHA**: `7f914b9`

### Objective
Wire vector search results into an LLM to produce cited answers. Expose a streaming `/chat` WebSocket endpoint. Connect the React frontend with a chat interface displaying streamed responses and source citations. **This is the first publicly demo-able milestone.**

### Deliverables
- `POST /api/v1/chat` and `WS /api/v1/chat/stream` endpoints
- Ollama (local) and Gemini API (cloud fallback) LLM integration via `Model Gateway` abstraction (ADR-001)
- Response generator: markdown-formatted answers with inline source citations `[Doc Title, p.N]`
- React `ChatInterface` component with streaming token display and citation cards
- End-to-end flow: upload PDF → ask question → get cited answer within 5 seconds for simple queries

### Checklist
- [x] `ModelGatewayInterface` abstract class defined in `domain/` — no concrete LLM client in domain layer (ADR-013)
- [x] `OllamaGateway` and `GeminiGateway` implementations in `infrastructure/` implementing the interface
- [x] Environment variable `LLM_PROVIDER=ollama|gemini` selects active gateway at startup
- [x] Fallback: if primary gateway returns error, retry with fallback gateway using exponential backoff (Engineering Bible §23)
- [x] Retry policy: max 3 attempts, backoff 1s→2s→4s; error logged with Correlation-ID at each attempt
- [x] `max_tokens` enforced per request: 2048 default, configurable via env
- [x] Chat endpoint receives: `{query: str, session_id: str, top_k: int = 5}`
- [x] Context builder: fetches top-k vector chunks, deduplicates by `chunk_id`, ranks by score, truncates to token budget
- [x] System prompt loaded from `ai/prompts/knowledge_copilot.yaml` (not hardcoded — ADR-020)
- [x] Response streamed token-by-token via WebSocket; final message includes `citations[]` array
- [x] Citation schema: `{document_title, page_number, chunk_text_excerpt, score, storage_key}`
- [x] Session history stored in Redis with 1-hour TTL (Engineering Bible §3 — short-term memory)
- [x] `ChatInterface` React component: message thread, streaming token animation, citation accordion cards
- [x] Citation card links to document viewer (stub route at this milestone)
- [x] Token usage logged per request: `{prompt_tokens, completion_tokens, model, latency_ms}` (Engineering Bible §23)
- [x] `POST /api/v1/chat` non-streaming variant returns same structure for mobile/field-tech clients
- [x] Unit tests: context builder, citation resolver, gateway fallback logic (11 tests)
- [ ] Manual demo test: upload `sample_manual.pdf`, ask "What is the operating pressure of valve VLV-101?", verify cited answer

---

---

# PHASE 2
> **Goal**: Knowledge Graph populated, GraphRAG active, Knowledge Brain agent live. Platform transitions from "semantic search with LLM" to "industrial reasoning with entity relationships."

---

## M6 — Industrial Ontology Schema & Neo4j Initialization

**Phase**: Phase 2
**Difficulty**: Medium
**Depends on**: M1
**Blocks**: M7

### Objective
Define and enforce the Industrial Ontology in Neo4j per the architecture specification (§3) and ADR-010. Node types, required properties, and relationship types must be schema-validated before any entity extraction pipeline writes to the graph.

### Deliverables
- `ontology/industrial_ontology.yaml` version-controlled schema file defining all node types, properties, and allowed relationships
- Neo4j constraint and index migration scripts applied via startup initialization
- Schema validator service that rejects writes violating the ontology
- Node types: `Asset`, `Equipment`, `Sensor`, `FailureMode`, `Procedure`, `Document`, `Maintenance`, `Inspection`, `Regulation`, `Personnel`, `Process`
- Relationship types: `MONITORS`, `IS_PART_OF`, `EXHIBITS`, `REFERENCES`, `PERFORMED_BY`, `REQUIRES`, `INDICATES_FAILURE_OF`

### Checklist
- [ ] `ontology/industrial_ontology.yaml` committed with: node_types, required_properties, optional_properties, allowed_relations
- [ ] Schema file validated against JSON Schema on CI build — malformed ontology fails the build (ADR-020 pattern applied to ontology)
- [ ] Neo4j constraint: `UNIQUE (n:Asset {tag_number})`
- [ ] Neo4j constraint: `UNIQUE (n:Equipment {tag_number})`
- [ ] Neo4j constraint: `UNIQUE (n:Sensor {tag_number})`
- [ ] Neo4j constraint: `UNIQUE (n:Document {source_id})`
- [ ] Neo4j constraint: `UNIQUE (n:FailureMode {failure_code})`
- [ ] Neo4j index: `INDEX ON :Equipment(manufacturer)`
- [ ] Neo4j index: `INDEX ON :Procedure(procedure_type)`
- [ ] `OntologyValidatorService` in `domain/` rejects node creation if required properties are missing
- [ ] `OntologyValidatorService` rejects relationship creation if the source→target type combination is not in allowed_relations
- [ ] Validation errors return structured `OntologyViolationError` with node type and missing field (Engineering Bible §29)
- [ ] `GET /api/v1/ontology/schema` endpoint returns the current ontology YAML as JSON for frontend consumption
- [ ] Unit tests: validator accepts valid nodes, rejects nodes with missing required properties, rejects illegal relationships
- [ ] No ad-hoc relationship types permitted outside the ontology YAML (Engineering Bible §18)

---

## M7 — Entity & Relation Extraction Pipeline

**Phase**: Phase 2
**Difficulty**: Very Hard
**Depends on**: M3, M6
**Blocks**: M8

### Objective
Extract industrial entities and relationships from `DocumentChunk` text using a two-pass pipeline: spaCy NER for fast entity detection followed by LLM-guided relation extraction. Populate Neo4j with validated nodes and relationships. Perform entity resolution to merge duplicates (e.g., "VLV-101" and "Valve 101" → single `Equipment` node).

### Deliverables
- spaCy NER pipeline with custom industrial entity patterns for tag IDs, sensor codes, equipment classes
- LLM-guided relation extraction prompt (version-controlled in `ai/prompts/`)
- Entity resolution: fuzzy matching on tag numbers, manufacturer+model deduplication
- Neo4j population service: idempotent `MERGE` Cypher writes validated against the ontology
- `Document` → extracted entity count report logged per ingestion job
- Job state extended: `INDEXED → KG_EXTRACTING → KG_POPULATED`

### Checklist
- [ ] spaCy model: `en_core_web_trf` with custom `EntityRuler` patterns for industrial tag formats (e.g., `FT-\d+`, `VLV-\d+`, `TE-\d+`)
- [ ] spaCy NER labels mapped to ontology node types: `EQUIPMENT_TAG → Equipment`, `SENSOR_TAG → Sensor`, `PROCEDURE_REF → Procedure`
- [ ] LLM relation extraction prompt loaded from `ai/prompts/relation_extraction.yaml` — not hardcoded (ADR-020)
- [ ] Relation extraction prompt defines output schema: `{subject_tag, relation_type, object_tag}` JSON array
- [ ] Only ontology-approved `relation_type` values accepted; others discarded with warning log
- [ ] Entity resolution: Levenshtein distance ≤ 2 on tag numbers treated as same entity
- [ ] Entity resolution: same manufacturer + model_number treated as same `Equipment` node
- [ ] Neo4j writes: `MERGE (n:Equipment {tag_number: $tag}) SET n += $properties` — idempotent
- [ ] Relationship writes: `MERGE (a)-[r:MONITORS]->(b)` — no duplicate edges
- [ ] Each chunk that yields entities creates `HAS_CHUNK` relationship: `(doc:Document)-[:HAS_CHUNK]->(chunk:DocumentChunk)`
- [ ] Extraction confidence score stored as relationship property: `{confidence: float}`
- [ ] Relationships with confidence < 0.6 written with `{tentative: true}` flag — not used in high-confidence queries
- [ ] `OntologyValidatorService` called before every Neo4j write — write rejected if validation fails
- [ ] Extraction errors logged with chunk_id and document_id; job continues on per-chunk failures
- [ ] Unit tests: spaCy pattern matcher, relation prompt parser, entity resolver, Neo4j merge service
- [ ] Integration test: process sample chunk with known entities, verify correct Neo4j nodes and relationships created

---

## M8 — GraphRAG Engine (Hybrid Retrieval Pipeline, Stages 1–6)

**Phase**: Phase 2
**Difficulty**: Very Hard
**Depends on**: M4, M7
**Blocks**: M9, M10, M11, M12, M13

### Objective
Implement Stages 1–6 of the 8-stage hybrid retrieval pipeline from the architecture (§4): BM25 keyword match, metadata filtering, dense vector search, KG graph traversal, GraphRAG synthesis, and cross-encoder reranking. Replace the M5 simple vector lookup with this full pipeline in the `/chat` endpoint.

### Deliverables
- `GraphRAGEngine` service coordinating all six retrieval stages in parallel where possible
- Neo4j Cypher traversal extracting entity subgraphs with depth limit ≤ 2 (ADR-004 mitigation)
- Cross-encoder reranker: `BAAI/bge-reranker-large` scoring merged candidates
- `HybridSearchResult` DTO combining vector chunks + graph paths into ranked, deduplicated context
- `/chat` endpoint upgraded to use `GraphRAGEngine` transparently
- P50 latency for GraphRAG synthesis < 3000ms (NFR-03 from architecture spec)

### Checklist
- [ ] `GraphRAGEngineInterface` defined in `domain/` (ADR-013 — domain-agnostic interface)
- [ ] Stage 1 (BM25): query against `bm25_index` in PostgreSQL; return top-20 chunk candidates
- [ ] Stage 2 (Metadata Filter): filter all candidates by `role_scope` matching current user permissions before further processing
- [ ] Stage 3 (Dense Vector): Qdrant query with `role_scope` filter payload; return top-20 candidates with scores
- [ ] Stage 4 (KG Traversal): extract entity tags from query using spaCy; execute `MATCH (n {tag_number: $tag})-[*1..2]-(neighbor) RETURN n, neighbor LIMIT 50`
- [ ] Stage 4: max depth hardcoded to 2; APOC procedures used for traversal (ADR-004)
- [ ] Stage 5 (GraphRAG Synthesis): merge BM25 + vector candidates + KG subgraph paths into single candidate list; deduplicate by `chunk_id`
- [ ] Stage 5: KG paths formatted as Markdown table before inclusion in context (Engineering Bible §20)
- [ ] Stage 6 (Cross-Encoder Reranking): batch all merged candidates through `bge-reranker-large`; re-score and sort descending
- [ ] Cross-encoder inference in thread pool (no blocking event loop)
- [ ] `HybridSearchResult` fields: `ranked_chunks[]`, `kg_paths[]`, `entity_mentions[]`, `total_candidates_before_rerank`, `rerank_latency_ms`
- [ ] Stage 1–3 executed in parallel (`asyncio.gather`); Stage 4 runs concurrently; Stage 5–6 sequential
- [ ] Token budget enforced after reranking: discard chunks beyond 6000 token context budget
- [ ] Redis cache: cache GraphRAG results keyed by `hash(query + role_scope)` with 5-minute TTL (Engineering Bible §27)
- [ ] Unfiltered subgraphs never sent directly to LLM context — always formatted (Engineering Bible §20)
- [ ] `/chat` endpoint updated to call `GraphRAGEngine` instead of direct vector search
- [ ] Performance test: 10 sequential queries on 1000-chunk corpus; p50 < 3000ms, p95 < 6000ms
- [ ] Unit tests: each stage independently testable with mock inputs/outputs
- [ ] Integration test: query "What sensors monitor pump P-102A?" — verify KG path `Sensor→MONITORS→Equipment` appears in result

---

## M9 — Knowledge Brain Agent (LangGraph)

**Phase**: Phase 2
**Difficulty**: Hard
**Depends on**: M8, M5
**Blocks**: M10, M11, M12, M13

### Objective
Build the first of five sub-brains using LangGraph: the **Knowledge Brain**, which handles document search, navigation, and general operational Q&A. This establishes the agent state machine pattern all subsequent brains will reuse.

### Deliverables
- `KnowledgeBrainAgent` LangGraph state machine with defined nodes: `route_query`, `retrieve_context`, `synthesize_answer`, `validate_citations`, `format_response`
- Agent tool registry: `semantic_search`, `graph_search`, `document_lookup`, `entity_lookup`
- Prompt templates for all agent nodes in `ai/prompts/knowledge_brain/`
- Maximum step limit: 10 steps per query (Engineering Bible §21)
- Fallback handler: if any tool fails, agent returns partial answer with explicit uncertainty flag
- `/api/v1/brain/knowledge/chat` endpoint routing to this agent

### Checklist
- [ ] `AgentState` TypedDict defined with: `query`, `session_id`, `user_role`, `retrieved_chunks`, `kg_paths`, `draft_answer`, `citations`, `step_count`, `error_flag`
- [ ] LangGraph `StateGraph` compiled with nodes: `route_query → retrieve_context → synthesize_answer → validate_citations → format_response`
- [ ] `route_query` node: classifies query as `document_search | entity_lookup | procedural | unknown`; unknown routes to `synthesize_answer` with explicit uncertainty
- [ ] `retrieve_context` node: calls `GraphRAGEngine` (M8); populates `retrieved_chunks` and `kg_paths` in state
- [ ] `synthesize_answer` node: calls `ModelGateway` (M5) with assembled context; draft stored in state
- [ ] `validate_citations` node: verifies each citation in draft maps to a real chunk_id in `retrieved_chunks`; removes hallucinated citations
- [ ] `format_response` node: renders final markdown with validated citations
- [ ] Step counter incremented at each node; graph exits with `STEP_LIMIT_EXCEEDED` error if > 10 steps (Engineering Bible §21)
- [ ] Fallback: any tool exception sets `error_flag = True`; agent routes to `format_response` with partial answer
- [ ] All agent tool definitions in `ai/agents/knowledge_brain/tools.py` — separate from state machine definition
- [ ] All prompt templates in `ai/prompts/knowledge_brain/*.yaml` — not hardcoded (ADR-020)
- [ ] Agent execution steps logged with step number, node name, duration, and Correlation-ID (Engineering Bible §16)
- [ ] `/api/v1/brain/knowledge/chat` validates user auth and RBAC before passing to agent
- [ ] Unit tests: each LangGraph node independently; state transitions; step limit enforcement; fallback handler
- [ ] Integration test: multi-turn conversation; verify state accumulates across turns via Redis session

---

---

# PHASE 3
> **Goal**: All five sub-brains operational, full 8-stage pipeline complete, event-driven ingestion, evaluation layer active.

---

## M10 — Maintenance Brain Agent

**Phase**: Phase 3
**Difficulty**: Hard
**Depends on**: M9
**Blocks**: None

### Objective
Specialized LangGraph agent for maintenance operations: work order assistance, preventative maintenance scheduling guidance, and asset failure history queries. Reuses the Knowledge Brain pattern with maintenance-specific tools and prompts.

### Deliverables
- `MaintenanceBrainAgent` LangGraph state machine
- Tools: `work_order_lookup`, `maintenance_schedule_query`, `failure_history_search`, `oem_manual_lookup`
- Mock CMMS data loader for demo purposes (CSV → PostgreSQL `work_orders` table)
- `/api/v1/brain/maintenance/chat` endpoint

### Checklist
- [ ] `work_orders` table in PostgreSQL: `wo_id`, `asset_tag`, `description`, `status`, `priority`, `scheduled_date`, `completed_date`
- [ ] Mock CMMS CSV loaded via `scripts/load_mock_cmms.py` into `work_orders` table
- [ ] `work_order_lookup` tool: queries PostgreSQL by asset_tag or work order ID
- [ ] `failure_history_search` tool: queries Neo4j for `(Equipment)-[:EXHIBITS]->(FailureMode)` paths filtered by asset tag
- [ ] `oem_manual_lookup` tool: calls GraphRAG with document_category filter = "OEM Manual"
- [ ] `maintenance_schedule_query` tool: returns open work orders for an asset sorted by scheduled_date
- [ ] LangGraph nodes: `classify_maintenance_query → retrieve_asset_context → retrieve_work_orders → synthesize_guidance → format_response`
- [ ] Prompt templates in `ai/prompts/maintenance_brain/*.yaml`
- [ ] Step limit: 10; fallback handler inherited from Knowledge Brain pattern
- [ ] Agent logs include asset_tag extracted from query for audit trail
- [ ] Unit tests: each tool independently; state machine transitions
- [ ] Demo test: "Show me all open work orders for pump P-102A and the relevant maintenance procedure"

---

## M11 — Compliance Brain Agent

**Phase**: Phase 3
**Difficulty**: Hard
**Depends on**: M9
**Blocks**: None

### Objective
Agentic system that maps regulatory requirements against current procedures and equipment states, identifies compliance gaps, and generates evidence summaries for audits per the problem statement evaluation criteria.

### Deliverables
- `ComplianceBrainAgent` LangGraph state machine
- Regulatory document ingestion tag: `document_category = "Regulation"` used to filter retrieval
- Compliance gap detection workflow: compare procedure text against regulatory requirements
- `compliance_gap_report` structured output schema
- `/api/v1/brain/compliance/chat` endpoint

### Checklist
- [ ] Regulatory documents ingested with `document_category = "Regulation"` metadata tag
- [ ] `regulation_lookup` tool: GraphRAG search filtered to `document_category = "Regulation"` chunks only
- [ ] `procedure_lookup` tool: GraphRAG search filtered to `document_category = "SOP"` chunks only
- [ ] `compliance_gap_detector` tool: sends regulation text + procedure text to LLM with structured gap detection prompt; returns `{gaps: [{regulation_clause, procedure_gap, severity}]}`
- [ ] Gap severity levels: `CRITICAL | MAJOR | MINOR` — mapped from regulation language
- [ ] LangGraph nodes: `identify_regulation_scope → retrieve_procedures → detect_gaps → generate_evidence → format_report`
- [ ] `ComplianceGapReport` output schema enforced via Pydantic — not free-text (Engineering Bible §33)
- [ ] Report stored in PostgreSQL `compliance_reports` table for audit trail
- [ ] Prompt templates in `ai/prompts/compliance_brain/*.yaml`
- [ ] Unit tests: gap detector with mock regulation/procedure pairs; severity classification
- [ ] Demo test: "Check if our valve inspection procedure complies with OSHA 1910.119"

---

## M12 — RCA Brain Agent

**Phase**: Phase 3
**Difficulty**: Very Hard
**Depends on**: M9
**Blocks**: None

### Objective
Guides reliability engineers through structured Root Cause Analysis using 5-Whys and Fishbone (Ishikawa) workflows implemented as LangGraph state machines. Uses failure history from Neo4j and maintenance history from PostgreSQL as evidence.

### Deliverables
- `RCABrainAgent` LangGraph state machine with human-in-the-loop pause states
- 5-Whys workflow: iterative cause traversal with LLM-suggested next why
- Fishbone structured output: categories (Equipment, Method, Material, Man, Environment, Measurement)
- `RCAReport` output schema stored in PostgreSQL
- `/api/v1/brain/rca/session` endpoint (session-based, multi-turn)

### Checklist
- [ ] LangGraph `interrupt_before` configured at human-in-the-loop nodes (LangGraph built-in pause feature per ADR-007)
- [ ] `rca_session` table in PostgreSQL: `session_id`, `asset_tag`, `incident_description`, `status`, `rca_report_json`, `created_at`
- [ ] 5-Whys workflow nodes: `define_problem → suggest_why_1 → [human_confirm] → suggest_why_2 → ... → identify_root_cause → generate_report`
- [ ] At each `suggest_why_N` node: LLM queries Neo4j for `FailureMode` patterns on the affected asset before suggesting
- [ ] Fishbone workflow: parallel branches per Ishikawa category; each branch queries relevant document chunks
- [ ] `failure_pattern_search` tool: Cypher query `MATCH (e:Equipment {tag_number: $tag})-[:EXHIBITS]->(f:FailureMode) RETURN f.failure_code, f.effect_severity`
- [ ] `incident_history_search` tool: queries historical work orders for similar failure descriptions
- [ ] `RCAReport` Pydantic schema: `{problem_statement, root_cause, contributing_factors[], recommended_actions[], evidence_citations[]}`
- [ ] Report citations validated: every `evidence_citation` maps to real `chunk_id` or Neo4j node ID
- [ ] Session state persisted in LangGraph checkpoint store (Redis-backed) enabling resume after human input
- [ ] Prompt templates in `ai/prompts/rca_brain/*.yaml`
- [ ] Unit tests: 5-Whys iteration logic; Fishbone branch merge; human interrupt/resume
- [ ] Demo test: initiate RCA for "pump P-102A bearing failure" — complete full 5-Whys and generate report

---

## M13 — Lessons Learned Brain Agent

**Phase**: Phase 3
**Difficulty**: Hard
**Depends on**: M9
**Blocks**: None

### Objective
Captures post-incident logs and patterns, surfaces relevant historical warnings when similar conditions are detected during active queries. Enables the knowledge cliff mitigation from the problem statement.

### Deliverables
- `LessonsLearnedBrainAgent` LangGraph state machine
- Incident ingestion endpoint: `POST /api/v1/incidents` with `LessonLearned` entity creation in Neo4j
- Pattern detection: similarity search on new queries against historical incident embeddings
- Proactive warning injection: if similarity > 0.85, prepend warning to Knowledge Brain responses
- `/api/v1/brain/lessons/chat` endpoint

### Checklist
- [ ] `LessonLearned` Neo4j node type added to ontology YAML (M6 schema extended)
- [ ] `(LessonLearned)-[:RELATED_TO]->(Equipment)` and `(LessonLearned)-[:REFERENCES]->(FailureMode)` relationships defined
- [ ] `POST /api/v1/incidents` ingests: `{asset_tag, incident_date, description, root_cause, corrective_actions[], severity}`
- [ ] Incident description embedded and upserted to Qdrant collection `lessons_learned` (separate collection)
- [ ] `POST /api/v1/incidents` creates `LessonLearned` node in Neo4j with RELATED_TO and REFERENCES edges
- [ ] `proactive_warning_detector` service: on every `/chat` query, checks `lessons_learned` Qdrant collection for similarity > 0.85
- [ ] If warning detected: structured `{warning_type: "LESSONS_LEARNED", lesson_summary, similarity_score, incident_date}` prepended to response
- [ ] LangGraph nodes: `analyze_incident → extract_patterns → link_to_ontology → store_lesson → generate_summary`
- [ ] Prompt templates in `ai/prompts/lessons_brain/*.yaml`
- [ ] Unit tests: incident ingestion, similarity detection, warning injection logic
- [ ] Demo test: ingest a bearing failure incident, then query about pump P-102A — verify warning appears

---

## M14 — Full 8-Stage Pipeline (Stages 7–8: Compression & Citation Validation)

**Phase**: Phase 3
**Difficulty**: Hard
**Depends on**: M8
**Blocks**: None (enhances existing pipeline)

### Objective
Complete the retrieval pipeline by adding Stage 7 (LLMLingua context compression) and Stage 8 (citation validation with absolute source coordinates). Updates the `GraphRAGEngine` from M8 in place.

### Deliverables
- LLMLingua integration compressing reranked context before LLM call
- Token savings target: ≥ 30% context compression without faithfulness degradation
- Stage 8 citation validator: every cited chunk mapped to `(document_id, page_number, bbox_json)` absolute coordinates
- `CitationValidationReport` appended to every `/chat` response

### Checklist
- [ ] `llmlingua` library integrated as Stage 7 in `GraphRAGEngine`
- [ ] Compression ratio logged per request: `{original_tokens, compressed_tokens, ratio}` (Engineering Bible §17)
- [ ] LLMLingua target ratio: 0.7 (compress to 70% of input size); configurable via env
- [ ] Compression skipped if context is already under 2000 tokens (avoid over-compression on small results)
- [ ] Stage 8: parse LLM response for citation markers `[source_N]`; resolve each to chunk record in PostgreSQL
- [ ] If cited `source_N` does not match any chunk in `retrieved_chunks[]`, citation removed and `hallucinated_citation_count` incremented
- [ ] `hallucinated_citation_count > 0` sets `response_quality_flag = "CITATION_WARNING"` in API response
- [ ] `CitationValidationReport` returned in response: `{validated_count, hallucinated_count, quality_flag}`
- [ ] Compression and citation stats logged as structured JSON per request (Engineering Bible §16)
- [ ] Unit tests: LLMLingua wrapper, citation resolver, hallucinated citation detection

---

## M15 — Event-Driven Ingestion Pipeline (Celery + Redis)

**Phase**: Phase 3
**Difficulty**: Medium
**Depends on**: M3, M4, M7
**Blocks**: None (replaces synchronous ingestion)

### Objective
Replace the synchronous document processing chain (M2→M3→M4→M7) with Celery async task workers. Each pipeline stage becomes a discrete Celery task with automatic retry. Web API returns immediately with a job ID per ADR-015.

### Deliverables
- Celery app configured with Redis broker and result backend
- Celery task chain: `extract_task → parse_task → embed_task → kg_task`
- `POST /api/v1/documents/upload` returns `{job_id}` instantly; processing is fully async
- `GET /api/v1/jobs/{job_id}` polling endpoint returning state + progress
- Worker Dockerfile added to docker-compose.yml as `ib_worker` service

### Checklist
- [ ] `celery` and `kombu` added to `requirements.txt` with pinned versions
- [ ] Celery app configured: broker=Redis, backend=Redis, task serializer=json
- [ ] `extract_task(document_id)` → calls PyMuPDF extraction (M2 logic); chains to `parse_task`
- [ ] `parse_task(document_id)` → calls layout parser + OCR (M3 logic); chains to `embed_task`
- [ ] `embed_task(document_id)` → calls embedding + Qdrant upsert (M4 logic); chains to `kg_task`
- [ ] `kg_task(document_id)` → calls NER + relation extraction + Neo4j population (M7 logic)
- [ ] Each task: max 3 retries, exponential backoff 60s→120s→240s (Engineering Bible §23)
- [ ] Each task updates `jobs.status` in PostgreSQL at start and completion
- [ ] Failed task: sets `jobs.status = FAILED`, writes `jobs.error_details` JSON with task name + exception message
- [ ] `POST /api/v1/documents/upload` no longer waits for processing; returns `{document_id, job_id, status: "PENDING"}` in < 200ms
- [ ] `ib_worker` service in docker-compose.yml: same image as backend, entrypoint `celery -A app.worker worker --loglevel=info`
- [ ] Worker concurrency: 2 per container (configurable via `CELERY_WORKER_CONCURRENCY` env)
- [ ] Celery task logs include Correlation-ID propagated from the original upload request
- [ ] Session state never stored in worker memory — all state in PostgreSQL/Redis (Engineering Bible §28)
- [ ] Unit tests: task retry logic, job status transitions, Correlation-ID propagation
- [ ] Integration test: upload file, verify all four tasks complete, verify Qdrant and Neo4j populated

---

## M16 — Evaluation Layer

**Phase**: Phase 3
**Difficulty**: Hard
**Depends on**: M8, M9
**Blocks**: Final Demo

### Objective
Implement the Dedicated Evaluation Layer from the architecture (§5): automated RAG metrics (retrieval recall, context precision, faithfulness, hallucination detection) run against a golden dataset. Results exposed on a metrics endpoint and logged to Prometheus.

### Deliverables
- `datasets/golden_qa.json`: 20+ question-answer pairs with known source citations (industrial domain)
- Evaluation runner: batch mode scoring against golden dataset
- Metrics: Retrieval Recall@10, Context Precision, Faithfulness (LLM-as-a-judge), Hallucination Rate
- `GET /api/v1/eval/report` endpoint returning latest evaluation run results
- Prometheus counters for real-time hallucination rate and citation accuracy

### Checklist
- [ ] `datasets/golden_qa.json` format: `[{question, expected_answer, source_document_id, source_page, expected_entity_mentions[]}]`
- [ ] Minimum 20 QA pairs covering: equipment lookup, procedure query, failure mode query, multi-hop entity relationship query
- [ ] `EvaluationRunner` service: iterates golden dataset, runs each question through `GraphRAGEngine` + LLM
- [ ] Retrieval Recall@10: % of golden source chunks appearing in top-10 retrieved results
- [ ] Context Precision: % of retrieved chunks that are relevant (judged by LLM against expected_answer)
- [ ] Faithfulness: LLM-as-a-judge prompt checks if answer is derivable from retrieved context only — not from LLM prior knowledge
- [ ] Hallucination Rate: count of responses where `CitationValidationReport.hallucinated_count > 0` / total responses
- [ ] Evaluation run results stored in PostgreSQL `evaluation_runs` table with timestamp and metric scores
- [ ] `GET /api/v1/eval/report` returns latest run: `{run_date, retrieval_recall, context_precision, faithfulness, hallucination_rate}`
- [ ] Prometheus gauge metrics: `ib_hallucination_rate`, `ib_faithfulness_score`, `ib_retrieval_recall`
- [ ] Evaluation prompt templates in `ai/prompts/evaluation/*.yaml` (not hardcoded — ADR-020)
- [ ] `make eval` command runs full evaluation suite and prints report
- [ ] CI step: run evaluation on every PR merge to `main`; fail if hallucination_rate > 0.15
- [ ] Unit tests: metric calculation functions with known inputs/outputs
- [ ] Baseline evaluation run committed to `docs/eval_baseline.json`

---

---

# FINAL DEMO PHASE
> **Goal**: Production-quality observable system. All five brains operational. UI polished for judging. Demo dataset loaded. Metrics dashboards live.

---

## M17 — Observability Stack (OpenTelemetry + Prometheus + Grafana)

**Phase**: Final Demo
**Difficulty**: Medium
**Depends on**: M5
**Blocks**: None

### Objective
Instrument all services with OpenTelemetry spans per ADR-016. Deploy Prometheus for metrics collection and Grafana dashboards per ADR-017. Every agent step, database query, and LLM call captured as a traceable span.

### Deliverables
- OpenTelemetry SDK instrumented across FastAPI, Neo4j driver, Qdrant client, Celery tasks
- Jaeger container added to docker-compose.yml
- Prometheus + Grafana containers added to docker-compose.yml
- Grafana dashboard: API latency P50/P95/P99, error rates, token usage, queue depth
- Grafana dashboard: RAG quality metrics from M16 evaluation layer
- Correlation-ID propagated as OTel trace ID across all service boundaries

### Checklist
- [ ] `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy` added to requirements
- [ ] OTel tracer initialized at FastAPI startup; exports to Jaeger via OTLP
- [ ] Every LLM call wrapped in OTel span: attributes `llm.model`, `llm.prompt_tokens`, `llm.completion_tokens`, `llm.latency_ms`
- [ ] Every Qdrant query wrapped in OTel span: attributes `vector_db.collection`, `vector_db.top_k`, `vector_db.latency_ms`
- [ ] Every Neo4j query wrapped in OTel span: attributes `graph_db.query_type`, `graph_db.depth`, `graph_db.result_count`
- [ ] Every Celery task wrapped in OTel span; trace context propagated from upload request through all task steps
- [ ] Correlation-ID == OTel trace ID; injected into all structured log entries (Engineering Bible §16)
- [ ] `jaeger` service in docker-compose.yml: `jaegertracing/all-in-one:1.57`, ports 16686 (UI), 4317 (OTLP)
- [ ] `prometheus` service in docker-compose.yml: scrapes FastAPI `/metrics` endpoint, Celery worker metrics
- [ ] `grafana` service in docker-compose.yml: pre-configured datasources for Prometheus and Jaeger
- [ ] Grafana dashboard JSON committed to `monitoring/grafana/dashboards/`
- [ ] Dashboard panels: API request rate, p50/p95 latency, LLM token usage per hour, Celery queue depth, active WebSocket connections
- [ ] Dashboard panels: hallucination rate trend, faithfulness score trend (from M16 Prometheus gauges)
- [ ] No sensitive data (tokens, passwords, user queries) logged as OTel span attributes (Engineering Bible §16)
- [ ] `docker compose up` brings all monitoring services up with no additional configuration
- [ ] Smoke test: make one `/chat` request, verify trace appears in Jaeger UI

---

## M18 — PromptOps Finalization

**Phase**: Final Demo
**Difficulty**: Easy
**Depends on**: M9, M10, M11, M12, M13
**Blocks**: None

### Objective
Audit all agent and system prompts across all five brains. Ensure every prompt is in a version-controlled YAML/JSON file with schema validation. No hardcoded prompt strings anywhere in Python code per ADR-020.

### Deliverables
- All prompts under `ai/prompts/` in YAML format with standardized schema
- `PromptLoader` service that loads, validates, and injects variables into templates
- CI lint step: grep for hardcoded prompt strings; fail build if found
- Prompt schema: `{prompt_id, version, description, system_template, user_template, output_format}`

### Checklist
- [ ] Audit: grep codebase for f-string or multiline string prompt patterns in `.py` files — resolve all findings
- [ ] `PromptLoader` service: reads YAML from `ai/prompts/`, validates against JSON Schema, supports variable injection via `{variable}` syntax
- [ ] `PromptLoader` raises `PromptValidationError` on missing required variables — no silent failures (Engineering Bible §1)
- [ ] Prompt YAML schema fields: `prompt_id` (unique), `version` (semver), `description`, `system_template`, `user_template`, `output_format`
- [ ] All prompts inventoried in `ai/prompts/MANIFEST.yaml` with prompt_id, version, owning brain
- [ ] CI step: `python scripts/validate_prompts.py` — fails if any prompt YAML fails schema or variable injection test
- [ ] CI step: `grep -rn "system_prompt\s*=\s*[\"']" backend/app/` — fails if hardcoded prompts found
- [ ] Prompt version bump required for any prompt change (enforced by schema: version must be higher than prior)
- [ ] Unit tests: `PromptLoader` with valid template, missing variable, invalid schema

---

## M19 — UI Polish, Knowledge Graph Visualizer & Demo Dataset

**Phase**: Final Demo
**Difficulty**: Medium
**Depends on**: M8, M9
**Blocks**: None

### Objective
Polish the React frontend for judging. Add a Knowledge Graph visualizer. Load the full industrial demo dataset. Ensure responsive layout works on mobile for field technicians per ADR-002 and the problem statement.

### Deliverables
- Interactive Knowledge Graph visualization using Cytoscape.js
- Document viewer with page rendering and highlighted citation bounding boxes
- Multi-brain selector UI: tabs/sidebar switching between Knowledge, Maintenance, Compliance, RCA, Lessons Learned
- Demo dataset: 10+ realistic industrial PDF documents loaded and fully indexed
- Mobile-responsive layout verified on 375px viewport

### Checklist
- [ ] `cytoscape` npm package added; `KnowledgeGraphView` component renders Neo4j subgraph as interactive node-edge diagram
- [ ] `KnowledgeGraphView`: node color-coded by ontology type (Asset=blue, Equipment=green, Sensor=yellow, FailureMode=red)
- [ ] `KnowledgeGraphView`: clicking a node loads entity details panel with properties and related chunks
- [ ] `GET /api/v1/graph/subgraph?entity_tag=&depth=1` endpoint returning Cytoscape-compatible JSON
- [ ] `DocumentViewer` component: renders PDF pages using `react-pdf`; overlays citation bounding boxes as colored highlights
- [ ] Citation highlight color: gold for vector-matched, blue for KG-traversal matched
- [ ] Multi-brain sidebar: icons + labels for Knowledge Brain, Maintenance Brain, Compliance Brain, RCA Brain, Lessons Learned Brain
- [ ] Brain selector persists in URL (`/brain/knowledge`, `/brain/maintenance`, etc.) — React Router routes defined
- [ ] Demo dataset: minimum 10 PDF documents covering: 2 OEM manuals, 2 SOPs, 2 inspection reports, 2 P&ID descriptions, 1 regulatory excerpt, 1 maintenance log
- [ ] Demo dataset loaded via `make demo-data` command; script documented in README
- [ ] All demo documents fully indexed (M2→M3→M4→M7 pipeline complete) before demo
- [ ] Mobile layout: chat interface usable at 375px; document upload works on mobile
- [ ] Accessibility: all interactive elements keyboard-navigable; contrast ratio ≥ 4.5:1 (WCAG 2.1 AA — Engineering Bible §39)
- [ ] Build completes without TypeScript errors: `tsc --noEmit` passes
- [ ] No `any` types in frontend TypeScript (Engineering Bible §8)
- [ ] Manual UI walkthrough: upload → index → chat → view citation → view KG — all flows work without console errors

---

## M20 — Performance Hardening, Security Audit & Final Validation

**Phase**: Final Demo
**Difficulty**: Medium
**Depends on**: All prior milestones
**Blocks**: None (final milestone)

### Objective
Final pre-submission hardening pass: latency targets verified against NFRs, security scan clean, all Engineering Bible checklists complete, `docker compose up` reproducible from clean state in under 3 minutes.

### Deliverables
- `bandit` and `pip-audit` scans passing with zero high-severity findings
- Latency validation: P50 semantic search < 500ms, P50 GraphRAG < 3000ms (NFR-03)
- Final `docker compose up` from scratch verified on clean machine
- Engineering Bible compliance checklist completed and committed

### Checklist
- [ ] `bandit -r backend/app/ -ll` exits 0 (no medium or high severity issues — Engineering Bible §14)
- [ ] `pip-audit` exits 0 (no known vulnerabilities in pinned dependencies — Engineering Bible §40)
- [ ] `npm audit --audit-level=high` exits 0 for frontend dependencies
- [ ] All environment secrets read from `.env` file; `.env` in `.gitignore`; no secrets in committed code (Engineering Bible §14)
- [ ] Latency test: 50 sequential `/api/v1/search/semantic` requests on demo dataset; assert p50 < 500ms
- [ ] Latency test: 20 sequential `/api/v1/chat` requests through full GraphRAG pipeline; assert p50 < 3000ms
- [ ] Database query plans reviewed: `EXPLAIN ANALYZE` on top-5 most frequent PostgreSQL queries; all using index scans
- [ ] Neo4j query review: all Cypher queries have `LIMIT` clause; no unconstrained full-graph scans (Engineering Bible §36)
- [ ] Connection pooling configured: SQLAlchemy pool_size=10, max_overflow=20
- [ ] `docker compose down -v && docker compose up` completes and all health checks pass in < 3 minutes
- [ ] All `domain/` Python modules: zero imports from `infrastructure/`, `presentation/`, or FastAPI (ADR-013)
- [ ] Cyclomatic complexity audit: `radon cc backend/app/ -a` — average < 5, no function > 10 (Engineering Bible §1)
- [ ] All public API routes have OpenAPI descriptions: `openapi.json` generated and committed to `docs/api/`
- [ ] Test coverage: `pytest --cov=backend/app --cov-report=term` ≥ 80% (Engineering Bible §26)
- [ ] README `Quick Start` section verified: `git clone → docker compose up → open browser` works without extra steps
- [ ] Engineering Bible compliance self-assessment completed and committed to `docs/bible_compliance.md`

---

---

## Milestone Dependency Map

```
Baseline ──► M1 ──► M2 ──► M3 ──► M4 ──► M5 (MVP DEMO ✦)
              │                    │
              └──► M6 ──► M7 ──► M8 ──► M9 ──► M10
                                   │      │      M11
                                   │      │      M12
                                   │      │      M13
                                   └──► M14
              M2+M3+M4+M7 ──────────────────► M15
              M8+M9 ──────────────────────────► M16
              M5 ───────────────────────────────► M17
              M9–M13 ──────────────────────────► M18
              M8+M9 ──────────────────────────► M19
              ALL ─────────────────────────────► M20 (FINAL DEMO ✦)
```

---

## Difficulty & Effort Summary

| Milestone | Title | Phase | Difficulty | Key Risk |
| :-------- | :---- | :---- | :--------- | :------- |
| M1 | Infrastructure Validation | MVP | Easy | Service startup ordering |
| M2 | Document Ingestion Pipeline | MVP | Medium | MinIO streaming, file validation |
| M3 | OCR & Layout-Aware Parsing | MVP | Hard | Layout detection accuracy on legacy PDFs |
| M4 | Embedding Pipeline & Qdrant | MVP | Medium | Embedding model cold-start latency |
| M5 | Basic Chat API & Copilot UI | MVP | Medium | WebSocket stability, streaming citation render |
| M6 | Industrial Ontology & Neo4j | Phase 2 | Medium | Schema completeness vs. flexibility trade-off |
| M7 | Entity & Relation Extraction | Phase 2 | Very Hard | NER accuracy, entity resolution false-positives |
| M8 | GraphRAG Engine | Phase 2 | Very Hard | Multi-stage latency, RBAC filter correctness |
| M9 | Knowledge Brain Agent | Phase 2 | Hard | LangGraph state management, hallucinated citation removal |
| M10 | Maintenance Brain Agent | Phase 3 | Hard | CMMS mock data quality, tool disambiguation |
| M11 | Compliance Brain Agent | Phase 3 | Hard | Regulatory language parsing, gap severity calibration |
| M12 | RCA Brain Agent | Phase 3 | Very Hard | Human-in-the-loop LangGraph persistence |
| M13 | Lessons Learned Brain | Phase 3 | Hard | Similarity threshold tuning, proactive injection UX |
| M14 | Full 8-Stage Pipeline | Phase 3 | Hard | LLMLingua compression faithfulness degradation |
| M15 | Event-Driven Pipeline | Phase 3 | Medium | Celery worker isolation, retry idempotency |
| M16 | Evaluation Layer | Phase 3 | Hard | Golden dataset construction, LLM-as-a-judge calibration |
| M17 | Observability Stack | Final Demo | Medium | OTel span volume, Grafana dashboard config |
| M18 | PromptOps Finalization | Final Demo | Easy | Full audit coverage, CI enforcement |
| M19 | UI Polish & Demo Dataset | Final Demo | Medium | Cytoscape performance on large graphs |
| M20 | Performance & Security Hardening | Final Demo | Medium | Latency regression from full pipeline |

---

*Roadmap version: 1.0 | Created: 2026-06-29 | Governed by: Engineering Bible v1.0 & ADRs 001–020*
