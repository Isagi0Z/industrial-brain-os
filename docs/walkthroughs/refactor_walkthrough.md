# Architecture Refactoring Walkthrough — Shared Brain-Agent Base

## Scope

Behaviour-preserving consolidation of the five LangGraph sub-brain agents
(Knowledge M9, Maintenance M10, Compliance M11, RCA M12, Lessons M13),
which the architecture review identified as near-identical copies. **No
functional, endpoint, schema, prompt, workflow, retrieval, GraphRAG, or UI
change** was made — only duplication was removed. The 312-test backend
suite passes identically before and after.

## What was extracted

### `app/application/agents/base.py` (new, 182 LOC)

| Symbol | Replaces (per-agent copies) |
|--------|------------------------------|
| `StepLimitExceededError` | 5 identical class definitions |
| `load_prompt(path)` | 5 identical `_load_prompt` functions |
| `error_router(default)` / `BaseBrainAgent._error_or` | 5 identical `_error_or` factories |
| `format_context_blocks(chunks)` | 3 identical `_format_context_blocks` (knowledge/maintenance/compliance) |
| `validate_chunk_citations(text, chunks)` | 3 identical `[[chunk:<id>]]` → `Citation` validation loops |
| `render_citations(text, citations, sources_header)` | 3 near-identical footnote+Sources renderers (heading text was the only difference → now a parameter) |
| `CITATION_PATTERN` | 4 identical `_CITATION_PATTERN` constants |
| `BaseBrainAgent._check_step_limit` | 5 identical step-limit guards |
| `BaseBrainAgent._step_limit_context` | the one per-agent difference (chat brains key on `session_id`; lessons ingestion keys on `asset_tag`) — now an overridable hook |
| `BaseBrainAgent._persist_turn` | 3 identical chat-history persisters (knowledge/maintenance/compliance) |

### `ai/agents/common/json_parse.py` (new, 67 LOC)

| Symbol | Replaces |
|--------|----------|
| `try_direct` / `balanced_extract` / `try_bracket_extract` / `try_brace_extract` / `try_strip_fences` | The JSON-extraction helpers duplicated in `rca_brain/tools.py` and `compliance_brain/tools.py`. The Compliance registry's inline `_try_bracket_extract` was verified to be exactly `balanced_extract(text, "[", "]")` — a specialised copy of RCA's generalised version. |

## How behaviour is preserved

The refactor is a mechanical *extract-method / pull-up-to-base* with three
subtleties handled explicitly:

1. **Step-limit log message.** Four brains embed `session={session_id}` in
   the `StepLimitExceededError` message; the Lessons ingestion graph has no
   `session_id` and embedded `asset_tag={incident.asset_tag}`. Rather than
   flatten this, `BaseBrainAgent._step_limit_context(state)` defaults to the
   `session_id` form and `LessonsLearnedBrainAgent` overrides it — the
   emitted strings are byte-identical to before. (No test asserts on this
   string; it is caught and logged. Preserved regardless.)

2. **Sources heading.** Maintenance renders `**Manual Sources:**`; the
   others render `**Sources:**`. `render_citations` takes the heading as a
   parameter, so each call site reproduces its exact previous output.

3. **Compliance gap-table ordering.** Compliance prepends a gap table
   between marker-substitution and the Sources block. Because the gap table
   is a pure prefix and the Sources block a pure suffix (they never
   interleave), calling `render_citations` first and prepending the gap
   table after yields byte-identical output in every branch (empty/non-empty
   citations × empty/non-empty gaps) — verified by the 26 compliance tests.

RCA keeps its own bespoke `_validate_citations` (it validates into
citation *strings* plus known failure codes, not the shared `Citation`
list) — it only adopted the shared step-limit/error/prompt-loader
primitives and imports `CITATION_PATTERN` from the base. Lessons keeps its
own inline `chat()` history persistence (different signature from the base
`_persist_turn`).

## Public-surface preservation

- Every agent class name, constructor signature, and public method
  (`run` / `start_session` / `advance_session` / `ingest_incident` /
  `chat`) is unchanged → the DI container needed **no** edits.
- `test_knowledge_brain.py` imports `_format_context_blocks` **from the
  knowledge agent module** → preserved via
  `from app.application.agents.base import format_context_blocks as
  _format_context_blocks` (the alias keeps both the internal call sites and
  the external test import valid).
- `test_rca_brain.py` imports `parse_report_object` from
  `ai.agents.rca_brain.tools` → that function stays defined there, now
  delegating to the shared `json_parse` helpers.
- The M7 extraction module (`llm_relation_extractor`) keeps its own JSON
  helpers; it is part of the ingestion/KG pipeline (outside this refactor's
  agent scope) and its own tests import those names directly, so it was
  deliberately left untouched.

## Inheritance shape

Each agent now declares `class XBrainAgent(BaseBrainAgent, IXBrainAgent)`.
`BaseBrainAgent` is a plain (non-ABC) mixin with no `__init__`; the domain
interface (`IXBrainAgent`) remains an ABC whose abstract method the concrete
class still implements. MRO: `XBrainAgent → BaseBrainAgent → IXBrainAgent →
ABC → object`. No method-name collisions between the base mechanics
(`_check_step_limit`, `_error_or`, `_persist_turn`, `_step_limit_context`)
and the interface's abstract methods.

## Net effect

| File | Before | After | Δ |
|------|-------:|------:|--:|
| knowledge_brain_agent.py | 505 | 428 | −77 |
| maintenance_brain_agent.py | 510 | 435 | −75 |
| compliance_brain_agent.py | 496 | 416 | −80 |
| rca_brain_agent.py | 546 | 524 | −22 |
| lessons_brain_agent.py | 436 | 415 | −21 |
| rca_brain/tools.py | 227 | 191 | −36 |
| compliance_brain/tools.py | 195 | 163 | −32 |
| **new** agents/base.py | — | 182 | +182 |
| **new** common/json_parse.py | — | 67 | +67 |

~444 lines of duplicated boilerplate deleted; replaced by 249 lines of
single-source shared code (net −343 in the touched agents/tools, ≈ −94
overall). The value is not the line count — it is that the step-limit
guard, error router, prompt loader, citation validation/rendering, and JSON
extraction now have exactly one definition each.
