# M13 Summary — Lessons Learned Brain Agent

**Milestone**: M13
**Status**: ✅ Complete
**Date**: 2026-07-02

## Delivered

M13 is the fifth and final planned sub-brain, closing the "knowledge
cliff" gap from the problem statement: past incidents are captured once
(`POST /api/v1/incidents`) and proactively resurfaced — without being
asked — whenever a later Knowledge Brain query resembles one closely
enough (`similarity > 0.85`). It also exposes a dedicated Q&A endpoint
over the lessons themselves, `POST /api/v1/brain/lessons/chat`.

### Domain Layer
- `Incident`, `LessonLearned`, `LessonLinkResult`, `LessonsAgentState`
  (`domain/lessons_brain/models.py`)
- `ILessonRepository`, `IProactiveWarningDetector`,
  `ILessonsLearnedBrainAgent` (`domain/lessons_brain/interfaces.py`)
- `ProactiveWarning` value object added to the shared `domain/chat/models.py`
- `AgentState.proactive_warning` (additive field) on the M9 Knowledge
  Brain's domain model

### Application Layer
- `LessonsLearnedBrainAgent` — a compiled LangGraph `StateGraph`
  (`analyze_incident → extract_patterns → link_to_ontology → store_lesson
  → generate_summary`) driving `ingest_incident()`, plus a direct
  (non-graph) `chat()` method for the lessons-only Q&A endpoint
- `KnowledgeBrainAgent` (M9) — additive `warning_detector` wiring inside
  the existing `_format_response` node; no graph-topology change

### Infrastructure Layer
- `Neo4jLessonRepository` — `LessonLearned` node MERGE + `RELATED_TO`/
  `REFERENCES` edges against existing Equipment/FailureMode nodes only,
  reporting actual link outcomes (Neo4j write-summary counters), not
  assumed ones
- `ProactiveWarningDetector` — embed query → search the `lessons_learned`
  Qdrant collection (role-scoped) → threshold check → resolve the
  canonical lesson from Neo4j
- `infra_init.py` — `lessons_learned` Qdrant collection (1024-dim,
  cosine, `role_scope`/`document_id` payload indexes) +
  `lesson_learned_id_unique` Neo4j constraint, both idempotent at startup

### Tool Registry
- `failure_pattern_match` (reuses M10's `Neo4jFailureHistoryRepository`
  verbatim), `find_similar_lessons` (reuses M4's `IVectorRepository`/
  `IEmbeddingService` against the new collection), `generate_lesson_summary`,
  `synthesize_chat_answer`

### Prompt Engineering (ADR-020)
- `generate_summary.yaml`, `chat_answer.yaml` — version-controlled

### Presentation Layer
- `POST /api/v1/incidents` — JWT-authenticated; 201 with the stored
  `LessonLearned` (including honestly-reported `equipment_linked` /
  `failure_modes_linked`)
- `POST /api/v1/brain/lessons/chat` — JWT-authenticated Q&A over ingested
  lessons only
- `POST /api/v1/brain/knowledge/chat` (M9) — response schema extended with
  `proactive_warning`

### Ontology
- `LessonLearned` node type + `RELATED_TO(Equipment)` /
  `REFERENCES(FailureMode)` relations added to `industrial_ontology.yaml`
  (M6 schema, now 12 node types)

## Files Created

```
backend/app/domain/lessons_brain/{__init__,models,interfaces}.py
backend/app/application/lessons_brain/{__init__,lessons_brain_agent}.py
backend/app/infrastructure/lessons/{__init__,lesson_repository,proactive_warning_detector}.py
backend/ai/agents/lessons_brain/{__init__,tools}.py
backend/ai/prompts/lessons_brain/{generate_summary,chat_answer}.yaml
backend/app/presentation/api/v1/endpoints/{incidents,lessons_brain}.py
backend/tests/test_lessons_brain.py
docs/walkthroughs/m13_walkthrough.md
docs/verification/m13_verification.md
docs/reports/m13_summary.md
```

## Files Modified

```
backend/app/domain/chat/models.py                    — +ProactiveWarning
backend/app/domain/knowledge_brain/models.py          — AgentState +proactive_warning field
backend/app/application/knowledge_brain/knowledge_brain_agent.py
                                                       — +warning_detector param; _format_response
                                                         prepends the warning (additive, no new graph node)
backend/app/presentation/api/v1/endpoints/knowledge_brain.py
                                                       — response schema +proactive_warning
backend/app/infrastructure/database/infra_init.py     — +lessons_learned Qdrant collection, +Neo4j constraint
backend/app/infrastructure/di/container.py            — +get_lesson_repository(), +get_proactive_warning_detector(),
                                                         +get_lessons_brain_agent(); knowledge_brain_agent wired with warning_detector
backend/app/infrastructure/config/settings.py         — +LESSONS_* settings (2 prompt files, max_steps,
                                                         similar_lessons_limit, chat_top_k, similarity_threshold)
backend/app/presentation/api/v1/router.py             — registered incidents.router, lessons_brain.router
backend/tests/test_ontology.py                        — node-type count 11→12; required_types +LessonLearned
ontology/industrial_ontology.yaml                     — +LessonLearned node type, +2 relations
docs/implementation_roadmap.md                        — M13 checklist all [x]; commit SHA TBD
```

