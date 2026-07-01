# M10 Walkthrough — Maintenance Brain Agent (LangGraph)

## Overview

M10 is the second of five planned sub-brains, reusing the LangGraph agent
pattern established by the Knowledge Brain (M9) with maintenance-specific
tools, state, and prompts. It answers questions about work orders,
maintenance scheduling, failure history, and OEM manual procedures for a
named piece of equipment.

```
POST /api/v1/brain/maintenance/chat
    │
    └─ MaintenanceBrainAgent.run(query, session_id, user_role)
            │
            ├─ classify_maintenance_query (step 1)
            │      extract_asset_tag_tool (spaCy, M7) → asset_tag
            │      logged for audit trail
            │
            ├── [asset_tag found] ──────────► retrieve_asset_context (step 2)
            │                                       │
            │                          failure_history_search (Neo4j EXHIBITS)
            │                          oem_manual_lookup (GraphRAG, M8, title-filtered)
            │                                       │
            │                                       ▼
            │                             retrieve_work_orders (step 3)
            │                                       │
            │                    "WO-1234" in query? ──► work_order_lookup(wo_id=...)
            │                    otherwise            ──► maintenance_schedule_query(asset_tag)
            │                                       │
            │                                       ▼
            └── [no asset_tag] ──────────────► synthesize_guidance (step 4)
                                                       │
                                          IModelGateway.generate() (M5)
                                          + prior turn history (Redis, M5/M9)
                                                       │
                                                       ▼
                                            format_response (step 5)
                                     [[chunk:<id>]] citation validation
                                     (same convention as M9, folded into
                                     this node rather than a separate one —
                                     the M10 checklist specifies exactly
                                     five nodes)
                                                       │
                                                       ▼
                                                     END

Any node's tool/gateway exception → error_flag=True, node returns
normally (no raise) → conditional edge routes straight to format_response.

Step count > max_steps (10) → StepLimitExceededError, caught in run(),
produces a "STEP_LIMIT_EXCEEDED" answer instead of crashing — identical
mechanics to M9 (duplicated rather than shared via a base class this
session; see "Key Technical Decisions" in the summary for why).
```

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/maintenance_brain/models.py` (`WorkOrder`, `FailureRecord`, `MaintenanceAgentState`), `domain/maintenance_brain/interfaces.py` (`IWorkOrderRepository`, `IFailureHistoryRepository`, `IMaintenanceBrainAgent`) |
| Application | `application/maintenance_brain/maintenance_brain_agent.py` — the LangGraph `StateGraph` and all five node implementations |
| Infrastructure | `infrastructure/maintenance/work_order_repository.py` (`PostgresWorkOrderRepository`), `infrastructure/maintenance/failure_history_repository.py` (`Neo4jFailureHistoryRepository`) |
| Tool registry | `ai/agents/maintenance_brain/tools.py` |
| Prompt | `ai/prompts/maintenance_brain/synthesize_guidance.yaml` |
| Presentation | `presentation/api/v1/endpoints/maintenance_brain.py` — `POST /api/v1/brain/maintenance/chat` |
| Data | `migrations/versions/004_work_orders_m10.py`, `scripts/load_mock_cmms.py`, `scripts/mock_cmms_data.csv` |

## Domain Model

```python
@dataclass
class WorkOrder:
    wo_id: str
    asset_tag: str
    description: str
    status: str
    priority: str
    scheduled_date: Optional[date] = None
    completed_date: Optional[date] = None

@dataclass
class FailureRecord:
    """One (Equipment)-[:EXHIBITS]->(FailureMode) edge (M6/M7 ontology, ADR-010)."""
    failure_code: str
    description: str
    severity: Optional[str] = None
    typical_cause: Optional[str] = None

class MaintenanceAgentState(TypedDict):
    query: str
    session_id: str
    user_role: str
    asset_tag: Optional[str]
    work_orders: List[WorkOrder]
    failure_history: List[FailureRecord]
    retrieved_chunks: List[SearchResult]
    draft_answer: str
    citations: List[Citation]
    step_count: int
    error_flag: bool
