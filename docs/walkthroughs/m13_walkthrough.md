# M13 Walkthrough — Lessons Learned Brain Agent

## Overview

M13 is the fifth and final planned sub-brain. It closes the "knowledge
cliff" gap called out in the problem statement: post-incident lessons are
captured once (`POST /api/v1/incidents`), then surfaced proactively —
without the user having to ask — whenever a later query resembles a past
incident closely enough. Two integration points exist:

1. **Ingestion** — a five-node LangGraph pipeline
   (`analyze_incident → extract_patterns → link_to_ontology → store_lesson
   → generate_summary`) turns a raw incident report into a durable
   `LessonLearned` record (Neo4j node + Qdrant embedding).
2. **Proactive warning** — a lightweight, non-LLM detector
   (`ProactiveWarningDetector`) is consulted by the **Knowledge Brain
   (M9)** on every `/brain/knowledge/chat` call; if the query's embedding
   is more than `0.85` cosine-similar to a stored lesson, a structured
   warning is prepended to the Knowledge Brain's answer.

```
POST /api/v1/incidents
    │
    └─ LessonsLearnedBrainAgent.ingest_incident(Incident)
           analyze_incident   → M10 reuse: (Equipment)-[:EXHIBITS]->(FailureMode)
                                 candidates for this asset_tag
           extract_patterns   → semantic search of `lessons_learned` Qdrant
                                 collection for recurrence awareness
           link_to_ontology   → validate LessonLearned node/relation types
                                 against industrial_ontology.yaml (M6)
           store_lesson       → embed description (BGE-large, 1024-dim);
                                 upsert to Qdrant `lessons_learned`;
                                 MERGE LessonLearned node in Neo4j +
                                 attempt RELATED_TO(Equipment) /
                                 REFERENCES(FailureMode) edges
           generate_summary   → one LLM call → 1-2 sentence warning text;
                                 patched onto the Neo4j node
           → returns LessonLearned{lesson_id, equipment_linked, failure_modes_linked, summary, ...}

POST /api/v1/brain/knowledge/chat  (M9, unchanged graph topology)
    │
    └─ KnowledgeBrainAgent._format_response  (every path reaches this node)
           → run_in_threadpool(warning_detector.detect, query, role_scope)
                 embed query → search `lessons_learned` (role-scoped)
                 → score > 0.85 ? lesson_repo.get(chunk_id) : None
           → if warning: prepend {warning_type, lesson_summary,
                                    similarity_score, incident_date, asset_tag}
                          to the rendered answer AND to the JSON response

POST /api/v1/brain/lessons/chat
    │
    └─ LessonsLearnedBrainAgent.chat(query, session_id, role)
           → semantic search `lessons_learned` only (not the full
             document corpus — this sub-brain only ever answers from
             ingested incidents) → one LLM synthesis call
```

## Reuse, not duplication

Per the roadmap's explicit instruction, M13 introduces **zero** new
LangGraph orchestration primitives, repository base patterns, or GraphRAG
code:

- **Step-limited graph pattern** — same `_check_step_limit` /
  `error_flag` / `_error_or(default=...)` conditional-edge shape as
  M9–M12.
- **`(Equipment)-[:EXHIBITS]->(FailureMode)` lookup** — `analyze_incident`
  calls the *exact same* `IFailureHistoryRepository.search_by_asset_tag`
  used by M10's Maintenance Brain and M12's RCA Brain; no new Neo4j query
  was written for failure-mode candidates.
- **`IVectorRepository`** (M4) is reused unmodified for the new
  `lessons_learned` Qdrant collection — the interface already parameterizes
  `collection_name`, so no new vector-repository class was needed.
- **Ontology validation** — `link_to_ontology` calls the existing
  `IOntologyValidator` (M6) rather than hand-rolling schema checks.
- **Prompt-loading, citation, and JSON-parsing helpers** follow the same
  shape as `ai/agents/rca_brain/tools.py` / `compliance_brain/tools.py`.