## Key Technical Decisions

- **No new LangGraph orchestration, repository base pattern, or GraphRAG
  code.** `analyze_incident` reuses M10's `IFailureHistoryRepository`
  verbatim; `find_similar_lessons` reuses M4's `IVectorRepository`
  unmodified (it already parameterizes `collection_name`); ontology
  conformance reuses M6's `IOntologyValidator`.
- **Proactive warning is an additive change to M9's `_format_response`
  node, not a new graph branch.** A new optional constructor parameter
  defaulting to `None` keeps every existing instantiation/test
  unaffected; the detector call is wrapped in its own try/except so a
  detector failure never surfaces to the user or blocks the underlying
  answer. See the walkthrough for the full reasoning.
- **`equipment_linked`/`failure_modes_linked` reflect actual Neo4j write
  outcomes**, read from the write summary's `relationships_created`
  counter — not assumed from the presence of an `asset_tag` string —
  since the referenced Equipment/FailureMode node may not exist yet.
- **No new Postgres migration.** The roadmap checklist specifies Neo4j
  (graph) + Qdrant (embeddings) as `LessonLearned`'s persistence, unlike
  M11/M12's audit-trail tables — Neo4j is treated as the source of truth,
  with `Neo4jLessonRepository.get()` resolving the canonical record when
  the proactive detector needs full lesson details beyond the Qdrant hit.
- **`/brain/lessons/chat` is a direct semantic search, not a duplicate
  GraphRAG pipeline** — it only ever needs to answer from the
  `lessons_learned` collection, so reusing the full M8 hybrid-retrieval
  engine would be unjustified complexity (Engineering Bible §1).

## Blockers Encountered and How They Were Resolved

- **Fitting a `LessonLearned` hit into the shared `SearchResult` model**
  without adding fields no other collection needs — resolved by treating
  Qdrant purely as the similarity index (point id = `lesson_id`, minimal
  payload) and always resolving full lesson details (summary,
  incident_date, etc.) from Neo4j via `ILessonRepository.get()` once a
  match crosses the threshold, rather than denormalizing everything into
  Qdrant's payload.
- **Reporting real vs. assumed graph links** — the first draft passed a
  `link_equipment: bool` the agent had to guess; replaced with
  `LessonLinkResult`, populated from the Neo4j write summary's
  `relationships_created` counters, so the API response never overclaims.
- **A pre-existing `test_ontology.py` assertion hard-coded the node-type
  count (`== 11`)** — updating it to `12` (and adding `LessonLearned` to
  the required-types set) was necessary and in-scope, since the M13
  checklist explicitly requires the ontology extension the test now
  reflects.
- **Passlib/bcrypt incompatibility in the dev seeder** blocked
  `POST /api/v1/auth/login` for live E2E testing — unrelated to M13
  (affects every milestone's auth equally); worked around for this
  session's manual verification with a directly minted JWT rather than
  modifying the auth dependency stack.

## Test Results

- **21 new M13 unit tests** (`test_lessons_brain.py`) — all pass, first
  run after resolving an unrelated pytest `tmp_path` environment issue
- **312 total backend tests pass** across the full suite (unit +
  integration) — 0 failures, 0 errors
- Live E2E against the real Docker stack + real Ollama (`mistral:latest`):
  ingested a real bearing-failure incident for P-102A, confirmed the
  LLM-generated summary, then confirmed the Knowledge Brain's
  `/brain/knowledge/chat` correctly prepends the structured
  `LESSONS_LEARNED` warning (`similarity_score: 1.0`) when queried with
  matching phrasing, and correctly withholds it for a loosely paraphrased
  query that falls below the 0.85 threshold — proving the discrimination
  is working as designed, not just firing unconditionally. RBAC verified
  (401 on both new endpoints without a token). Details in the
  verification report.

## What M13 Unlocks

M13 completes all five planned sub-brains (Knowledge, Maintenance,
Compliance, RCA, Lessons Learned) from the architecture's Phase 3 roadmap.
Nothing blocks on M13 (`Blocks: None`). The remaining Phase 3 items —
M14 (compression/citation-validation pipeline stages), M15 (event-driven
async ingestion), M16 (evaluation layer) — and the Final Demo phase (M17+)
are unblocked and ready to begin in a future session, each requiring
explicit approval per the one-milestone-per-session workflow rule.
