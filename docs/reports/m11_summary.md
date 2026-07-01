# M11 Summary — Compliance Brain Agent (LangGraph)

**Milestone**: M11
**Status**: ✅ Complete
**Date**: 2026-07-01

## Delivered

M11 is the third of five planned sub-brains, reusing the LangGraph agent
pattern from the Knowledge Brain (M9) and Maintenance Brain (M10):
`identify_regulation_scope → retrieve_procedures → detect_gaps →
generate_evidence → format_report`, exposed at `POST
/api/v1/brain/compliance/chat`. It maps regulatory text against procedure
text, detects compliance gaps with severity classification, and persists
every report for audit trail purposes.

### Domain Layer
- `GapSeverity` (enum), `ComplianceGap`, `ComplianceGapReport` — **Pydantic
  models**, not dataclasses (a deliberate departure from every other
  sub-brain's domain model, because the roadmap requires the LLM's output
  be schema-*enforced*, not just schema-*shaped*)
- `ComplianceAgentState` TypedDict — composes the Pydantic gap report with
  existing `SearchResult` (M4/M8) and `Citation` (M5) types
- `IComplianceReportRepository`, `IComplianceBrainAgent` interfaces

### Application Layer
- `ComplianceBrainAgent` — LangGraph state machine; no "uncertain intent"
  branch (an empty retrieval is a normal, reportable compliance-check
  result, not a classification failure, unlike M9/M10's routing logic)

### Infrastructure Layer
- `PostgresComplianceReportRepository` — persists
  `report.model_dump_json()` plus a denormalized `has_critical_gaps`
  boolean to a new `compliance_reports` table (migration `005`)

### Tool Registry
- `ai/agents/compliance_brain/tools.py` — `regulation_lookup`,
  `procedure_lookup` (both GraphRAG-based with a title-keyword filter),
  `compliance_gap_detector` (LLM call + the same 3-strategy JSON parsing
  M7's `LLMRelationExtractor` established, now validating into Pydantic
  instead of a dataclass)

### Prompt Engineering (ADR-020)
- `ai/prompts/compliance_brain/gap_detection.yaml` — strict JSON-only
  output, severity mapped explicitly from regulatory language strength
- `ai/prompts/compliance_brain/generate_evidence.yaml` — cited prose
  summary using the same `[[chunk:<id>]]` convention as M9/M10

### Presentation Layer
- `POST /api/v1/brain/compliance/chat` — JWT-authenticated; response
  includes the full structured `gap_report` alongside the cited prose
  summary, so a UI can render the gap table independently of the
  narrative text

## Files Created

```
backend/app/domain/compliance_brain/__init__.py
backend/app/domain/compliance_brain/models.py
backend/app/domain/compliance_brain/interfaces.py
backend/app/application/compliance_brain/__init__.py
backend/app/application/compliance_brain/compliance_brain_agent.py
backend/app/infrastructure/compliance/__init__.py
backend/app/infrastructure/compliance/compliance_report_repository.py
backend/ai/agents/compliance_brain/__init__.py
backend/ai/agents/compliance_brain/tools.py
backend/ai/prompts/compliance_brain/gap_detection.yaml
backend/ai/prompts/compliance_brain/generate_evidence.yaml
backend/app/presentation/api/v1/endpoints/compliance_brain.py
backend/migrations/versions/005_compliance_reports_m11.py
backend/tests/test_compliance_brain.py
docs/walkthroughs/m11_walkthrough.md
docs/verification/m11_verification.md
docs/reports/m11_summary.md
```

## Files Modified

```
backend/app/infrastructure/di/container.py
backend/app/infrastructure/config/settings.py
backend/app/presentation/api/v1/router.py
docs/implementation_roadmap.md
```

## Key Technical Decisions

- **`ComplianceGap`/`ComplianceGapReport` are Pydantic models, breaking
  the dataclass-only convention every other domain model in this codebase
  follows.** The roadmap is explicit: "enforced via Pydantic — not
  free-text (Engineering Bible §33)." Rather than maintaining a
  dataclass-for-domain / Pydantic-for-parsing pair with conversion
  boilerplate, both representations are the same object — Pydantic
  validates the LLM's JSON at construction time and rejects malformed
  entries immediately, which is exactly the boundary where runtime
  validation matters most. ADR-013 prohibits FastAPI/SQLAlchemy in domain,
  not validation libraries, so this doesn't violate Clean Architecture's
  actual intent.
- **`document_category` filtering is the same documented heuristic as
  M10, not a fresh attempt to fix it.** The gap was already fully
  investigated and accepted as a known limitation in M10; M11 hits the
  identical wall (no classification write/index path exists) and applies
  the same accepted pattern rather than re-investigating or expanding
  scope into M2/M4 a second time.
- **No "uncertain intent" routing branch**, unlike M9 (unknown query
  intent) and M10 (no asset tag found). A compliance check with no
  matching regulation or procedure content is still a *valid* outcome —
  "I couldn't find anything to compare" is itself the useful answer, not
  a failure to classify the request. The graph stays linear.
- **Report persistence failures are isolated from the answer-quality
  contract.** `format_report` wraps the Postgres write in its own
  try/except; a DB hiccup during the audit write logs a warning but does
  not set `error_flag` or block the user's answer, since the two concerns
  (answering the user vs. writing the audit trail) have different
  failure-tolerance requirements.

## Blockers Encountered and How They Were Resolved

- **None requiring debugging this session.** The step-counting lesson
  from M9 (LangGraph merges only a node's *returned* dict, not in-place
  mutation) and the `document_category` heuristic pattern from M10 were
  both applied correctly from the start — all 26 unit tests and the
  integration test passed on the first run.
- **mypy flagged a `str` where `GapSeverity` was expected** in
  `_item_to_gap` (Pydantic coerces strings to enums at runtime, but mypy's
  static check doesn't know that) — fixed by explicitly constructing
  `GapSeverity(str(item["severity"]).upper())` instead of passing the raw
  string, which also makes the coercion point visible to a reader.
- **Live E2E against the real sandbox correctly found zero matching
  regulation/procedure content**, since no OSHA/SOP documents are indexed
  in this dev Qdrant — this is the same honest "nothing found" behavior
  M10 exhibited for OEM manuals, not a defect. The actual gap-detection
  capability is proven by the integration test, which seeds realistic
  content directly and confirms a real `CRITICAL` gap lands in real
  Postgres.

## Test Results

- **27 new M11 tests** (26 unit + 1 integration) — all pass, first run
- **1/1 integration test run against live Postgres + Redis** (not mocked,
  not skipped) — confirms a real detected gap persists correctly
- **266 total backend tests pass** across the full suite — 0 failures, 0 errors
- Live E2E run against the real Docker stack + real Ollama: the roadmap's
  exact demo query correctly reported no matching documents (honest, not
  hallucinated) with full 5-step pipeline execution and real Redis session
  persistence

## What M11 Unlocks

Nothing blocks on M11 specifically (`Blocks: None` per the roadmap) — it
further validates the Knowledge Brain agent pattern generalizes to a third
structurally distinct sub-brain (structured-output-heavy rather than
document-retrieval-heavy or deterministic-data-heavy), and specifically
demonstrates the Pydantic-enforced-output pattern that M12 (RCA, which
also needs a validated `RCAReport` schema) will need too.
