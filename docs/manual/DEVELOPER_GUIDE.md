# Developer Guide

Practical, task-oriented instructions for engineers working in this codebase
day to day. For first-time setup, see [`INSTALLATION.md`](INSTALLATION.md).
For the "why" behind the structure, see [`ARCHITECTURE.md`](ARCHITECTURE.md).
For git/PR/release process, see [`WORKFLOW.md`](WORKFLOW.md).

---

## 1. Local Development Loop

```bash
# Terminal 1 — infrastructure (once per session)
docker compose up -d

# Terminal 2 — backend (auto-reloads on file change)
cd backend
venv\Scripts\Activate.ps1        # or: source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 3 — Celery worker (needed for document ingestion)
cd backend
celery -A app.worker worker --loglevel=info

# Terminal 4 — frontend (auto-reloads on file change)
cd frontend
pnpm run dev
```

Common tasks (all defined in the root `Makefile`; PowerShell users can run
the underlying command directly or via `run.ps1` for the subset it covers):

| Task | Command |
|---|---|
| Install everything | `make install` |
| Lint (black, ruff, eslint) | `make lint` |
| Auto-format | `make format` |
| Run backend tests | `make test` |
| Run backend tests with coverage | `make coverage` |
| Run the RAG evaluation suite | `make eval` |
| Validate all prompt YAMLs | `make validate-prompts` |
| Seed demo KG + generate demo PDFs | `make demo-data` |
| Security scan (bandit + pip-audit + pnpm audit) | `make security-audit` |
| Latency benchmark | `make benchmark` |
| Apply DB migrations | `make db-migrate` |
| Reset DB (destroys data) | `make db-reset` |
| Initialise Qdrant/Neo4j/MinIO | `make init-infra` |

---

## 2. Testing Guide

The backend test suite lives in `backend/tests/` (385+ tests, pytest).

```bash
cd backend
pytest                          # full suite
pytest tests/test_auth_service.py -v      # a single file
pytest -k "test_authenticate"             # by name pattern
pytest --cov=app --cov-report=term-missing   # with coverage (target ≥80%)
```

**Windows note**: if you see `PermissionError: [WinError 5]` from a
`tmp_path`-based test, it's a Windows temp-directory ACL quirk, not a code
bug — rerun with an explicit writable basetemp:

```powershell
pytest --basetemp=C:\temp\pytest-tmp
```

Testing conventions actually used in this codebase:

- **Unit tests** mock domain-port dependencies with plain Python
  classes/`SimpleNamespace` (see `tests/test_auth_service.py`) — no mocking
  framework required for simple cases.
- **Architecture tests** (`tests/test_architecture.py`) assert the domain
  layer never imports outward (ADR-013) — this is CI-enforced, not just a
  convention.
- **Prompt tests** (`tests/test_prompts.py`) validate every shipped prompt
  against the schema and confirm the MANIFEST matches disk.
- Frontend has no unit-test runner configured yet; verification is
  `tsc --noEmit` + `eslint` + a manual/browser check (see `WORKFLOW.md`).

Frontend checks:

```bash
cd frontend
npx tsc --noEmit
pnpm run lint
pnpm run build     # tsc && vite build
```

---

## 3. How to Add New Documents

**Via the UI**: Document Hub → Upload tab → drag a PDF/DOCX/XLSX/PNG/JPEG
(max 100 MB) → the file uploads to `POST /api/v1/documents/`, which stores the
raw file in MinIO, creates a `jobs` row, and dispatches the Celery ingestion
chain (parse → embed → KG-extract). Watch its status in the Document Hub's
Library tab (it polls automatically while a job is in progress).

**Via the API**:

```bash
TOKEN="<your JWT — see API_REFERENCE.md#authentication>"
curl -X POST http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/manual.pdf"
```

**Programmatically at scale**: see `scripts/load_demo_data.py` — it shows the
pattern (mint a token, `POST` each file, one at a time) used to bulk-load the
demo dataset. Copy that pattern for a bulk-ingestion script; there is no
existing "bulk upload" endpoint.

If ingestion fails, `GET /api/v1/documents/{id}/status` shows the failure
reason, and `POST /api/v1/documents/{id}/retry` re-queues it.

---

## 4. How to Add New Regulations

Regulations are **not** a separate content type in this codebase — they are
ingested through the same document pipeline as any other file (§3). The
Compliance Brain distinguishes "regulation" text from "procedure" text at
**retrieval time** using a title-keyword heuristic
(`backend/ai/agents/compliance_brain/tools.py::_looks_like_regulation`):

```python
_REGULATION_KEYWORDS = (
    "regulation", "osha", "cfr", "code of federal", "standard",
    "ansi", "iso ", "api rp", "nfpa", "epa",
)
```

**To add a new regulation so the Compliance Brain finds it:**

1. Upload the regulation document (§3) with a **title that contains one of
   the keywords above** — e.g. `"OSHA 1910.119 — Process Safety Management.pdf"`
   or `"ANSI/API RP 754 — Process Safety Metrics.pdf"`. The title comes from
   the uploaded filename by default (or can be edited via
   `PUT /api/v1/documents/{id}/metadata`).
