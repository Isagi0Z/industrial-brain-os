# M9 Walkthrough — Knowledge Brain Agent (LangGraph)

## Overview

M9 introduces the first of five planned sub-brains: a LangGraph state machine
that wraps M8's `GraphRAGEngine` and M5's `IModelGateway` in a routed,
citation-validated, step-limited agent. This establishes the agent pattern
every subsequent sub-brain (Maintenance, Compliance, RCA, Lessons Learned)
will reuse.

```
POST /api/v1/brain/knowledge/chat
    │
    └─ KnowledgeBrainAgent.run(query, session_id, user_role)
            │
            ├─ route_query            (step 1 — step-limit check + logging;
            │                           classification lives in the edge
            │                           selector attached to this node)
            │
            ├── [document_search|procedural] ──► retrieve_context (step 2)
            │        │                                 │
            │        │                    entity_lookup ──► entity_lookup_tool
            │        │                    intent            + graph_search_tool
            │        │                                 │    (skips BM25/vector/rerank)
            │        │                    other intent ──► semantic_search_tool
            │        │                                      (= GraphRAGEngine.retrieve(), M8)
            │        │
            │        └── [unknown] ──────────────────────────────────┐
            │                                                        │
            │                                                        ▼
            └────────────────────────────────────────────► synthesize_answer (step 3)
                                                                      │
                                                       IModelGateway.generate() (M5)
                                                       + prior turn history (Redis, M5)
                                                                      │
                                                                      ▼
                                                          validate_citations (step 4)
                                                       [[chunk:<id>]] markers checked
                                                       against retrieved_chunks
                                                                      │
                                                                      ▼
                                                           format_response (step 5)
                                                       footnotes + Sources list
                                                                      │
                                                                      ▼
                                                                    END

Any node's tool/gateway exception → error_flag=True, node returns normally
(no raise) → conditional edge routes straight to format_response.

Step count > max_steps (10) → StepLimitExceededError raised, caught in
run(), produces a "STEP_LIMIT_EXCEEDED" answer instead of crashing.
```

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/knowledge_brain/models.py` (`AgentState` TypedDict), `domain/knowledge_brain/interfaces.py` (`IKnowledgeBrainAgent`) |
| Application | `application/knowledge_brain/knowledge_brain_agent.py` — the LangGraph `StateGraph` construction, all five node implementations, step-limit and error-fallback logic |
| Tool registry | `ai/agents/knowledge_brain/tools.py` — thin, independently-testable wrappers (`semantic_search_tool`, `graph_search_tool`, `entity_lookup_tool`, `document_lookup_tool`) around domain interfaces; no framework/DI imports |
| Prompt | `ai/prompts/knowledge_brain/synthesize_answer.yaml` |
| Presentation | `presentation/api/v1/endpoints/knowledge_brain.py` — `POST /api/v1/brain/knowledge/chat` |

LangGraph itself (`from langgraph.graph import StateGraph, END`) is used
directly inside the **application** layer, in the same spirit as
`asyncio.gather` is already used inside M8's `GraphRAGEngine` — it is a
pure in-process orchestration primitive with no DB/HTTP/ML-model surface,
unlike the concrete infrastructure clients (Postgres, Neo4j, Qdrant, Redis,
spaCy, sentence-transformers, Ollama/Gemini) that always live in
`infrastructure/`.

## Domain Model

```python
class AgentState(TypedDict):
    query: str
    session_id: str
    user_role: str
    retrieved_chunks: List[SearchResult]   # M4/M8 domain type
    kg_paths: List[KGPath]                 # M8 domain type
    draft_answer: str
    citations: List[Citation]              # M5 domain type
    step_count: int
    error_flag: bool
```

No new value types were introduced — `AgentState` composes existing domain
models from M4, M5, and M8, keeping the ubiquitous language consistent
across milestones.

## Routing — `_classify_intent`

A pure, deterministic function of the query text (no LLM call):

- Query contains an industrial tag pattern (`P-102A`, `FT101`, same regex
  family as M7's `SpacyEntityExtractor`) → `entity_lookup`
- Query contains a procedural keyword (`how to`, `steps to`, `procedure`,
  `instructions`, `walk me through`) → `procedural`
- Empty/whitespace-only query → `unknown`
- Otherwise → `document_search`

This is called from three places — the conditional edge attached to
`route_query`, and again inside `retrieve_context` and `synthesize_answer`
— rather than being stored as an extra `AgentState` field, since the M9
checklist specifies the state schema exactly and the function is cheap and
side-effect-free.

## Why `retrieve_context` branches on intent

- `entity_lookup`: the user already named a specific tag. Running the full
  hybrid pipeline (BM25 + vector + cross-encoder rerank) would be wasted
  work for a query that's really just "look up this one thing" — so
  `retrieve_context` calls `entity_lookup_tool` (spaCy tag extraction) +
  `graph_search_tool` (direct Neo4j traversal) instead, skipping
  `retrieved_chunks` entirely (`kg_paths` alone answers the question).
- `document_search` / `procedural`: calls `semantic_search_tool`, which is
  a one-line delegation to `GraphRAGEngine.retrieve()` (M8) — the full
  6-stage pipeline, including its own internal KG traversal.

## Citation Validation

The `synthesize_answer` prompt (`ai/prompts/knowledge_brain/synthesize_answer.yaml`)
instructs the model to cite using `[[chunk:<chunk_id>]]` markers — stricter
and more machine-verifiable than M5's free-text `[Title, p.N]` format,
because `validate_citations` needs to programmatically confirm every
citation maps to a real `chunk_id` in `retrieved_chunks`:

```python
for match in _CITATION_PATTERN.finditer(state["draft_answer"]):
    chunk_id = match.group(1)
    if chunk_id in by_chunk_id and chunk_id not in seen:
        # keep — build a Citation from the matching SearchResult
    # else: silently dropped — this is a hallucinated citation
