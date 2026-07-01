# M9 Summary — Knowledge Brain Agent (LangGraph)

**Milestone**: M9
**Status**: ✅ Complete
**Date**: 2026-07-01

## Delivered

M9 builds the first of five planned sub-brains: a LangGraph state machine
(`route_query → retrieve_context → synthesize_answer → validate_citations
→ format_response`) that wraps M8's `GraphRAGEngine` and M5's
`IModelGateway`/session history into a routed, citation-validated,
step-limited agent exposed at `POST /api/v1/brain/knowledge/chat`. This
establishes the reusable agent pattern for the Maintenance, Compliance,
RCA, and Lessons Learned sub-brains still to come.

### Domain Layer
- `AgentState` TypedDict — composes existing M4/M5/M8 domain types (`SearchResult`, `KGPath`, `Citation`) rather than inventing new ones
- `IKnowledgeBrainAgent` interface

### Application Layer
- `KnowledgeBrainAgent` — LangGraph `StateGraph` construction and all five node implementations; deterministic (non-LLM) intent classification for routing; branches `retrieve_context` between a full `GraphRAGEngine` hybrid search and a cheaper direct entity/graph lookup depending on intent; regex-based `[[chunk:<id>]]` citation extraction and hallucination filtering; step-limit enforcement via each node's return value (LangGraph merges returns, not in-place state mutation — caught via unit testing)

### Tool Registry
- `ai/agents/knowledge_brain/tools.py` — `semantic_search_tool`, `graph_search_tool`, `entity_lookup_tool`, `document_lookup_tool`, each a pure function over an injected domain interface, independently unit-tested (including one test against the real M7 `SpacyEntityExtractor`)

### Prompt Engineering (ADR-020)
- `ai/prompts/knowledge_brain/synthesize_answer.yaml` — system + user + uncertain templates; stricter `[[chunk:<id>]]` citation format than M5's free-text style, chosen specifically so citations can be programmatically verified

### Presentation Layer
- `POST /api/v1/brain/knowledge/chat` — JWT-authenticated, `user_role` resolved server-side from the authenticated user (never client-supplied), verified live to return 401 when unauthenticated

### DI Wiring
- `DIContainer.get_knowledge_brain_agent()` — wires `GraphRAGEngine` (M8), `SpacyEntityExtractor`/`Neo4jKGTraversalService` (shared singletons from M7/M8), a fresh `IModelGateway`, and the chat history repository
- Extracted `get_chat_history_repository()` as a shared singleton, now used by both `ChatUseCase` (M5) and `KnowledgeBrainAgent` (M9)

## Files Created

```
backend/app/domain/knowledge_brain/__init__.py
backend/app/domain/knowledge_brain/models.py
backend/app/domain/knowledge_brain/interfaces.py
backend/app/application/knowledge_brain/__init__.py
backend/app/application/knowledge_brain/knowledge_brain_agent.py
backend/ai/__init__.py
backend/ai/agents/__init__.py
backend/ai/agents/knowledge_brain/__init__.py
backend/ai/agents/knowledge_brain/tools.py
backend/ai/prompts/knowledge_brain/synthesize_answer.yaml
backend/app/presentation/api/v1/endpoints/knowledge_brain.py
backend/tests/test_knowledge_brain.py
docs/walkthroughs/m9_walkthrough.md
docs/verification/m9_verification.md
docs/reports/m9_summary.md
```

## Files Modified

```
backend/app/infrastructure/di/container.py
backend/app/infrastructure/config/settings.py
backend/app/presentation/api/v1/router.py
backend/requirements.txt
docs/implementation_roadmap.md
```

## Key Technical Decisions

- **LangGraph lives in the application layer, not infrastructure.** It's an
  in-process orchestration primitive (like `asyncio.gather`, already used
  this way in M8's `GraphRAGEngine`) with no DB/HTTP/ML-model surface,
  unlike every other concrete client in this codebase (Postgres, Neo4j,
  Qdrant, Redis, spaCy, sentence-transformers, Ollama/Gemini), which always
  live in `infrastructure/`.
- **Intent classification is deterministic, not LLM-based.** A regex check
  for industrial tag patterns / procedural keywords is cheap, instant, and
  fully deterministic for testing — an LLM router would add latency, cost,
  and non-determinism for a decision this cheap to make with rules.
- **`entity_lookup` intent bypasses the full hybrid pipeline.** When the
  user names a specific tag, running BM25 + vector + cross-encoder rerank
  is wasted work; `retrieve_context` calls the lighter direct
  entity-extraction + graph-traversal tools instead.
- **Citations use a stricter machine-verifiable marker than M5.** M5's
  `[Title, p.N]` format can't be programmatically checked against a
  specific chunk; M9's `[[chunk:<id>]]` format lets `validate_citations`
  definitively confirm or reject every claim.
- **Session state reuses M5's Redis history, not a new LangGraph checkpointer.**
  The roadmap's "state accumulates across turns via Redis" requirement is
  satisfied by having the agent read/write the same
  `IChatHistoryRepository` already used by `ChatUseCase`, avoiding a second
  persistence mechanism for the same conceptual data.

## Blockers Encountered and How They Were Resolved

- **LangGraph state updates are return-value-based, not mutation-based.**
  The first implementation mutated `state["step_count"]` in place inside
  `_check_step_limit` and never included it in each node's return dict —
  every test asserting `step_count` reported `0`. Fixed by having
  `_check_step_limit` return the new count and every node explicitly
  include `"step_count": step_count"` in its own return value.
- **Pre-existing path bug blocked the container from constructing anything
  that loads a `backend/ai/*.yaml` file.** `get_chat_use_case()` (M5) and
  `get_extraction_use_case()` (M7) both used `parents[4]` (repo root)
  instead of `parents[3]` (`backend/`) — M5 silently masked this with a
  default-prompt fallback; M7 would have hard-crashed on first real use.
  Both fixed; caught only because my own new code copied the same buggy
  pattern and had no fallback, surfacing immediately during container
  wiring verification.
- **Windows temp-dir `PermissionError` blocked all `tmp_path`-based
  tests** (a pre-existing, previously-documented issue from M7/M8).
  Worked around with `pytest --basetemp=<writable dir>`, which incidentally
  fixed the 4 previously-documented pre-existing test errors too — the
  full suite is now 209/209 passing with zero errors.
- **Ollama's configured default model (`llama3.2`) isn't pulled in this
  sandbox.** Used the locally-available `mistral:latest` for the live E2E
  proof; documented as an environment caveat, not a code defect.

## Test Results

- **31 new M9 tests** (30 unit + 1 integration) — all pass
- **1/1 integration test run against live Redis** (not mocked, not skipped)
- **209 total backend tests pass** across the full suite — 0 failures, 0 errors
- Live E2E run against the real Docker stack + real Ollama: two-turn
  conversation correctly classified intents, found a real seeded Neo4j
  relationship via `entity_lookup`, and correctly persisted/accumulated
  both turns in real Redis

## What M9 Unlocks

M9 establishes the LangGraph agent pattern (state schema, node structure,
step-limit enforcement, fallback handling, tool registry separation) that
M10 (Maintenance Brain), M11 (Compliance Brain), M12 (RCA Brain), and M13
(Lessons Learned Brain) will all reuse with domain-specific tools and
prompts.
