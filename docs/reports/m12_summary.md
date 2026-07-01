# M12 Summary — RCA Brain Agent (LangGraph, 5-Whys + Fishbone)

**Milestone**: M12
**Status**: ✅ Complete
**Date**: 2026-07-02

## Delivered

M12 is the fourth of five planned sub-brains and the first that is
**session-based and human-in-the-loop**: an interactive 5-Whys Root Cause
Analysis spanning multiple HTTP requests, culminating in a Pydantic-
validated `RCAReport` that combines the converged root cause with a
parallel Fishbone (Ishikawa 6M) analysis. Exposed at
`POST /api/v1/brain/rca/session`.

### Domain Layer
- `RCAReport` — Pydantic model (`problem_statement`, `root_cause`,
  `contributing_factors[]`, `recommended_actions[]`, `evidence_citations[]`,
  plus a `fishbone` map), validated at the LLM-output boundary (§33)
- `RCAStatus`, `FishboneCategory` (the six 6M categories), `WhyStep`,
  `RCASession`, `RCAAgentState`
- `IIncidentHistoryRepository`, `IRCASessionRepository` (Postgres audit),
  `IRCASessionStateStore` (Redis live state), `IRCABrainAgent`

### Application Layer
- `RCABrainAgent` — a single compiled LangGraph `StateGraph`
  (`define_problem → decide → {suggest_why → [interrupt_before]
  human_confirm | identify_root_cause → generate_report}`) driven by
  `start_session` / `advance_session`; cross-request resume via durable
  Redis+Postgres session state (stateless service, §28)

### Infrastructure Layer
- `PostgresIncidentHistoryRepository` — queries the M10 `work_orders` table
  by description `ILIKE` (reuses M10 data, no M10 code touched)
- `PostgresRCASessionRepository` — `rca_sessions` audit table (migration 006)
- `RedisRCAStateStore` — live working-state store enabling resume
- `serialization.py` — shared session (de)serialization

### Tool Registry
- `failure_pattern_search` (reuses M10's Neo4j `EXHIBITS` repo),
  `incident_history_search`, `extract_keywords`, `suggest_next_why`,
  `fishbone_analysis` (6 concurrent branches via `asyncio.gather`),
  `parse_report_object` (M7/M11 3-strategy JSON parse)

### Prompt Engineering (ADR-020)
- `suggest_why.yaml`, `generate_report.yaml` (strict JSON object),
  `fishbone.yaml` (per-category JSON array) — all version-controlled

### Presentation Layer
- `POST /api/v1/brain/rca/session` — JWT-authenticated, session-based
  multi-turn; response carries the whys ladder, the pending `next_why`, and
  (on completion) the full structured `RCAReport`

## Files Created

```
backend/app/domain/rca_brain/{__init__,models,interfaces}.py
backend/app/application/rca_brain/{__init__,rca_brain_agent}.py
backend/app/infrastructure/rca/{__init__,incident_history_repository,rca_session_repository,redis_rca_state_store,serialization}.py
backend/ai/agents/rca_brain/{__init__,tools}.py
backend/ai/prompts/rca_brain/{suggest_why,generate_report,fishbone}.yaml
backend/app/presentation/api/v1/endpoints/rca_brain.py
backend/migrations/versions/006_rca_sessions_m12.py
backend/tests/test_rca_brain.py
docs/walkthroughs/m12_walkthrough.md
docs/verification/m12_verification.md
docs/reports/m12_summary.md
```

## Files Modified

```
backend/app/infrastructure/di/container.py     — +get_incident_history_repository(), +get_rca_session_repository(), +get_rca_state_store(), +get_rca_brain_agent()
backend/app/infrastructure/config/settings.py  — +RCA_* settings (3 prompt files, max_steps, max_whys, top_k, incident_history_limit)
backend/app/presentation/api/v1/router.py      — registered rca_brain.router
docs/implementation_roadmap.md                 — M12 checklist all [x]; commit SHA TBD
```

## Key Technical Decisions

- **Human-in-the-loop resume is stateless (Redis+Postgres), not an
  in-process LangGraph checkpointer.** The official
  `langgraph-checkpoint-redis` needs the RedisJSON module (absent from the
  plain `redis:7.2-alpine` deployment), and an in-process `MemorySaver`
  would violate Engineering Bible §28's stateless-service rule. The graph
  still genuinely compiles with `interrupt_before=["human_confirm"]` +
  `MemorySaver` (so the 5-Whys pause is a real LangGraph interrupt), but
  cross-request continuity comes from reloading the durable session and
  re-invoking. This is documented as a deliberate, justified deviation
  rather than silently substituted.
- **Session-based endpoint, not the single-shot `run()` of M9–M11.** RCA is
  inherently multi-turn; `start_session`/`advance_session` model the human
  loop, and the same `POST /brain/rca/session` endpoint discriminates start
  vs. advance by the presence of `session_id`.
- **`RCAReport` is Pydantic (like M11), the rest is dataclass (like
  M9/M10).** Only the LLM-output boundary needs schema enforcement.
- **Fishbone runs six genuinely concurrent branches** (`asyncio.gather`),
  each with its own GraphRAG retrieval, satisfying "parallel branches per
  Ishikawa category"; a branch failure degrades to an empty category rather
  than failing the report.
- **No duplication of M10.** Failure-pattern search reuses M10's
  `Neo4jFailureHistoryRepository`; incident history reuses the M10
  `work_orders` table via a new focused repository, leaving M10 untouched.

## Blockers Encountered and How They Were Resolved

- **`langgraph-checkpoint-redis` unusable against plain Redis** (needs
  RedisJSON) — resolved with the stateless Redis+Postgres session design
  above; verified the `interrupt_before` mechanism directly before building.
- **Passing the Fishbone dict between graph nodes** initially used a hacky
  carrier stuffed into the `report` state slot; replaced with a proper
  `fishbone` field on `RCAAgentState` for clean typing.
- **Redis `.get()` typing** flagged by mypy — resolved with the same
  targeted `# type: ignore[arg-type]` M8's `RedisGraphRAGCache` already uses.
- **No step-counting or LangGraph-API pitfalls recurred** — the M9 lesson
  (return-value-based state updates) was applied from the start; all 24 unit
  tests and the integration test passed on the first run.

## Test Results

- **25 new M12 tests** (24 unit + 1 integration) — all pass, first run
- **1/1 integration test against live Postgres + Neo4j + Redis** — drives a
  full 3-turn 5-Whys to a COMPLETED report and verifies it persisted to the
  real `rca_sessions` table
- **291 total backend tests pass** across the full suite — 0 failures, 0 errors
- Live E2E against the real Docker stack + real Ollama: a full multi-turn
  5-Whys session produced a genuine root-cause report with a 6-category
  Fishbone, persisted to real Postgres (details in the verification report)

## What M12 Unlocks

Nothing blocks on M12 (`Blocks: None`). It proves the LangGraph agent
pattern extends to a genuinely stateful, multi-turn, human-in-the-loop
workflow — the most structurally different sub-brain so far — leaving only
M13 (Lessons Learned) to complete the five-brain platform.
