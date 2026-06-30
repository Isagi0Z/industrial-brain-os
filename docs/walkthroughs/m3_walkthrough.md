# M3 Walkthrough — OCR & Layout-Aware Parsing Pipeline

## Overview

Milestone M3 adds a production-grade document parsing pipeline on top of the M2 upload foundation. Every uploaded document is now automatically ingested by a daemon worker, parsed for structure, and stored as semantically typed chunks ready for downstream embedding (M4+).

---

## Architecture

```
Upload (M2)
    ↓
Redis queue  ← IngestionWorker (daemon thread, FastAPI lifespan)
    ↓
DocumentParsingUseCase
    ↓
IDocumentParser  ─────────────────────────────────────
    ├─ PyMuPDFParser   (application/pdf)
    ├─ DocxParser       (docx, doc)
    ├─ XlsxParser       (xlsx)
    └─ ImageParser      (jpeg, png — PaddleOCR or figure fallback)
    ↓
ChunkRepository.bulk_insert()  → PostgreSQL document_chunks
    ↓
Job status: QUEUED → EXTRACTING → EXTRACTED → PARSING → CHUNKED
```

---

## Domain Layer Changes

### ChunkType (new value object)
```python
class ChunkType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    FOOTER = "footer"
    LIST_ITEM = "list_item"
```

### JobStatus extensions
Added intermediate states: `EXTRACTING`, `EXTRACTED`, `PARSING`, `CHUNKED`, `EMBEDDING`, `INDEXED`.

### DocumentChunk (new aggregate)
```python
@dataclass
class DocumentChunk:
    id: str
    document_id: str
    chunk_index: int
    chunk_type: ChunkType
    text: str
    page_number: Optional[int]
    parent_section_header: Optional[str]
    bbox_json: Optional[Dict[str, Any]]
    token_count: int
    created_at: datetime
    table_data_json: Optional[List[Dict[str, Any]]] = None
    figure_storage_key: Optional[str] = None
```

---

## Application Layer

### DocumentParsingUseCase (`parsing_service.py`)

1. **EXTRACTING** — update job status, download file bytes from MinIO via `storage_service.download_file()`
2. **EXTRACTED** — bytes received; update status
3. **PARSING** — select parser with `can_parse(mime_type)`, call `parser.parse()`
4. **CHUNKED** — `chunk_repo.delete_by_document_id()` + `bulk_insert()` in a single transaction; update document status to `PROCESSED`

Inner `_fail(msg)` helper sets job to `FAILED` and marks document `FAILED` atomically on any exception.

---

## Infrastructure Layer

### PyMuPDFParser (`pymupdf_parser.py`)

Uses `page.get_text("dict")` for block-level layout detection:

| Signal | Rule | Assigned type |
|--------|------|--------------|
| Block y > 92% page height + text < 120 chars | Footer | `FOOTER` |
| Average span font-size ≥ 1.4× median | Heading | `HEADING` |
| Regex `^\s*(\d+[.)]\s\|[-•*]\s)` | List | `LIST_ITEM` |
| Block type 1 (image) | OCR or figure | `FIGURE` |
| Default | Paragraph | `PARAGRAPH` |

PaddleOCR is attempted for image-only pages (< 10 extracted characters). If unavailable or failing, the page becomes a `FIGURE` chunk.

### Hierarchical Chunker (`chunker.py`)

| Constant | Value |
|----------|-------|
| `CHUNK_SOFT_MAX_TOKENS` | 512 |
| `CHUNK_HARD_MAX_TOKENS` | 768 |
| `CHUNK_OVERLAP_TOKENS` | 64 |

- Tables and figures → single atomic chunk (never split)
- Paragraphs > 768 tokens → split using tiktoken `cl100k_base` with 64-token overlap windows
- `finalize_chunks()` re-indexes all chunks sequentially

### PostgresChunkRepository (`chunk_repository.py`)

`bulk_insert()` uses a single PostgreSQL transaction with `executemany`. JSONB fields (`bbox_json`, `table_data_json`) are serialized via `json.dumps()`.

### Migration 002

```sql
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS table_data_json JSONB;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS figure_storage_key TEXT;
```

### IngestionWorker (`worker.py`)

Daemon thread started in FastAPI lifespan (`app.main:lifespan`). Uses `Redis.blpop("ingestion:jobs", timeout=5)` — non-blocking poll with 5-second timeout. Parses JSON payload `{document_id, job_id}` and calls `DocumentParsingUseCase.parse_document()`.

---

## API Addition

### `GET /api/v1/documents/{id}/chunks`

Returns all stored chunks for a document:
```json
{
  "document_id": "...",
  "total_chunks": 3,
  "chunks": [
    {
      "chunk_index": 0,
      "chunk_type": "heading",
      "text": "Pump Maintenance Manual",
      "page_number": 1,
      "parent_section_header": null,
      "token_count": 9,
      "has_table_data": false,
      "has_figure": false,
      "bbox": {...}
    }
  ]
}
```

---

## Dependency Installation

Due to Windows corporate TLS inspection, packages were installed with:
```
pip install PyMuPDF tiktoken python-docx openpyxl paddlepaddle paddleocr \
  --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

tiktoken's BPE cache was pre-seeded to `%TEMP%\data-gym-cache\` to avoid network calls at import time.

---

## URLs

- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Frontend:** http://localhost:5173