```

`SearchResult` (M4/M8) and `Citation` (M5) are reused unchanged — only
`WorkOrder` and `FailureRecord` are genuinely new domain concepts for M10.

## Tool Registry (`ai/agents/maintenance_brain/tools.py`)

| Tool | Backing interface | Behavior |
|------|-------------------|----------|
| `extract_asset_tag_tool` | `IEntityExtractor` (M7) | Wraps query text in a throwaway `DocumentChunk`, runs the same `SpacyEntityExtractor` used at ingestion time, returns the first recognized tag |
| `work_order_lookup` | `IWorkOrderRepository` | By explicit `wo_id`, or all work orders for an `asset_tag` |
| `maintenance_schedule_query` | `IWorkOrderRepository` | Open (`OPEN`/`IN_PROGRESS`) work orders for an asset, sorted by `scheduled_date` ascending |
| `failure_history_search` | `IFailureHistoryRepository` | `(Equipment)-[:EXHIBITS]->(FailureMode)` records for an asset |
| `oem_manual_lookup` | `IGraphRAGEngine` (M8) | Full hybrid retrieval, then filtered to chunks whose `document_title` matches an OEM/manual keyword heuristic |

Each is a pure function over an injected domain interface — no container/DI
imports inside `tools.py` — matching the M9 precedent so every tool is
independently unit-testable with plain mocks.

## Routing Logic

`classify_maintenance_query` extracts `asset_tag` and nothing else; the
actual routing decision (`retrieve` vs `uncertain`) happens in the
conditional edge attached to that node, mirroring M9's `_classify_intent`
placement. If no asset tag is found anywhere in the query, the agent skips
`retrieve_asset_context`/`retrieve_work_orders` entirely and goes straight
to `synthesize_guidance` with an "I couldn't identify which asset..."
uncertain template — there's no useful work to look up without knowing
*which* piece of equipment the user means.

`retrieve_work_orders` additionally checks for an explicit work-order ID
pattern (`WO-\d+`) in the query text — if present, it calls
`work_order_lookup(wo_id=...)` for a precise single-record lookup instead
of `maintenance_schedule_query`'s "all open work orders" behavior.

## Why `oem_manual_lookup` uses a title heuristic, not `document_category`

The roadmap's original wording was "calls GraphRAG with document_category
filter = 'OEM Manual'". Investigating the existing pipeline before
implementing this showed that capability doesn't exist end-to-end today:

- `DocumentClassification.category` is a real domain field (M2), but
  **nothing in the codebase ever writes it** — `IDocumentRepository` has no
  `add_classification`/`upsert_classification` method at all.
- `PostgresDocumentRepository.get_by_id()` never populates
  `Document.classifications` even if rows existed in the
  `document_classifications` table.
- The Qdrant payload schema written by `EmbeddingUseCase.embed_document()`
  (M4) has no category/document_type field — only `document_id`,
  `chunk_type`, `page_number`, `role_scope`, `document_title`, etc.

Building a real classification-and-indexing pipeline would mean touching
M2 (classification write path), M4 (embedding payload schema), and
possibly re-indexing already-embedded documents — well outside a single
milestone's scope and risking exactly the kind of unrelated-module
refactor the engineering workflow prohibits. `oem_manual_lookup` instead
retrieves normally via `GraphRAGEngine.retrieve()` (M8, unchanged) and
filters the ranked results by a case-insensitive keyword match against
`document_title` (`manual`, `oem`, `datasheet`, `spec sheet`, etc.) — a
practical proxy that produces useful results today without requiring an
architecture change mid-milestone. This is documented as a known
limitation rather than silently passed off as the real thing.

## Citation Validation

Same `[[chunk:<chunk_id>]]` marker convention as M9's
`synthesize_answer.yaml`, but folded directly into `format_response`
rather than a separate `validate_citations` node — the M10 checklist
specifies exactly five nodes (`classify_maintenance_query`,
`retrieve_asset_context`, `retrieve_work_orders`, `synthesize_guidance`,
`format_response`), so the same regex-based extraction, hallucination
filtering, and footnote-numbering logic from M9 lives inline in
`format_response` instead of its own node.

## Step Limit — the same lesson from M9, applied correctly from the start

M9's `KnowledgeBrainAgent` initially mutated `state["step_count"]` in place
inside `_check_step_limit`, discovered via testing to have no effect since
LangGraph only merges a node's *returned* dict. `MaintenanceBrainAgent` was
written with `_check_step_limit` returning the new count from the start,
and every node explicitly includes `"step_count": step_count` in its
return dict — all 29 unit tests (including the step-limit tests) passed on
the first run, no debugging needed this time.

## Session Persistence

Reuses the exact same `IChatHistoryRepository`/`RedisChatHistoryRepository`
singleton (`DIContainer.get_chat_history_repository()`) already shared
between `ChatUseCase` (M5) and `KnowledgeBrainAgent` (M9) — no new
persistence mechanism.

## Data Layer

- `migrations/versions/004_work_orders_m10.py` — `work_orders` table
  (`wo_id` PK, `asset_tag`, `description`, `status`, `priority`,
  `scheduled_date`, `completed_date`), indexed on `asset_tag` and `status`.
- `scripts/load_mock_cmms.py` — idempotent CSV loader (`INSERT ... ON
  CONFLICT (wo_id) DO UPDATE`), matching `scripts/init_infra.py`'s
  connection-handling convention (`DIContainer` directly, no FastAPI app).
- `scripts/mock_cmms_data.csv` — 10 demo work orders across 4 assets
  (`P-102A`, `FT-101`, `VLV-202`, `TK-301`), including the exact scenario
  the roadmap's demo test names (`P-102A` with 3 open/in-progress orders).

## Presentation Layer

```
POST /api/v1/brain/maintenance/chat
Auth: Bearer JWT (OAuth2PasswordBearer, same as M9's knowledge_brain endpoint)
Body: { "query": str, "session_id": str }
Response: { "answer": str, "asset_tag": str | null,
            "work_orders": [...], "failure_history": [...],
            "citations": [...], "session_id": str,
            "error_flag": bool, "step_count": int }
```

Unlike the Knowledge Brain's response, this includes the structured
`work_orders` and `failure_history` lists directly (not just the rendered
prose answer) so a UI can display them as their own panels alongside the
generated guidance text.

## Configuration

| Setting | Default |
|---------|---------|
| `MAINTENANCE_BRAIN_PROMPT_FILE` | `ai/prompts/maintenance_brain/synthesize_guidance.yaml` |
| `MAINTENANCE_BRAIN_MAX_STEPS` | `10` |
| `MAINTENANCE_BRAIN_TOP_K` | `5` |

Reuses `CHAT_MAX_TOKENS` / `CHAT_SESSION_TTL_SECONDS` (M5) for generation
and session TTL.

## Environment Notes

No new third-party dependencies — `langgraph` was already added to
`requirements.txt` in M9. Migration `004` was applied via
`alembic upgrade head`, and the mock CMMS CSV loaded via
`python scripts/load_mock_cmms.py` against the live Docker Postgres.