2. Wait for ingestion to complete (chunked, embedded, and its entities
   written to the Knowledge Graph as `Regulation`/`Document` nodes per
   `ontology/industrial_ontology.yaml`).
3. Ask the Compliance Brain a gap-detection question referencing the
   regulation and the procedure to check it against
   (`POST /api/v1/brain/compliance/chat`).

> **Known limitation** (documented in `docs/verification/m11_verification.md`):
> there is no dedicated `document_category` field enforced at the retrieval
> layer yet — the keyword heuristic is a stand-in. If you're extending this,
> the clean fix is to populate `DocumentClassification.category` at ingest
> time and filter on it in `regulation_lookup`/`procedure_lookup` instead of
> matching titles.

---

## 5. How to Add New Ontology Entities

The ontology is a single source of truth:
`ontology/industrial_ontology.yaml`, loaded and validated by
`backend/app/infrastructure/ontology/yaml_loader.py` against a meta-schema
(every node type needs `required_properties`; every relation needs
`source`/`relation`/`target`).

**To add a new node type:**

```yaml
# ontology/industrial_ontology.yaml
node_types:
  ControlValve:                     # new node type
    required_properties:
      - tag_number
      - valve_type
    optional_properties:
      - manufacturer
      - fail_position
```

**To add a new relation:**

```yaml
allowed_relations:
  - source: ControlValve
    relation: CONTROLS
    target: Process
```

**Steps:**

1. Edit `ontology/industrial_ontology.yaml` following the pattern above.
2. Validate it loads:
   ```bash
   cd backend
   python -c "from app.infrastructure.ontology.yaml_loader import load_ontology_schema; load_ontology_schema('../ontology/industrial_ontology.yaml')"
   ```
   (Adjust the import path/function name if it differs — check
   `yaml_loader.py`'s public functions if this exact call doesn't match.)
3. Restart the backend — `OntologyValidator` loads the file once at
   construction via the DI container (`container.get_ontology_validator()`);
   there's no hot-reload.
4. The new type is now enforced anywhere `OntologySchema.get_node_type()` is
   consulted (extraction, KG writes) and surfaced by
   `GET /api/v1/ontology/schema`.
5. If entity extraction should actually *recognize* the new type from text,
   also extend the relation-extraction prompt
   (`backend/ai/prompts/relation_extraction.yaml`) and/or the spaCy NER
   pipeline configuration — the ontology file alone only defines what's
   *allowed*, not what's automatically *detected*.

---

## 6. How to Add a New Brain Agent

This is the most involved recipe. Follow the pattern already established by
the five existing brains (Knowledge, Maintenance, Compliance, RCA, Lessons
Learned) — every one of them is built from the same shared primitives.

1. **Domain layer** (`app/domain/<new>_brain/`):
   - `models.py` — request/response dataclasses specific to this brain.
   - `interfaces.py` — any new repository ports this brain needs (skip if it
     only needs `IGraphRAGEngine` + `IModelGateway`, already defined).

2. **Prompt** (`backend/ai/prompts/<new>_brain/*.yaml`):
   - Follow the schema in `backend/ai/prompts/prompt_schema.json`: `prompt_id`
     (e.g. `new_brain.synthesize_answer`), `version`, `description`,
     `owning_brain`, `output_format`, `system`, plus `user_template` (and
     `uncertain_template` if the brain needs a clarification fallback).
   - Add an entry to `backend/ai/prompts/MANIFEST.yaml`.
   - Validate: `make validate-prompts`.

3. **Tool functions** (`backend/ai/agents/<new>_brain/tools.py`):
   - Thin, independently-testable functions wrapping domain interfaces (mirror
     `ai/agents/knowledge_brain/tools.py`).

4. **LangGraph agent** (`app/application/<new>_brain/<new>_brain_agent.py`):
   - Subclass `BaseBrainAgent` (`app/application/agents/base.py`) to get the
     step-limit guard and error-router edge selector for free.
   - Use the shared helpers: `load_prompt()`, `format_context_blocks()`,
     `validate_chunk_citations()`, `render_citations()` — do not reimplement
     citation validation from scratch.
   - Build the LangGraph `StateGraph` with nodes for retrieve → synthesize →
     validate/render, wired with `self._error_or(default=...)` conditional
     edges.

5. **Infrastructure** (only if the brain needs new persistence):
   - Add a repository under `app/infrastructure/<new>_brain/` implementing
     the domain interface from step 1.
   - If it needs a new table, add an Alembic migration under
     `backend/migrations/versions/` (see §8 below for the `CREATE TABLE IF
     NOT EXISTS` idempotent pattern used by every prior migration).

6. **Settings** (`app/infrastructure/config/settings.py`):
   - Add `<NEW>_BRAIN_PROMPT_FILE`, `<NEW>_BRAIN_MAX_STEPS`,
     `<NEW>_BRAIN_TOP_K` following the existing per-brain naming convention.

