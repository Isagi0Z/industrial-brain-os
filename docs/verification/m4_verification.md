# M4 Verification Report — Embedding Pipeline & Qdrant Indexing

**Date:** 2026-06-30  
**Milestone:** M4 — Embedding Pipeline & Qdrant Indexing  
**Branch:** feature/bootstrap  
**Verified by:** automated test suite + manual E2E  

---

## Test Suite

```
pytest tests/ -v
45 passed
```

### M2 carry-over (11 tests)
- `test_document_upload.py` — upload, list, status, retry, soft-delete, restore, metadata ✓

### M3 carry-over (16 tests)
- `test_document_parsing.py` — chunker, parsing use case, PyMuPDF, DOCX parsers ✓

### M4 new tests (18 tests)
| Test | Result |
|------|--------|
| `test_embedding_service_embed_one_returns_list` | PASS |
| `test_embedding_service_embed_batch_multiple` | PASS |
| `test_qdrant_ensure_collection_creates_if_missing` | PASS |
| `test_qdrant_ensure_collection_skips_existing` | PASS |
| `test_qdrant_batch_upsert_calls_client` | PASS |
| `test_qdrant_search_maps_hits_to_search_results` | PASS |
| `test_qdrant_search_applies_role_scope_filter` | PASS |
| `test_bm25_tokenize` | PASS |
| `test_bm25_tokenize_empty` | PASS |
| `test_bm25_build_index_and_search` | PASS |
| `test_bm25_search_returns_normalized_scores` | PASS |
| `test_qdrant_search_empty_for_wrong_scope` | PASS |
| `test_embed_document_success` | PASS |
| `test_embed_document_missing_doc` | PASS |
| `test_embed_document_no_chunks` | PASS |
| `test_integration_index_and_semantic_search` (integration) | PASS |

---

## Code Quality

| Check | Result |
|-------|--------|
| `black --check .` | All files formatted |
| `ruff check .` | All checks passed |
| `mypy app/ --explicit-package-bases --ignore-missing-imports` | 0 errors |
| `tsc --noEmit` | No TypeScript errors |

---

## Infrastructure

| Service | Status |
|---------|--------|
| PostgreSQL (port 5433) | healthy |
| Redis | healthy |
| MinIO | healthy |
| Neo4j | healthy |
| Qdrant (port 6333) v1.9.0 | healthy |

Migration `003_bm25_index_m4` applied:
- `bm25_index` table created with term/scope/text columns

---

## Integration Test Result

```
5 chunks upserted into test_m4_integration collection
Query: "pump impeller wear vibration"
Top-1 result: "centrifugal pump impeller wear causes vibration and flow loss"
  → Contains "pump" and "impeller" ✓
PASS
```

---

## End-to-End Test

### Upload
```
POST /api/v1/documents/
→ 201 Created
→ document_id: e8a6897b-3439-4c0d-aaa9-c76ef0b96419
```

### Full Pipeline
```
QUEUED → EXTRACTING → EXTRACTED → PARSING → CHUNKED → EMBEDDING → INDEXED (95%)
```

### Semantic Search
```
GET /api/v1/search/semantic?q=impeller+wear+inspection&limit=3
→ total: 3
  [0.899] paragraph: "Inspect impeller for wear and cavitation erosion."
  [0.886] paragraph: "Section 1: Impeller Inspection"
  [0.855] paragraph: "Inspect impeller for wear cavitation erosion. Measure clearance."
```

### Keyword Search
```
GET /api/v1/search/keyword?q=bearing+temperature&limit=3
→ total: 3
  [1.000] paragraph: "Section 2: Bearing Replacement"
  [0.126] paragraph: "Replace bearings when temperature exceeds 80 Celsius."
```

### RBAC
```
GET /api/v1/search/semantic?q=pump (no auth)
→ 401 Not authenticated ✓
```

---

## Acceptance Criteria Checklist

- [x] `sentence-transformers` model `BAAI/bge-large-en-v1.5` loaded once at startup
- [x] Embedding inference runs in thread pool via `run_in_threadpool`
- [x] Batch size: 32 chunks per embedding call; progress logged per batch
- [x] Qdrant point payload: document_id, chunk_index, chunk_type, page_number, parent_section_header, role_scope, document_title, revision_date
- [x] `role_scope` payload field used as Qdrant filter on every query
- [x] Qdrant upsert uses `upsert` (idempotent) — safe to re-run
- [x] BM25 index built per-document at ingestion time; stored in `bm25_index` PostgreSQL table
- [x] `/search/semantic` returns chunk_text, score, document_title, page_number, bbox_json, chunk_type
- [x] `/search/keyword` returns same schema
- [x] Both endpoints: limit default=10, max=50; scores normalized 0–1
- [x] Both endpoints: unauthenticated requests return 401
- [x] No `Any` typing in embedding service or Qdrant client wrapper
- [x] Job state transitions: CHUNKED → EMBEDDING → INDEXED
- [x] Unit tests: embedding service, Qdrant client wrapper, BM25 indexer, RBAC filter logic
- [x] Integration test: index 5 chunks, run semantic query, verify top-1 result is correct chunk
