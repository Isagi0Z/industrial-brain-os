# M4 Walkthrough — Embedding Pipeline & Qdrant Indexing

## Overview

M4 completes the ingestion pipeline from M2/M3 by embedding `DocumentChunk` text into dense 1024-dim vectors (BAAI/bge-large-en-v1.5) and indexing them in Qdrant. It also builds a BM25 keyword index in PostgreSQL. Both indexes are queryable via authenticated REST endpoints.

---

## Architecture

```
IngestionWorker (M3+M4 daemon)
    ├─ DocumentParsingUseCase.parse_document()   → CHUNKED
    └─ EmbeddingUseCase.embed_document()         → INDEXED
            ├─ SentenceTransformerEmbedder       (BAAI/bge-large-en-v1.5, 1024-dim)
            ├─ QdrantVectorRepository            → Qdrant collection 'document_chunks'
            └─ PostgresBM25Repository            → PostgreSQL bm25_index table

GET /api/v1/search/semantic → EmbeddingUseCase.search_semantic()
    └─ embed_one(query) via run_in_threadpool → QdrantVectorRepository.search() (role_scope filter)

GET /api/v1/search/keyword → EmbeddingUseCase.search_keyword()
    └─ run_in_threadpool → PostgresBM25Repository.search() (BM25 ranking)
```

---

## Domain Layer

### SearchResult (new model)
```python
@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    document_title: str
    chunk_type: ChunkType
    text: str
    page_number: Optional[int]
    parent_section_header: Optional[str]
    bbox_json: Optional[dict]
    score: float        # normalized 0–1
    role_scope: str
```

### New Interfaces
- `IEmbeddingService`: `embed_batch(texts) → List[List[float]]`, `embed_one(text) → List[float]`
- `IVectorRepository`: `ensure_collection`, `batch_upsert`, `search`, `delete_by_document`
- `IBM25Repository`: `build_index`, `search`, `delete_by_document`

---

## Application Layer

### EmbeddingUseCase

**`embed_document(document_id, job_id)`** — called by IngestionWorker after parsing:
1. Verify document exists, chunks exist
2. `job_repo.update_status(EMBEDDING)`
3. `vector_repo.ensure_collection("document_chunks", 1024)` — idempotent
4. `vector_repo.delete_by_document(...)` — clear old vectors for re-ingestion safety
5. Batch embed (32 chunks per call), upsert to Qdrant with payload
6. `bm25_repo.build_index(...)` — store TF per term in PostgreSQL
7. `job_repo.update_status(INDEXED)`

**Payload per Qdrant point:**
```json
{
  "document_id": "...",
  "chunk_index": 0,
  "chunk_type": "paragraph",
  "page_number": 1,
  "parent_section_header": "Section 1",
  "role_scope": "public",
  "document_title": "pump_manual.pdf",
  "revision_date": null,
  "text": "Inspect impeller for wear...",
  "bbox_json": null
}
```

**`search_semantic(query, role_scope, limit)`** — async:
- Embeds query via `run_in_threadpool` (non-blocking event loop)
- Calls `QdrantVectorRepository.search()` with `role_scope` filter

**`search_keyword(query, role_scope, limit)`** — async:
- Calls `PostgresBM25Repository.search()` via `run_in_threadpool`

---

## Infrastructure Layer

### SentenceTransformerEmbedder

- Model: `BAAI/bge-large-en-v1.5` (1024-dim, cosine-normalized)
- Loaded once at container startup (`get_embedding_service()`)
- `USE_TF=0` set at module level to prevent TF import conflicts
- SSL bypass via `requests.Session.request` monkey-patch (corporate cert workaround)

### QdrantVectorRepository

- `search()` uses `role_scope` Qdrant filter on every query (ADR-005 RBAC enforcement)
- `batch_upsert()` uses `client.upsert` (idempotent, safe for re-ingestion)
- Compatible with Qdrant server 1.9.x (client pinned to `>=1.9.0,<1.10.0`)

### PostgresBM25Repository

- BM25 parameters: K1=1.5, B=0.75 (standard Okapi BM25)
- Custom tokenizer: lowercase, alphanumeric, stop-word filtered, min length 2
- `search()` returns scores normalized to [0, 1]

### Migration 003

```sql
CREATE TABLE bm25_index (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_type TEXT NOT NULL DEFAULT 'paragraph',
    term TEXT NOT NULL,
    tf FLOAT NOT NULL,
    role_scope TEXT NOT NULL DEFAULT 'public',
    document_title TEXT NOT NULL DEFAULT '',
    page_number INTEGER,
    parent_section_header TEXT,
    bbox_json JSONB,
    chunk_text TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_bm25_term_scope ON bm25_index (term, role_scope);
CREATE INDEX idx_bm25_document ON bm25_index (document_id);
```

---

## API Endpoints

### `GET /api/v1/search/semantic`

```
?q=impeller+wear+inspection&limit=3&role_scope=public
Authorization: Bearer <token>

Response:
{
  "query": "impeller wear inspection",
  "total": 3,
  "results": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "document_title": "pump_manual.pdf",
      "chunk_type": "paragraph",
      "chunk_text": "Inspect impeller for wear and cavitation erosion.",
      "page_number": 1,
      "score": 0.899
    }
  ]
}
```

### `GET /api/v1/search/keyword`

Same schema. BM25 ranked. Both require `Authorization: Bearer` — unauthenticated returns 401.

---

## Job State Machine (complete)

```
QUEUED → EXTRACTING → EXTRACTED → PARSING → CHUNKED → EMBEDDING → INDEXED → COMPLETED
                                                                              FAILED (any step)
```

---

## Environment Notes

- `USE_TF=0` must be set before starting uvicorn to avoid Keras 3 conflict
- tiktoken BPE: pre-cached in `%TEMP%\data-gym-cache\`
- Model: `~/.cache/huggingface/hub/models--BAAI--bge-large-en-v1.5/`
- qdrant-client pinned to `>=1.9.0,<1.10.0` to match Qdrant server 1.9.0

---

## URLs

- **Backend API:** http://localhost:8000
- **Semantic search:** http://localhost:8000/api/v1/search/semantic?q=pump
- **Keyword search:** http://localhost:8000/api/v1/search/keyword?q=bearing
- **Frontend:** http://localhost:5173
