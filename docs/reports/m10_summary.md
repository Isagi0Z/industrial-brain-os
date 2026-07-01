# M10 Summary — Maintenance Brain Agent (LangGraph)

**Milestone**: M10
**Status**: ✅ Complete
**Date**: 2026-07-01

## Delivered

M10 is the second of five planned sub-brains, reusing the LangGraph agent
pattern from the Knowledge Brain (M9) with maintenance-specific state and
tools: `classify_maintenance_query → retrieve_asset_context →
retrieve_work_orders → synthesize_guidance → format_response`, exposed at
`POST /api/v1/brain/maintenance/chat`.

### Domain Layer
- `WorkOrder`, `FailureRecord` — new domain dataclasses
- `MaintenanceAgentState` TypedDict — composes `WorkOrder`/`FailureRecord`
  with existing `SearchResult` (M4/M8) and `Citation` (M5) types
- `IWorkOrderRepository`, `IFailureHistoryRepository`, `IMaintenanceBrainAgent` interfaces

### Application Layer
- `MaintenanceBrainAgent` — LangGraph state machine; asset-tag-driven
  routing (skip retrieval entirely with no tag found); branches
  `retrieve_work_orders` between a precise `WO-1234` lookup and the
  general "open work orders for this asset" query; citation validation
  folded into `format_response` (the checklist specifies exactly five
  nodes, no separate validation node like M9 has)

### Infrastructure Layer
- `PostgresWorkOrderRepository` — `work_orders` table queries (by wo_id,
  by asset_tag, open-only sorted by scheduled_date)
- `Neo4jFailureHistoryRepository` — queries the ontology's
  `(Equipment)-[:EXHIBITS]->(FailureMode)` edge (M6/M7, ADR-010)

### Tool Registry
- `ai/agents/maintenance_brain/tools.py` — `work_order_lookup`,
  `maintenance_schedule_query`, `failure_history_search`,
  `oem_manual_lookup`, `extract_asset_tag_tool`; each a pure function over
  an injected domain interface, independently unit-tested

### Data Layer
- Migration `004_work_orders_m10` — `work_orders` table
- `scripts/load_mock_cmms.py` + `scripts/mock_cmms_data.csv` — idempotent
  mock CMMS loader, 10 demo work orders across 4 assets

### Prompt Engineering (ADR-020)
- `ai/prompts/maintenance_brain/synthesize_guidance.yaml` — same
  `[[chunk:<id>]]` citation convention as M9, plus work-order and
  failure-history context blocks

### Presentation Layer
- `POST /api/v1/brain/maintenance/chat` — JWT-authenticated; response
  includes structured `work_orders`/`failure_history` lists alongside the
  generated guidance text (richer than M9's citation-only response, since
  a maintenance UI needs the raw records, not just prose)

## Files Created

```
backend/app/domain/maintenance_brain/__init__.py
backend/app/domain/maintenance_brain/models.py
backend/app/domain/maintenance_brain/interfaces.py
backend/app/application/maintenance_brain/__init__.py
backend/app/application/maintenance_brain/maintenance_brain_agent.py
backend/app/infrastructure/maintenance/__init__.py
backend/app/infrastructure/maintenance/work_order_repository.py
backend/app/infrastructure/maintenance/failure_history_repository.py
backend/ai/agents/maintenance_brain/__init__.py
backend/ai/agents/maintenance_brain/tools.py
backend/ai/prompts/maintenance_brain/synthesize_guidance.yaml
backend/app/presentation/api/v1/endpoints/maintenance_brain.py
backend/migrations/versions/004_work_orders_m10.py
backend/tests/test_maintenance_brain.py
scripts/load_mock_cmms.py
scripts/mock_cmms_data.csv
docs/walkthroughs/m10_walkthrough.md
docs/verification/m10_verification.md
docs/reports/m10_summary.md
```

## Files Modified

