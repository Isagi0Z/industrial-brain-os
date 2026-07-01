# M12 Verification Report

## Quality Gate Results

| Gate | Tool | Result |
|------|------|--------|
| Formatting | black | ✅ Pass on all M12 files (1 pre-existing unformatted file from M7, `worker.py`, left untouched — out of scope) |
| Lint | ruff | ✅ Pass (2 auto-fixed in the test file, 0 remaining) |
| Type check | mypy | ✅ Pass — 0 issues attributable to any new/changed M12 file (11 pre-existing errors elsewhere, identical set to M9–M11's sessions) |
| Unit tests | pytest | ✅ 24/24 M12 unit tests passed |
| Integration tests | pytest (`-m integration`) | ✅ 1/1 M12 integration test passed against **live** Postgres, Neo4j, and Redis |
| Full backend suite | pytest `tests/` | ✅ **291 passed, 0 failed, 0 errors** |
| Frontend type check | `tsc --noEmit` | ✅ No errors (M12 is backend-only) |
| Docker services | direct HTTP/driver checks | ✅ postgres, neo4j, redis healthy; qdrant/minio report `unhealthy` label (pre-existing broken healthcheck binary — both respond 200 on their real endpoints) |
| Migration | `alembic upgrade head` | ✅ `005 -> 006` applied cleanly (`rca_sessions` table created) |
| Live backend boot | `uvicorn app.main:app` | ✅ Started clean; all 5 infra connections established; `/api/v1/health` → `healthy` |
| RBAC | `curl -X POST /api/v1/brain/rca/session` unauthenticated | ✅ `401 Unauthorized` |
| Live agent run (demo scenario) | real Ollama, live Docker | ✅ Full 3-turn 5-Whys → COMPLETED report, persisted to real Postgres (see below) |

## New Tests (test_rca_brain.py — 25 tests: 24 unit + 1 integration)

| Class | Tests | Covers |
|-------|-------|--------|
| `TestDomainModels` | 3 | six Fishbone categories; `RCAReport` defaults; Pydantic rejects a report missing `root_cause` |
| `TestToolRegistry` | 10 | `extract_keywords` (stopword/short/domain-word filtering, empty); `failure_pattern_search` (delegate, empty tag); `incident_history_search` keyword use; `parse_report_object` (valid/fenced/unparseable); `fishbone_analysis` runs **all six categories** and isolates a branch failure |
| `TestRCAFiveWhys` | 5 | start suggests first why; advance records answer + suggests next; **reaching max_whys generates the report** (all six fishbone categories present, live-state cleared); **resume uses the persisted state store** (not memory); unknown session → `KeyError` |
| `TestRCAReportCitationValidation` | 2 | hallucinated `[[chunk:...]]` dropped while a real chunk id and a real failure code are kept; an unparseable report falls back gracefully with the Fishbone still attached |
| `TestRCAFallback` | 2 | a `suggest_why` LLM failure marks the session `FAILED`; the step limit marks it `FAILED` |
| `TestSerialization` | 2 | `RCASession` round-trips through the shared serializer with and without a report |
| Integration (live Postgres/Neo4j/Redis) | 1 | **Full roadmap acceptance test**: seeds a real `(Equipment)-[:EXHIBITS]->(FailureMode)` edge + a real `work_orders` row, runs a full 3-turn 5-Whys (`max_whys=2`) to a `COMPLETED` report, and verifies it persisted to the real `rca_sessions` table |

All 24 unit tests and the integration test passed on the **first run** — the
M9 step-count lesson (LangGraph merges only a node's returned dict) was
applied from the start, same as M10/M11.

## Live End-to-End Verification (beyond automated tests)

With the backend running against the real Docker Compose stack, a real
`(Equipment)-[:EXHIBITS]->(FailureMode)` edge (`FM-BRG-02`, "Bearing thermal
seizure") seeded in Neo4j and a real `work_orders` row seeded in Postgres
for `P-102A`, and the agent constructed with the **real `mistral:latest`**
Ollama model (settings' default `llama3.2` is not pulled in this sandbox —
same caveat as M9–M11):

```
Incident: "pump P-102A bearing failure"   (the roadmap's demo scenario)

TURN 1  start_session
  status: AWAITING_INPUT
  why 1 (real LLM, grounded in the seeded failure mode):
    "Why did bearing thermal seizure occur in P-102A pump?"

TURN 2  advance_session(answer="The bearing overheated during operation")
  status: AWAITING_INPUT
  why 2 (real LLM, drilling deeper):
    "Why was the bearing overheating during operation? (Specifically
     focusing on potential causes related to temperature or lubrication.)"

TURN 3  advance_session(answer="Lubrication was insufficient because PM was skipped")
  status: COMPLETED   (max_whys=2 reached)
  report (real LLM, validated into RCAReport):
    root_cause: "Skipped preventive maintenance resulting in insufficient
                 lubrication"
    contributing_factors: ["Operating pump without proper lubrication"]
    recommended_actions: ["Reinstate preventive maintenance schedule for
                           P-102A pump", "Ensure adequate lubricant levels
                           during operation"]
    evidence_citations: ["FM-BRG-02"]   ← the real seeded failure code was
                                           cited; citation validation kept it
    fishbone categories: all six present (Equipment, Method, Material, Man,
                          Environment, Measurement)

  Verified directly against real Postgres:
    SELECT status FROM rca_sessions WHERE session_id = '<session>'
    → COMPLETED
```

The root cause genuinely synthesizes the human answers across turns, and the
citation validator correctly retained the real `FM-BRG-02` failure code
while (in unit tests) dropping hallucinated chunk references. The six
Fishbone categories are all present but empty in this run — the honest
"no indexed documents to categorize" behavior identical to M10 (no OEM
manuals) and M11 (no regulations/SOPs) in this empty-corpus sandbox; the
parallel 6-branch mechanism itself is proven correct by
`test_fishbone_analysis_runs_all_six_categories`.

Unauthenticated request:
```
POST /api/v1/brain/rca/session  (no Authorization header)
→ 401 Unauthorized
```

## Files Created / Modified

See `docs/reports/m12_summary.md` for the full file inventory.

## Architecture Compliance

- Clean Architecture: RCA domain models/interfaces in `domain/`;
  `RCABrainAgent` (application) depends only on domain interfaces ✅
- ADR-007 (LangGraph): `StateGraph` with `interrupt_before` at the
  human-in-the-loop node; explicit step ceiling; no unbounded loops ✅
- ADR-010 (Industrial Ontology): failure patterns queried via the
  ontology-defined `EXHIBITS` relation (reusing M10's repository) ✅
- ADR-013 (Clean Architecture): dependency direction preserved; Pydantic
  used only at the LLM-output boundary, not as a framework substitute ✅
- ADR-020 (PromptOps): all three prompt files version-controlled ✅
- Engineering Bible §15 (RBAC): endpoint requires a valid JWT (401 verified) ✅
- Engineering Bible §16 (Logging): every node logs structured `extra=`
  fields (`node`, `step`, `duration_ms`, `session_id`, node-specific counts) ✅
- Engineering Bible §21 (AI Agent Standards): step ceiling + fallback
  handler + bounded 5-Whys depth ✅
- Engineering Bible §28 (Scalability / stateless services): session state
  lives in Redis + Postgres, not process memory — the service stays
  stateless and horizontally scalable ✅
- Engineering Bible §33 (explicit validation schemas): `RCAReport` is
  Pydantic-validated, never trusted as free LLM text ✅

## Deliberate Deviation (documented, not silently substituted)

The roadmap names "LangGraph checkpoint store (Redis-backed)" for session
resume. The official `langgraph-checkpoint-redis` requires the RedisJSON /
RediSearch modules, which the plain `redis:7.2-alpine` deployment does not
provide; and an in-process `MemorySaver` would make the service stateful,
violating Engineering Bible §28. The implementation therefore keeps the
service stateless with a Redis-backed application session store
(`RedisRCAStateStore`) for resume plus a Postgres audit table, while still
genuinely compiling the graph with `interrupt_before=["human_confirm"]` +
`MemorySaver` so the 5-Whys pause point is a real LangGraph interrupt. This
is the more robust reading of the requirement (survives restarts and
multiple workers) and is documented in the walkthrough.

The `document_category` retrieval-filter limitation noted in M10/M11 also
applies to any document evidence RCA retrieves (Fishbone / root-cause
chunks), for the same reason (no classification write/index pipeline). RCA
degrades honestly when no documents are indexed, as shown in the live run.

## Pre-existing Known Issues (NOT M12)

- `worker.py` (from M7) fails `black --check` — pre-existing formatting drift.
- Qdrant and MinIO report `unhealthy` in `docker compose ps` — pre-existing
  broken healthcheck binary; both respond `200 OK` on their real endpoints.
- Ollama's default configured model (`llama3.2`) is not pulled in this
  sandbox — only `mistral:latest` is; the live E2E used `mistral:latest`.
