# M3 Summary Report — OCR & Layout-Aware Parsing

**Date:** 2026-06-30  
**Status:** COMPLETE  

---

## What Was Built

M3 delivers the parsing backbone: every document uploaded in M2 is now automatically dequeued by a background worker, parsed into semantically typed chunks, and persisted in PostgreSQL, ready for embedding in M4.

### New files (12)
| File | Role |
|------|------|
| `backend/app/domain/document/constants.py` | `ChunkType` enum, extended `JobStatus`, chunking constants |
| `backend/app/domain/document/models.py` | `DocumentChunk` dataclass |
| `backend/app/domain/document/interfaces.py` | `IChunkRepository`, `IDocumentParser`, `download_file` |
| `backend/app/infrastructure/document/parsing/chunker.py` | tiktoken-based hierarchical splitter |
| `backend/app/infrastructure/document/parsing/pymupdf_parser.py` | PDF layout detection + PaddleOCR |
| `backend/app/infrastructure/document/parsing/docx_parser.py` | DOCX heading/table parser |
| `backend/app/infrastructure/document/parsing/xlsx_parser.py` | XLSX one-table-per-sheet parser |
| `backend/app/infrastructure/document/parsing/image_parser.py` | Image OCR with figure fallback |
| `backend/app/infrastructure/document/chunk_repository.py` | PostgresChunkRepository |
| `backend/app/application/document/parsing_service.py` | DocumentParsingUseCase |
| `backend/app/infrastructure/document/worker.py` | IngestionWorker (daemon thread) |
| `backend/migrations/versions/002_document_chunks_m3.py` | Schema: table_data_json, figure_storage_key |

### Modified files (5)
- `backend/app/infrastructure/document/minio_storage_service.py` — added `download_file()`
- `backend/app/infrastructure/di/container.py` — wired all M3 components
- `backend/app/main.py` — worker start/stop in lifespan
- `backend/app/presentation/api/v1/endpoints/document.py` — `/chunks` endpoint
- `backend/requirements.txt` — PyMuPDF, tiktoken, python-docx, openpyxl, paddlepaddle, paddleocr

---

## Key Design Decisions

**PyMuPDF over LayoutParser/PubLayNet** — ADR-012 allows equivalent open models. PyMuPDF's `get_text("dict")` provides block-level bbox + font metrics without requiring GPU inference, keeping the dev loop fast.

**Daemon thread over Celery** — Celery is deferred to M15 as specified in the roadmap. A simple `threading.Thread` with `BLPOP` polling satisfies the M3 requirement with zero operational overhead.

**Module-level tiktoken deferred** — `cl100k_base` encoding is loaded at first function call (not import time) to avoid SSL certificate failures on Windows when the BPE file is not yet cached. BPE file was pre-seeded to `%TEMP%\data-gym-cache\` for CI reproducibility.

**Single-transaction bulk insert** — `PostgresChunkRepository.bulk_insert()` wraps all chunk inserts in one transaction. On failure, no partial chunks are committed, making retries safe (combined with `delete_by_document_id()` before insert).

---

## Test Results

- **29 tests passed** (13 M2 + 16 M3)
- 0 lint errors (ruff)
- 0 type errors (mypy + tsc)
- E2E: PDF → 3 chunks (heading + 2 paragraphs) via `/chunks` endpoint

---

## Known Constraints

- PaddleOCR unavailable in current dev environment (corporate TLS blocks model download). Image pages fall back to FIGURE chunks. OCR path is tested at unit level with mocks.
- tiktoken BPE file must be pre-cached on new dev machines (one-time setup, documented in walkthrough).