7. **DI wiring** (`app/infrastructure/di/container.py`):
   - Add a `get_<new>_brain_agent()` factory method that constructs the agent
     with its dependencies pulled from other `container.get_*()` calls.

8. **Presentation** (`app/presentation/api/v1/endpoints/<new>_brain.py`):
   - `router = APIRouter(prefix="/brain/<new>", tags=["<New> Brain"])`
   - A `POST /chat` (or session-based) endpoint mirroring
     `knowledge_brain.py`'s shape (`Depends(get_current_user)` for auth,
     `Depends` on a factory that calls the container).
   - Register it in `app/presentation/api/v1/router.py`:
     `api_router.include_router(new_brain.router)`.

9. **Frontend** (optional, if it needs a dedicated UI beyond the generic
   `SubBrainPanel`):
   - Add a route in `frontend/src/router/routes.tsx` and a nav entry in
     `frontend/src/components/layout/DashboardLayout.tsx`.

10. **Tests**: add `backend/tests/test_<new>_brain.py` covering step-limit
    exceeded, LLM/repo failure fallback, citation validation, and the happy
    path — mirror `test_rca_brain.py` or `test_maintenance_brain.py`.

11. **Docs**: add a row to the brain table in
    [`ARCHITECTURE.md`](ARCHITECTURE.md#3-how-each-brain-works).

---

## 7. How to Retrain or Regenerate Embeddings

There is **no single "reindex everything" command** in this codebase today —
be deliberate about which of these you need:

**Re-embed a single document** (e.g. after fixing a parsing bug for it):

```bash
curl -X POST http://localhost:8000/api/v1/documents/{document_id}/retry \
  -H "Authorization: Bearer $TOKEN"
```

This re-queues the full `parse → embed → kg` Celery chain for that document.

**Re-embed every document** (e.g. after changing
`GRAPHRAG_RERANKER_MODEL`/embedding model, or after a chunking-strategy
change):

1. There is no bulk-retry endpoint — write a small script that lists all
   documents (`GET /api/v1/documents/?limit=...`, paginated) and calls the
   retry endpoint for each `id`. `scripts/load_demo_data.py` shows the
   token-minting + `httpx` request pattern to copy.
2. If you're changing the **embedding model itself**
   (`infrastructure/search/embedding_service.py`'s `_MODEL_NAME`, currently
   `BAAI/bge-large-en-v1.5`), the new vectors will have a different dimension
   than what's stored in Qdrant. You must **drop and recreate the Qdrant
   collection** first:
   ```bash
   curl -X DELETE http://localhost:6333/collections/document_chunks
   python scripts/init_infra.py     # recreates it with the new vector size
   ```
   Then bulk re-embed as above.
3. The BM25 index (PostgreSQL `bm25_index` table) is rebuilt automatically as
   part of `embed_task` — no separate action needed for keyword search.

**Retrain the reranker or LLMLingua models**: these are pretrained
third-party models (`BAAI/bge-reranker-large`,
`microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`) consumed
as-is — this project does not fine-tune them. If you need a different model,
change `GRAPHRAG_RERANKER_MODEL` / `LLMLINGUA_MODEL` in `.env` and restart the
backend; both are lazy-loaded on first use.

---

## 8. How to Reset Databases

**Soft reset (keep containers, replay migrations):**

```bash
make db-reset
# equivalent to:
cd backend && alembic downgrade base && alembic upgrade head
```

Note: every migration in this repo uses `CREATE TABLE IF NOT EXISTS`, so
`alembic downgrade base` does **not** actually drop tables (check the
specific migration's `downgrade()` before relying on this to wipe data) — for
a guaranteed clean slate, use the hard reset below.

**Hard reset (wipe all data + volumes):**

```bash
docker compose down -v      # deletes Postgres/Neo4j/Qdrant/Redis/MinIO volumes
docker compose up -d
cd backend && alembic upgrade head && cd ..
python scripts/init_infra.py    # recreates Qdrant collections, Neo4j constraints, MinIO buckets
```

**Reset a single store** (example: just the Knowledge Graph):

```cypher
// via the Neo4j browser at http://localhost:7474, or `cypher-shell`
MATCH (n) DETACH DELETE n;
```

Then re-run ingestion (§3) or `make demo-data` to repopulate it.

---

## 9. Contributor Guide

See [`WORKFLOW.md`](WORKFLOW.md) for branch naming, commit conventions, the
PR checklist, and the release process. In short:

1. Read `docs/engineering_bible.md` and the relevant ADRs in
   `docs/architecture_decision_records.md` before making an architectural
   change.
2. Keep the domain layer pure — `tests/test_architecture.py` will fail your
   PR if it imports outward.
3. Run `make lint` and `make test` before opening a PR.
4. If you touch a prompt, run `make validate-prompts`.
5. If you touch retrieval/generation code, consider running `make eval` to
   check you haven't regressed the hallucination rate.