```

`format_response` then replaces every *validated* marker with a numbered
footnote (`[1]`, `[2]`, ...) and appends a **Sources:** list; any
unvalidated `[[chunk:...]]` text is stripped rather than shown raw.

## Step Limit — an important implementation detail

LangGraph only merges the **dict a node returns** into its managed state —
mutating the `state` argument in place has no effect on what the next node
sees, even though `AgentState` is a plain (mutable) `TypedDict`. Every node
therefore calls `_check_step_limit(state)` (which returns the incremented
count rather than mutating `state`) and explicitly includes
`"step_count": step_count` in its own return dict. This was caught during
unit testing — the first version incremented `state["step_count"]` in
place and every test asserting `step_count` reported `0` regardless of how
many nodes had actually run.

`StepLimitExceededError` is raised outside any node's try/except (never
caught as a generic tool failure), so it propagates out of
`self._graph.ainvoke(...)` and is caught once in `run()`.

## Fallback Behavior

Every node wraps its "risky" work (a `GraphRAGEngine`/`IModelGateway`/tool
call) in `try/except Exception`. On failure: log the error, return
`{"error_flag": True, "step_count": step_count}` — no raise. Every
outgoing conditional edge checks `error_flag` first and routes straight to
`format_response` if it's set, so a single tool failure degrades to a
partial, clearly-flagged answer rather than crashing the request.

## Session Persistence

`KnowledgeBrainAgent` takes the *same* `IChatHistoryRepository` used by M5's
`ChatUseCase` (now shared via `DIContainer.get_chat_history_repository()`,
extracted as a singleton this milestone). `run()` calls
`self._history.append_messages(session_id, [user_msg, assistant_msg], ttl)`
after every turn, and `synthesize_answer` reads
`self._history.get_history(session_id)` to include prior turns in the LLM
message list — no new persistence mechanism was introduced; the roadmap's
"state accumulates across turns via Redis session" requirement is satisfied
by reusing M5's existing Redis-backed history, not by making LangGraph's
own checkpointer Redis-backed (out of scope for this milestone).

## Presentation Layer

```
POST /api/v1/brain/knowledge/chat
Auth: Bearer JWT (OAuth2PasswordBearer, same as /api/v1/search/*)
Body: { "query": str, "session_id": str }
Response: { "answer": str, "citations": [...], "session_id": str,
            "error_flag": bool, "step_count": int }
```

`user_role` is resolved server-side from the authenticated user's first
`Role.name` (defaulting to `"public"`), never taken from the request body —
this is deliberately stricter than the M5/M8 `/api/v1/chat` endpoint, which
still accepts a client-supplied `role_scope`.

## Configuration

| Setting | Default |
|---------|---------|
| `KNOWLEDGE_BRAIN_PROMPT_FILE` | `ai/prompts/knowledge_brain/synthesize_answer.yaml` |
| `KNOWLEDGE_BRAIN_MAX_STEPS` | `10` |
| `KNOWLEDGE_BRAIN_TOP_K` | `5` |

Reuses `GRAPHRAG_MAX_KG_DEPTH` / `GRAPHRAG_KG_TRAVERSAL_LIMIT` (M8) for its
own KG traversal calls, and `CHAT_MAX_TOKENS` / `CHAT_SESSION_TTL_SECONDS`
(M5) for generation and session TTL.

## Environment Notes

- `langgraph>=0.2.0` added to `requirements.txt` (installed as 0.6.11 in
  this sandbox — pure-Python, installed cleanly with prebuilt wheels).
- Found and fixed a pre-existing path-resolution bug affecting M5 and M7
  (see the roadmap's M9 entry for detail) — `backend/ai/prompts/*.yaml`
  files were resolving one directory level too high.
