# M12 Walkthrough — RCA Brain Agent (LangGraph, 5-Whys + Fishbone)

## Overview

M12 is the fourth of five planned sub-brains. Unlike the single-shot
Knowledge (M9), Maintenance (M10), and Compliance (M11) brains, the RCA
Brain is **session-based and human-in-the-loop**: it guides a reliability
engineer through an interactive 5-Whys investigation across multiple HTTP
requests, then produces a structured, Pydantic-validated `RCAReport`
combining the converged root cause with a parallel Fishbone (Ishikawa 6M)
analysis. Failure history comes from Neo4j (reusing M10's `EXHIBITS`
repository) and incident history from the Postgres `work_orders` table
(reusing M10's data).

```
POST /api/v1/brain/rca/session      (no session_id -> start; session_id+answer -> advance)
    │
    ├─ start_session(session_id, asset_tag, incident_description)
    │      → _run_turn(is_complete=False)
    │          define_problem → decide → suggest_why → [interrupt_before] human_confirm
    │          (returns the FIRST "why?"; status AWAITING_INPUT)
    │      → persist session to Redis (live state) + Postgres (audit)
    │
    └─ advance_session(session_id, human_answer)
           → load live state from Redis (stateless service — §28)
           → record answer against the open why
           → answered whys >= max_whys ?
                NO  → _run_turn(is_complete=False): suggest next why, pause again
                YES → _run_turn(is_complete=True):
                        define_problem → decide → identify_root_cause → generate_report
                        (GraphRAG evidence + parallel Fishbone + validated RCAReport)
                        status COMPLETED; report persisted to Postgres; Redis state cleared
```

## Human-in-the-Loop: a deliberate architecture choice

The roadmap checklist asks for "LangGraph `interrupt_before` at
human-in-the-loop nodes" and "session state persisted in LangGraph
checkpoint store (Redis-backed) enabling resume after human input." Both
intents are honored, but the durable cross-request mechanism is **not**
LangGraph's own checkpointer, for two concrete reasons discovered during
implementation:

1. **The official `langgraph-checkpoint-redis` requires the RedisJSON /
   RediSearch modules**, which the plain `redis:7.2-alpine` deployment does
   not provide. It cannot run against this infrastructure.
2. **An in-process `MemorySaver` would make the service stateful** —
   resume would break across process restarts or multiple uvicorn workers,
   violating Engineering Bible §28 ("Design all services to be stateless to
   support horizontal scaling").

So the design keeps the FastAPI service stateless: durable session
working-state (the whys chain + status) lives in a **Redis-backed store**
(`RedisRCAStateStore`, `IRCASessionStateStore`) and the audit record + final
report live in **Postgres** (`rca_sessions`, `PostgresRCASessionRepository`).
The LangGraph graph is still genuinely compiled with
`interrupt_before=["human_confirm"]` and a `MemorySaver`, so the 5-Whys
pause point is a real LangGraph interrupt — each `_run_turn` invocation runs
the graph up to and pauses before `human_confirm` (returning the suggested
why), or runs the root-cause/report path to completion. Cross-request
continuity is provided by reloading the durable session and re-invoking with
the accumulated whys, rather than relying on an in-process checkpoint. This
is the more robust interpretation of the requirement, and it is documented
here and in the verification report rather than silently substituted.

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/rca_brain/models.py` (`RCAStatus`, `FishboneCategory`, `WhyStep`, `RCAReport`, `RCASession`, `RCAAgentState`), `domain/rca_brain/interfaces.py` (`IIncidentHistoryRepository`, `IRCASessionRepository`, `IRCASessionStateStore`, `IRCABrainAgent`) |
| Application | `application/rca_brain/rca_brain_agent.py` — the LangGraph state machine + `start_session`/`advance_session` orchestration |
| Infrastructure | `infrastructure/rca/incident_history_repository.py`, `rca_session_repository.py`, `redis_rca_state_store.py`, `serialization.py` |
| Tool registry | `ai/agents/rca_brain/tools.py` |
| Prompts | `ai/prompts/rca_brain/suggest_why.yaml`, `generate_report.yaml`, `fishbone.yaml` |
| Presentation | `presentation/api/v1/endpoints/rca_brain.py` — `POST /api/v1/brain/rca/session` |
| Data | `migrations/versions/006_rca_sessions_m12.py` |

## Domain Model

`RCAReport` is a **Pydantic model** (like M11's `ComplianceGapReport`)
because the LLM-generated report is parsed and validated against a schema
rather than trusted as free text (Engineering Bible §33). The five required
fields plus a `fishbone` map and a timestamp:

```python
class RCAReport(BaseModel):
    problem_statement: str
    root_cause: str
    contributing_factors: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    evidence_citations: List[str] = Field(default_factory=list)
    fishbone: Dict[str, List[str]] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=...)
```

`RCASession`/`WhyStep`/`RCAAgentState` stay dataclasses / TypedDict
(matching M9–M11 state conventions); only the LLM-output boundary uses
Pydantic.

## Tool Registry (`ai/agents/rca_brain/tools.py`)

| Tool | Backing interface | Behavior |
|------|-------------------|----------|
| `failure_pattern_search` | `IFailureHistoryRepository` (reused from M10) | `(Equipment)-[:EXHIBITS]->(FailureMode)` records for the asset |
| `incident_history_search` | `IIncidentHistoryRepository` | Historical `work_orders` whose description matches keywords extracted from the incident |
| `extract_keywords` | pure | Salient-term extraction (drops stop words + domain-generic words like "failure") for incident matching |
| `suggest_next_why` | `IModelGateway` | One LLM call: the next "why?" grounded in incident + prior whys + failure/incident evidence |
| `fishbone_analysis` | `IGraphRAGEngine` + `IModelGateway` | **Six concurrent branches** (`asyncio.gather` over the 6M categories), each retrieving category-relevant chunks (GraphRAG, M8) and listing candidate causes; a branch failure is isolated to an empty list for that category |
| `parse_report_object` | pure | Extracts a JSON **object** (the RCA report) via the same 3-strategy parse as M7/M11 (direct → balanced-brace extraction → fence stripping) |

`failure_pattern_search` and the `WorkOrder` incident model are **reused
from M10** — no duplicate failure/work-order code was written. The
`work_orders` table is queried through a new focused
`PostgresIncidentHistoryRepository` (description `ILIKE` search) so M10's
files stay untouched.

## The 5-Whys Graph

One compiled `StateGraph` serves both turn types via an `is_complete` flag:

```
define_problem        gather failure patterns (Neo4j) + incident history (Postgres)
   │  (conditional: is_complete?)
   ├── no  → suggest_why → [interrupt_before] human_confirm → END
   └── yes → identify_root_cause → generate_report → END
```

- **`define_problem`** populates `failure_patterns` and `incident_history`
  in state (the "at each suggest_why node, query Neo4j failure patterns"
  requirement — evidence is gathered up front each turn and fed to the
  suggest/report LLM calls).
- **`suggest_why`** asks the LLM for the next why; the graph then pauses
  before `human_confirm` (a no-op HITL boundary node) via `interrupt_before`.
- **`identify_root_cause`** retrieves root-cause evidence chunks and runs the
  parallel Fishbone analysis.
- **`generate_report`** produces the JSON report, validates every
  `[[chunk:<id>]]` citation against the retrieved evidence chunk_ids (and
  every failure-code citation against the known failure codes), dropping
  hallucinated references — the same citation-validation contract as
  M9/M10/M11 — and attaches the Fishbone map.

Step counting follows the M9 lesson (LangGraph merges only a node's
returned dict, so every node returns its incremented `step_count`); the
5-Whys iteration is bounded at the application level by `max_whys` (default
5), and each turn's graph run is bounded by `max_steps` (§21 — no unbounded
loops).

## Session Persistence

- **Redis** (`RedisRCAStateStore`, key `rca:session:<id>`, TTL from
  `CHAT_SESSION_TTL_SECONDS`): the live working state (whys chain + status),
  enabling resume after human input without in-process state. Cleared once
  the report completes.
- **Postgres** (`rca_sessions`: `session_id`, `asset_tag`,
  `incident_description`, `status`, `rca_report_json`, `created_at`): the
  durable audit record. `rca_report_json` is populated on completion.

Both use a shared `serialization.py` so the two stores never drift.

## Presentation Layer

```
POST /api/v1/brain/rca/session
Auth: Bearer JWT (OAuth2PasswordBearer, same as M9–M11)

Start:   { "asset_tag": str, "incident_description": str }
Advance: { "session_id": str, "answer": str }

Response: { session_id, asset_tag, incident_description, status,
            whys: [{question, answer}], next_why: str|null,
            report: { problem_statement, root_cause, contributing_factors[],
                      recommended_actions[], evidence_citations[],
                      fishbone{}, generated_at } | null }
```

A request without `session_id` starts a new session (422 if
asset_tag/incident_description missing); a request with `session_id`
advances it (422 if `answer` missing, 404 if the session's live state has
expired). `user_role` is resolved server-side from the authenticated user.

## Configuration

| Setting | Default |
|---------|---------|
| `RCA_SUGGEST_WHY_PROMPT_FILE` | `ai/prompts/rca_brain/suggest_why.yaml` |
| `RCA_GENERATE_REPORT_PROMPT_FILE` | `ai/prompts/rca_brain/generate_report.yaml` |
| `RCA_FISHBONE_PROMPT_FILE` | `ai/prompts/rca_brain/fishbone.yaml` |
| `RCA_BRAIN_MAX_STEPS` | `10` |
| `RCA_BRAIN_MAX_WHYS` | `5` |
| `RCA_BRAIN_TOP_K` | `5` |
| `RCA_INCIDENT_HISTORY_LIMIT` | `5` |

## Environment Notes

No new third-party dependencies — `langgraph` and `pydantic` were already
present. Migration `006` (`rca_sessions`) applied via `alembic upgrade
head`. The `work_orders` table (M10) is reused as incident history; the
mock CMMS loader from M10 populates demo rows.
