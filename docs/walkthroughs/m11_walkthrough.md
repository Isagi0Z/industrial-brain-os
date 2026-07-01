# M11 Walkthrough — Compliance Brain Agent (LangGraph)

## Overview

M11 is the third of five planned sub-brains, reusing the LangGraph agent
pattern from the Knowledge Brain (M9) and Maintenance Brain (M10). It maps
regulatory requirements against current procedures, detects compliance
gaps with LLM-assisted analysis validated through a Pydantic schema (not
free text), and persists every report for audit trail purposes.

```
POST /api/v1/brain/compliance/chat
    │
    └─ ComplianceBrainAgent.run(query, session_id, user_role)
            │
            ├─ identify_regulation_scope (step 1)
            │      regulation_lookup(query) → GraphRAG (M8), title-filtered
            │      to regulation-looking documents
            │
            ├─ retrieve_procedures (step 2)
            │      procedure_lookup(query) → GraphRAG (M8), title-filtered
            │      to SOP/procedure-looking documents
            │
            ├─ detect_gaps (step 3)
            │      compliance_gap_detector(regulation_text, procedure_text)
            │      → IModelGateway.generate() with a strict-JSON prompt
            │      → parsed + validated into ComplianceGapReport (Pydantic)
            │
            ├─ generate_evidence (step 4)
            │      IModelGateway.generate() with the structured gaps +
            │      regulation/procedure context; produces a cited prose
            │      summary using [[chunk:<id>]] markers (same convention
            │      as M9/M10)
            │
            └─ format_report (step 5)
                   citation validation against regulation_chunks +
                   procedure_chunks combined; gap table prepended;
                   report persisted to Postgres (compliance_reports);
                   final markdown returned
                          │
                          ▼
                        END

Any node's tool/gateway exception -> error_flag=True, node returns
normally (no raise) -> conditional edge routes straight to format_report.

No "uncertain intent" branch: an empty regulation/procedure retrieval is a
normal, reportable compliance-check outcome, not a classification failure
— it flows through the same five nodes and the prompts handle empty
context honestly ("no matching regulation or procedure documents found").

Step count > max_steps (10) -> StepLimitExceededError, caught in run(),
produces a "STEP_LIMIT_EXCEEDED" answer instead of crashing — identical
mechanics to M9/M10, duplicated rather than shared via a base class this
session (same "wait for a third occurrence" reasoning noted in M10).
```

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/compliance_brain/models.py` (`GapSeverity`, `ComplianceGap`, `ComplianceGapReport`, `ComplianceAgentState`), `domain/compliance_brain/interfaces.py` (`IComplianceReportRepository`, `IComplianceBrainAgent`) |
| Application | `application/compliance_brain/compliance_brain_agent.py` — the LangGraph `StateGraph` and all five node implementations |
| Infrastructure | `infrastructure/compliance/compliance_report_repository.py` (`PostgresComplianceReportRepository`) |
| Tool registry | `ai/agents/compliance_brain/tools.py` |
| Prompts | `ai/prompts/compliance_brain/gap_detection.yaml`, `ai/prompts/compliance_brain/generate_evidence.yaml` |
| Presentation | `presentation/api/v1/endpoints/compliance_brain.py` — `POST /api/v1/brain/compliance/chat` |
| Data | `migrations/versions/005_compliance_reports_m11.py` |

## Domain Model — Pydantic, not dataclasses, and why

```python
class GapSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"

class ComplianceGap(BaseModel):
    regulation_clause: str
    procedure_gap: str
    severity: GapSeverity

class ComplianceGapReport(BaseModel):
    regulation_query: str
    procedure_query: str
    gaps: List[ComplianceGap] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_critical_gaps(self) -> bool:
        return any(g.severity == GapSeverity.CRITICAL for g in self.gaps)
