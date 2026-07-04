# Frequently Asked Questions

## General

**What is Industrial Brain OS?**
A unified Asset & Operations intelligence platform for industrial facilities.
It ingests heterogeneous documents (manuals, P&IDs, SOPs, inspection reports,
regulations, maintenance logs) and exposes them through a hybrid
GraphRAG-powered chat copilot, an interactive Knowledge Graph, and five
specialized "brain" agents (Knowledge, Maintenance, Compliance, Root Cause
Analysis, Lessons Learned). See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the
full picture.

**Do I need a GPU to run this?**
No. Everything (Ollama, the reranker, LLMLingua) runs on CPU by default.
A GPU dramatically improves chat/generation latency but isn't required to run
or evaluate the system.

**Do I need an internet connection to run it?**
Only for one-time setup: pulling Docker images, pulling the `llama3.2`
Ollama model, and the first-use download of the reranker/LLMLingua models
from HuggingFace. After that, everything runs fully local unless you set
`LLM_PROVIDER=gemini` (which calls the Gemini API).

**Can I use a different LLM instead of Ollama?**
Yes — set `LLM_PROVIDER=gemini` and provide `GEMINI_API_KEY` in `.env`. The
chat gateway is behind a domain interface (`IModelGateway`), so a third
provider could be added by implementing that interface and wiring it into
the DI container.

---

## Setup

**Why do I need to pull `llama3.2` separately from installing Ollama?**
Installing Ollama only installs the runtime — models are downloaded
on-demand with `ollama pull <model>`. Reinstalling Ollama does **not**
re-download previously pulled models; if you reinstall, re-pull.

**Why does the frontend dev server conflict with Grafana?**
Both default to port 3000 (Vite's config and Grafana's container port
coincidentally match). Stop one or change a port — see
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md#port-3000-conflict-between-grafana-and-the-vite-dev-server).

**What Python version should I use?**
The project's own virtual environment was built and tested against Python
3.9.13, and CI targets Python 3.9. It also runs fine on newer 3.x versions
for most day-to-day work, but if you hit a dependency-resolution issue,
Python 3.9 is the known-good baseline.

---

## Usage

**Why did the chat copilot say it has no information about something I know
is in a document I uploaded?**
Check the document's processing status in the Document Hub — if it's not yet
`PROCESSED`, it isn't searchable yet. Also confirm your account's role scope
has access to that document (see `ADMIN_GUIDE.md` for the current RBAC
status — most deployments today are effectively single-tier).

**Why does the same document keep showing 0% Knowledge Graph relationships?**
Knowledge Graph population happens in the *last* stage of ingestion
(`kg_task`) — confirm the document reached `PROCESSED`, not just
`PROCESSING`. Entity/relation extraction quality also depends on how
explicitly the document states tag numbers and relationships; free-form
prose extracts fewer relations than a structured P&ID description.

**Are chat answers guaranteed to be accurate?**
No system is — but the pipeline is specifically designed to reduce
hallucination: Stage 8 citation validation strips any `[[chunk:id]]`
reference that doesn't correspond to a real retrieved chunk, and the M16
evaluation layer continuously measures a `hallucination_rate` metric against
a golden dataset with a CI-enforced ceiling (0.15). Always verify a critical
answer against its cited source.

**What does "role_scope" mean and does it actually restrict what I see?**
Documents and chunks carry a `role_scope` field that both vector and keyword
search filter on. However, see `ADMIN_GUIDE.md` §1 — role hydration from the
database is a documented in-progress item, so in the current build most
authenticated users effectively resolve to the `"public"` scope. Don't rely
on this for strict access control until that gap is closed.

---

## Development

**Where do I add a new LLM prompt?**
Never inline it in Python. Add a YAML file under `backend/ai/prompts/`
following `prompt_schema.json`, register it in `MANIFEST.yaml`, and run
`make validate-prompts`. Full recipe: [`ARCHITECTURE.md` §10](ARCHITECTURE.md#10-promptops-m18).

**How do I add a whole new brain (like "Inspection Brain")?**
See the step-by-step recipe in
[`DEVELOPER_GUIDE.md` §6](DEVELOPER_GUIDE.md#6-how-to-add-a-new-brain-agent).

**Why does `tests/test_architecture.py` fail on my change?**
You imported something from `infrastructure/`, `presentation/`,
`application/`, or a framework (FastAPI, SQLAlchemy, psycopg2, etc.) into a
module under `app/domain/`. The domain layer must depend on nothing outward
(ADR-013) — move the framework-touching code to an infrastructure adapter
and depend on a domain interface instead.

**Is there a bulk/reindex-everything embeddings command?**
No — see [`DEVELOPER_GUIDE.md` §7](DEVELOPER_GUIDE.md#7-how-to-retrain-or-regenerate-embeddings)
for the manual (but straightforward) procedure, including the Qdrant
collection-recreation step required if you change the embedding model
itself.

**How is "regulation" content different from a normal document?**
It isn't, structurally — regulations are ingested through the same pipeline
as any document. The Compliance Brain distinguishes them at retrieval time
using a title-keyword heuristic. See
[`DEVELOPER_GUIDE.md` §4](DEVELOPER_GUIDE.md#4-how-to-add-new-regulations).

---

## Operations

**How do I know if the system is healthy?**
`GET /api/v1/health` returns per-database status. Grafana
(`http://localhost:3000`) has two dashboards (API Performance, RAG Quality).
Jaeger (`http://localhost:16686`) has full request traces.

**What's the CI merge gate?**
Two: the RAG evaluation gate (fails if hallucination rate > 0.15) and the
PromptOps gate (schema/manifest/hardcoded-prompt checks). See
[`WORKFLOW.md` §4](WORKFLOW.md#4-continuous-integration).

**Where are backups documented?**
[`DEPLOYMENT.md` §5](DEPLOYMENT.md#5-backup-and-restore) — each data store
(PostgreSQL, Neo4j, Qdrant, MinIO) has its own procedure; Redis holds only
transient state and doesn't need backing up.

**What's the current test coverage / are there known gaps?**
77% backend line coverage as of M20 (385+ tests). The gap is concentrated in
infrastructure adapters that need live-service integration harnesses (DI
container wiring, DB repositories, the streaming chat endpoint) rather than
untested business logic — see `docs/bible_compliance.md` for the full
self-assessment.