```
backend/app/infrastructure/di/container.py
backend/app/infrastructure/config/settings.py
backend/app/presentation/api/v1/router.py
docs/implementation_roadmap.md
```

## Key Technical Decisions

- **`document_category` filtering was investigated, found unimplementable
  as specified without touching frozen milestones, and honestly scoped
  down.** No write path in this codebase populates
  `DocumentClassification.category` or indexes a category field into
  Qdrant — building that pipeline would mean changing M2 and M4 code
  mid-milestone. `oem_manual_lookup` instead uses a documented
  document-title keyword heuristic and the gap is flagged in the roadmap
  for a future milestone, rather than silently faked or scope-crept into
  a rewrite of the embedding pipeline.
- **Step-limit and fallback mechanics are duplicated from M9, not shared
  via a base class, yet.** The roadmap says "fallback handler inherited
  from Knowledge Brain pattern" — interpreted as "same behavioral
  contract," not literal OOP inheritance, since retrofitting M9's
  already-committed `KnowledgeBrainAgent` to share a new base class would
  violate the "never refactor unrelated modules during a milestone" rule.
  With M10 now the second occurrence of this exact pattern and M11–M13
  confirmed still to come, extracting a shared `BaseLangGraphAgent` is a
  reasonable candidate for a future cleanup pass — not done here to keep
  this milestone's diff scoped to what M10 actually needs.
- **Citation validation is inline in `format_response`, not a separate
  node**, because the M10 checklist specifies exactly five named nodes,
  unlike M9's six (which includes a dedicated `validate_citations` node).
  The same regex-based extraction/hallucination-filtering logic from M9
  is reused conceptually, just placed differently.
- **`retrieve_work_orders` branches on an explicit `WO-\d+` pattern** in
  the query text, calling `work_order_lookup(wo_id=...)` for a precise
  single-record answer instead of always returning "all open work orders"
  — a query naming a specific work order should get that specific record.

## Blockers Encountered and How They Were Resolved

- **`document_category` filtering had no real data source.** Traced
  through `IDocumentRepository`, `PostgresDocumentRepository`, and the
  Qdrant payload schema written by `EmbeddingUseCase` before concluding
  the classification pipeline was never built. Implemented a documented
  heuristic instead of either faking the feature or expanding scope into
  M2/M4.
- **A transient LLM-call failure during live E2E verification** (empty
  exception message, consistent with cold-start httpx timeout while the
  embedding model was loading for the first time in a fresh process) —
  not a code bug. Confirmed by re-running with the embedding model
  pre-warmed, which completed cleanly end-to-end. The failure itself
  became useful evidence: `error_flag`, partial `work_orders`/
  `failure_history` data, and the degraded-response message all behaved
  exactly as designed under a real (not mocked) failure.
- **None of the step-counting or LangGraph-API pitfalls from M9 recurred**
  — applying the lesson learned (return-value-based state updates) from
  the start meant all 29 unit tests passed on the first run.

## Test Results

- **30 new M10 tests** (29 unit + 1 integration) — all pass, first run
- **1/1 integration test run against live Postgres + Neo4j + Redis** (not
  mocked, not skipped)
- **239 total backend tests pass** across the full suite — 0 failures, 0 errors
- Live E2E run against the real Docker stack + real Ollama + real loaded
  mock CMMS data: the roadmap's exact demo query correctly surfaced 3 real
  work orders and 1 real failure-history record for `P-102A`, and honestly
  reported no OEM manual content found (since no real documents are
  indexed in this sandbox yet) rather than hallucinating a procedure

## What M10 Unlocks

Nothing blocks on M10 specifically (`Blocks: None` per the roadmap) — it
demonstrates the Knowledge Brain agent pattern (M9) generalizes cleanly to
a second, structurally different sub-brain (deterministic-data-heavy
rather than document-retrieval-heavy), which de-risks M11 (Compliance),
M12 (RCA), and M13 (Lessons Learned) reusing the same pattern.