```

Every other sub-brain (M9, M10) and every other domain model in this
codebase uses plain dataclasses — `WorkOrder`, `FailureRecord`,
`AgentState`, `MaintenanceAgentState` are all dataclasses/TypedDicts, not
Pydantic. M11 deliberately breaks that pattern for `ComplianceGap`/
`ComplianceGapReport` specifically because the roadmap requires the LLM's
gap-detection output be schema-*enforced*, not just schema-*shaped*:
dataclasses don't validate or coerce field values at construction time,
so a malformed LLM response (missing field, wrong severity string) would
silently produce an invalid object. Pydantic's validation raises
immediately, which `_item_to_gap` in the tool registry catches and skips
per-item — exactly the same "skip malformed items" contract M7's
`LLMRelationExtractor` already established for its own JSON parsing, just
enforced through a schema instead of manual field checks.

ADR-013 prohibits FastAPI/SQLAlchemy in the domain layer (heavy web/ORM
frameworks); Pydantic is a validation library already used elsewhere in
this codebase (`pydantic-settings`), so using it directly in
`domain/compliance_brain/models.py` — rather than maintaining a parallel
dataclass representation with conversion boilerplate — keeps a single
source of truth without violating the actual intent of that rule.

`ComplianceAgentState` itself stays a `TypedDict` (matching M9/M10) for
LangGraph state-schema consistency; its `gap_report` field simply holds a
`ComplianceGapReport` Pydantic instance or `None`.

## Tool Registry (`ai/agents/compliance_brain/tools.py`)

| Tool | Backing interface | Behavior |
|------|-------------------|----------|
| `regulation_lookup` | `IGraphRAGEngine` (M8) | Full hybrid retrieval, filtered to chunks whose `document_title` matches a regulation keyword heuristic (`osha`, `cfr`, `ansi`, `nfpa`, etc.) |
| `procedure_lookup` | `IGraphRAGEngine` (M8) | Same retrieval, filtered to chunks that look like SOP/procedure content (`sop`, `procedure`, `work instruction`, etc.) |
| `compliance_gap_detector` | `IModelGateway` (M5) | Sends regulation + procedure text to the LLM per `gap_detection.yaml`; parses the JSON response through the same three-strategy approach as M7 (`_try_direct` → `_try_bracket_extract` → `_try_strip_fences`); validates each item into a `ComplianceGap`, skipping anything that fails Pydantic validation |

## Why `regulation_lookup`/`procedure_lookup` use a title heuristic

This is the identical investigation and conclusion already documented in
M10's walkthrough for `oem_manual_lookup`, applying here for the same
reason: `DocumentClassification.category` (the field the roadmap's
"document_category" language refers to) has no write path anywhere in
this codebase, and Qdrant's payload schema (written by
`EmbeddingUseCase.embed_document()`, M4) has no category field to filter
on. Building that pipeline would mean touching M2 and M4 mid-milestone.
`regulation_lookup`/`procedure_lookup` instead retrieve normally via
`GraphRAGEngine.retrieve()` and filter by a document-title keyword
heuristic — documented as a known limitation, not silently passed off as
the real thing.

## Gap Detection — Pydantic enforcement at the LLM boundary

`compliance_gap_detector` sends the assembled regulation/procedure text to
the LLM using `gap_detection.yaml`'s strict-JSON system prompt (mirroring
M7's `relation_extraction.yaml` convention), then:

```python
gaps = _parse_gap_response(text)   # 3-strategy JSON extraction, M7-style
return ComplianceGapReport(regulation_query=..., procedure_query=..., gaps=gaps)
```

`_item_to_gap` constructs a `ComplianceGap` per array item, explicitly
building `GapSeverity(str(item["severity"]).upper())` rather than passing
a raw string — this makes the enum coercion visible to both Pydantic's
runtime validation and mypy's static check, and any `KeyError`/`TypeError`/
`ValueError` (including Pydantic's own `ValidationError`, which subclasses
`ValueError`) causes that single item to be skipped rather than aborting
the whole gap list.

## Citation Validation and Gap Table Rendering

Same `[[chunk:<chunk_id>]]` marker convention as M9/M10, validated in
`format_report` against the *combined* pool of `regulation_chunks` +
`procedure_chunks` chunk_ids (a citation can legitimately point at either
source). Ahead of the cited prose, `format_report` prepends a
deterministic Markdown table built directly from the structured
`gap_report` — this part carries zero hallucination risk since it's
rendered from validated Pydantic data, not LLM-generated text:

```
| Regulation Clause | Procedure Gap | Severity |
| --- | --- | --- |
| 1910.119(j) mechanical integrity | No inspection interval specified | CRITICAL |
```

## Audit Trail Persistence

`format_report` calls `IComplianceReportRepository.save(session_id, query,
gap_report)` whenever a `gap_report` was produced (even an empty one —
"no gaps found" is itself an auditable outcome). `PostgresComplianceReportRepository`
stores `report.model_dump_json()` (Pydantic v2) in a `JSONB` column
alongside a denormalized `has_critical_gaps` boolean for fast filtering.
This write is wrapped in its own try/except inside `format_report` — a
persistence failure is logged and swallowed rather than flipping
`error_flag` or blocking the user's answer, since the audit write is
best-effort infrastructure, not part of the user-facing contract.

## Session Persistence

Reuses the same `IChatHistoryRepository`/`RedisChatHistoryRepository`
singleton (`DIContainer.get_chat_history_repository()`) already shared
between `ChatUseCase` (M5), `KnowledgeBrainAgent` (M9), and
`MaintenanceBrainAgent` (M10) — no new persistence mechanism.

## Presentation Layer

```
POST /api/v1/brain/compliance/chat
Auth: Bearer JWT (OAuth2PasswordBearer, same as M9/M10)
Body: { "query": str, "session_id": str }
Response: { "answer": str,
            "gap_report": { regulation_query, procedure_query, gaps[], has_critical_gaps, generated_at } | null,
            "citations": [...], "session_id": str,
            "error_flag": bool, "step_count": int }
```

`gap_report` is `null` only when `detect_gaps` itself failed
(`error_flag` will also be `True` in that case) — a successful run with
zero gaps still returns a `gap_report` with an empty `gaps` array, since
"compliant" is a valid, reportable result distinct from "couldn't check."

## Configuration

| Setting | Default |
|---------|---------|
| `COMPLIANCE_GAP_DETECTION_PROMPT_FILE` | `ai/prompts/compliance_brain/gap_detection.yaml` |
| `COMPLIANCE_EVIDENCE_PROMPT_FILE` | `ai/prompts/compliance_brain/generate_evidence.yaml` |
| `COMPLIANCE_BRAIN_MAX_STEPS` | `10` |
| `COMPLIANCE_BRAIN_TOP_K` | `5` |

Reuses `CHAT_MAX_TOKENS` / `CHAT_SESSION_TTL_SECONDS` (M5) for generation
and session TTL.

## Environment Notes

No new third-party dependencies — `langgraph` and `pydantic` were already
project dependencies before this milestone. Migration `005` was applied
via `alembic upgrade head` against the live Docker Postgres.