## A deliberate architecture choice: no new graph branch on the Knowledge Brain

The roadmap requires "if similarity > 0.85, prepend warning to Knowledge
Brain responses." The literal instruction could be read as adding a new
LangGraph node/branch to M9's `KnowledgeBrainAgent`. Instead, the
detector is invoked directly inside the **existing** `_format_response`
node — the one node every path already reaches, including the error path
— for two reasons:

1. `_format_response` already performs response-shaping (citation
   footnotes, error-note prepending); a proactive-warning prepend is the
   same category of concern, not a new retrieval/synthesis step.
2. Adding a new conditional-edge branch to M9's tested graph topology for
   a value-add feature would be exactly the kind of "redesign the
   architecture" the Engineering Bible prohibits for the sake of a smaller
   change. The chosen approach is additive: a new optional constructor
   parameter (`warning_detector: IProactiveWarningDetector | None = None`,
   defaulting to `None` so any existing test/instantiation is unaffected)
   and one `await run_in_threadpool(...)` call wrapped in its own
   try/except (ADR-001 — blocking embedding/vector calls off the event
   loop; a detector failure is logged and swallowed, never surfacing to
   the user).

`AgentState` gained one additive field, `proactive_warning: Optional[...]`,
and the new `ProactiveWarning` value object lives in the shared
`domain/chat/models.py` (alongside `Citation`) rather than in
`domain/lessons_brain`, to avoid the Knowledge Brain's domain layer
importing another sub-brain's domain package.

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/lessons_brain/models.py` (`Incident`, `LessonLearned`, `LessonLinkResult`, `LessonsAgentState`), `domain/lessons_brain/interfaces.py` (`ILessonRepository`, `IProactiveWarningDetector`, `ILessonsLearnedBrainAgent`); `domain/chat/models.py` gains `ProactiveWarning`; `domain/knowledge_brain/models.py` gains `AgentState.proactive_warning` |
| Application | `application/lessons_brain/lessons_brain_agent.py` — the ingestion LangGraph + `chat()`; `application/knowledge_brain/knowledge_brain_agent.py` — additive `warning_detector` wiring in `_format_response` |
| Infrastructure | `infrastructure/lessons/lesson_repository.py` (Neo4j), `infrastructure/lessons/proactive_warning_detector.py`; `infrastructure/database/infra_init.py` gains the `lessons_learned` Qdrant collection + `LessonLearned.lesson_id` Neo4j constraint |
| Tool registry | `ai/agents/lessons_brain/tools.py` |
| Prompts | `ai/prompts/lessons_brain/generate_summary.yaml`, `chat_answer.yaml` |
| Presentation | `presentation/api/v1/endpoints/incidents.py` (`POST /api/v1/incidents`), `presentation/api/v1/endpoints/lessons_brain.py` (`POST /api/v1/brain/lessons/chat`); `presentation/api/v1/endpoints/knowledge_brain.py` response schema gains `proactive_warning` |
| Ontology | `ontology/industrial_ontology.yaml` gains the `LessonLearned` node type and the `RELATED_TO(Equipment)` / `REFERENCES(FailureMode)` relations |
| Data | No new Postgres migration — `LessonLearned` is Neo4j + Qdrant only (no audit-trail table was specified in the checklist, unlike M11/M12) |

## Domain Model

```python
@dataclass
class Incident:                       # raw POST /api/v1/incidents body
    asset_tag: str
    incident_date: date
    description: str
    root_cause: str
    corrective_actions: List[str]
    severity: str = "MEDIUM"
    role_scope: str = "public"

@dataclass
class LessonLearned:                   # durable record — Neo4j is source of truth
    lesson_id: str
    asset_tag: str
    incident_date: date
    description: str
    root_cause: str
    corrective_actions: List[str]
    severity: str
    role_scope: str = "public"
    summary: str = ""
    equipment_linked: bool = False
    failure_modes_linked: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=...)

@dataclass
class LessonLinkResult:                # what the Neo4j write actually linked
    equipment_linked: bool
    failure_modes_linked: List[str]
```

`equipment_linked` / `failure_modes_linked` are **not** guessed by the
agent — `Neo4jLessonRepository.create()` reads the Neo4j write summary's
`relationships_created` counter for each attempted `MATCH ... MERGE` and
reports only edges that actually landed, since an incident's `asset_tag`
or a failure code may not yet exist as a graph node.

## The Ingestion Graph

```
analyze_incident     M10 reuse: search_by_asset_tag → failure_mode_candidates
   │ (conditional: error_flag?)
extract_patterns     semantic search lessons_learned (recurrence awareness)
   │
link_to_ontology     IOntologyValidator.validate_node/validate_relation
   │
store_lesson         embed description → Qdrant upsert; Neo4j MERGE + edges
   │
generate_summary     one LLM call → summary; Neo4j SET (non-fatal on failure)
   │
  END
```

Every node follows the `_check_step_limit` / try-except / `error_flag`
convention from M9–M12; `_error_or(default=...)` conditional edges skip
straight to `END` on error — there is no separate `format_report` node
because ingestion either succeeds (durable lesson) or the whole request
fails (`IncidentProcessingError` → HTTP 500), unlike the Q&A brains where
a partial answer is still useful. **`generate_summary` failure is the one
deliberate exception**: the lesson is already durably stored by
`store_lesson`, so a summary-generation failure (e.g. the LLM gateway is
unreachable) degrades to an empty `summary` rather than discarding the
already-persisted lesson.

## Presentation Layer

```
POST /api/v1/incidents
Auth: Bearer JWT
Body: { asset_tag, incident_date, description, root_cause,
        corrective_actions[], severity, role_scope? }
201 → { lesson_id, asset_tag, incident_date, description, root_cause,
        corrective_actions[], severity, summary, equipment_linked,
        failure_modes_linked[], created_at }
500 → incident processing failed (ontology violation, step-limit, etc.)

POST /api/v1/brain/lessons/chat
Auth: Bearer JWT
Body: { query, session_id }
200 → { answer, citations[], session_id, error_flag, step_count }

POST /api/v1/brain/knowledge/chat   (M9, response schema extended)
200 → { answer, citations[], session_id, error_flag, step_count,
        proactive_warning: { warning_type, lesson_summary,
                              similarity_score, incident_date,
                              asset_tag, lesson_id } | null }
```

All three routes require the same `Depends(get_current_user)` RBAC as
every other brain endpoint (Engineering Bible §15); unauthenticated
requests return 401 (verified in the E2E gate).

## Configuration

| Setting | Default |
|---------|---------|
| `LESSONS_GENERATE_SUMMARY_PROMPT_FILE` | `ai/prompts/lessons_brain/generate_summary.yaml` |
| `LESSONS_CHAT_PROMPT_FILE` | `ai/prompts/lessons_brain/chat_answer.yaml` |
| `LESSONS_BRAIN_MAX_STEPS` | `10` |
| `LESSONS_SIMILAR_LESSONS_LIMIT` | `3` |
| `LESSONS_BRAIN_CHAT_TOP_K` | `5` |
| `LESSONS_WARNING_SIMILARITY_THRESHOLD` | `0.85` |

## Environment Notes

No new third-party dependencies — `langgraph`, `qdrant-client`, and
`neo4j` were already present. No new Postgres migration. The
`lessons_learned` Qdrant collection (1024-dim, cosine, `role_scope` +
`document_id` payload indexes) is created idempotently at startup by
`infra_init.py`, matching the M1/M4 `document_chunks` pattern. A known,
pre-existing environment gap (unrelated to M13): the dev seeder's
`admin@industrialbrain.local` bootstrap fails under the currently
installed `passlib`/`bcrypt` combination (`password cannot be longer than
72 bytes` — a documented passlib/bcrypt>=4.1 incompatibility), so manual
E2E verification in this session used a directly-minted JWT rather than
`/api/v1/auth/login`. This is outside M13's scope and does not affect any
M13 code path.
