# Architecture Refactoring Summary — Shared Brain-Agent Base

**Type**: Behaviour-preserving refactor (no new features)
**Date**: 2026-07-02
**Trigger**: Architecture review finding #2 — the five LangGraph sub-brain
agents were near-identical copies with no shared abstraction.

## What was done

Extracted the duplicated LangGraph agent boilerplate into two shared
modules and migrated all five brains onto them, with **zero** functional,
endpoint, schema, prompt, workflow, retrieval, GraphRAG, or UI changes. The
full 312-test backend suite passes identically before and after.

## Files created

```
backend/app/application/agents/__init__.py
backend/app/application/agents/base.py            (StepLimitExceededError, load_prompt,
                                                    error_router, format_context_blocks,
                                                    validate_chunk_citations, render_citations,
                                                    CITATION_PATTERN, BaseBrainAgent)
backend/ai/agents/common/__init__.py
backend/ai/agents/common/json_parse.py            (try_direct, balanced_extract,
                                                    try_bracket_extract, try_brace_extract,
                                                    try_strip_fences)
docs/walkthroughs/refactor_walkthrough.md
docs/verification/refactor_verification.md
docs/reports/refactor_summary.md
```

## Files modified

```
backend/app/application/knowledge_brain/knowledge_brain_agent.py   505 → 428  (−77)
backend/app/application/maintenance_brain/maintenance_brain_agent.py 510 → 435  (−75)
backend/app/application/compliance_brain/compliance_brain_agent.py  496 → 416  (−80)
backend/app/application/rca_brain/rca_brain_agent.py               546 → 524  (−22)
backend/app/application/lessons_brain/lessons_brain_agent.py       436 → 415  (−21)
backend/ai/agents/rca_brain/tools.py                              227 → 191  (−36)
backend/ai/agents/compliance_brain/tools.py                       195 → 163  (−32)
```

7 files changed: +101 insertions, −444 deletions. ~444 lines of duplicated
boilerplate removed; 249 lines of single-source shared code added.

## Duplication eliminated

| Helper | Copies before | Copies after |
|--------|:-------------:|:------------:|
| `StepLimitExceededError` | 5 | 1 |
| step-limit guard (`_check_step_limit`) | 5 | 1 (base) |
| error router (`_error_or`) | 5 | 1 (base) |
| prompt loader (`_load_prompt`) | 5 | 1 |
| `CITATION_PATTERN` | 4 | 1 |
| citation validation loop | 3 | 1 |
| citation renderer | 3 | 1 (heading parameterised) |
| context formatter | 3 | 1 |
| chat-history persist | 3 | 1 (base) |
| JSON extraction helpers | 2 (rca+compliance tools) | 1 (`common/json_parse`) |

## Key technical decisions

- **`BaseBrainAgent` is a mixin, not a framework.** It provides only the
  genuinely-shared mechanics (step-limit guard, error router, chat persist)
  and owns no `__init__`; each agent keeps its own constructor, graph
  construction, and nodes. This deliberately avoids over-abstracting three
  structurally different agent shapes (single-shot chat; session-based
  human-in-the-loop RCA; ingestion-graph + chat Lessons) into one rigid
  base.
- **The one per-agent difference in the step-limit message** (session_id vs
  asset_tag) is preserved via an overridable `_step_limit_context` hook, so
  emitted log strings are byte-identical.
- **The Sources heading** ("**Sources:**" vs "**Manual Sources:**") is a
  `render_citations` parameter — no behavioural drift.
- **Compliance gap-table ordering** is byte-identical because the gap table
  is a pure prefix and Sources a pure suffix; they never interleave.
- **State TypedDicts were intentionally NOT unified** — each brain's state
  carries different fields, and the shared behaviour is consumed through
  `Mapping[str, Any]` in the base. A full state-hierarchy merge would be a
  typing change outside a no-functional-change refactor.
- **Test-import compatibility preserved**: `_format_context_blocks` (knowledge
  module) and `parse_report_object` (rca tools) remain importable from their
  original locations, so no test was touched.
- **DI container untouched** — public agent APIs are unchanged.

## Blockers encountered

- **`test_knowledge_brain.py` imports `_format_context_blocks` from the
  agent module** — resolved by re-exporting the shared function under the
  same private name via an aliased import, keeping both internal calls and
  the external test valid.
- **Lessons step-limit context has no `session_id`** — resolved with the
  `_step_limit_context` override hook rather than flattening the message.
- **Compliance's inline bracket extractor looked different** from RCA's
  generalised `_balanced_extract` — verified to be exactly
  `balanced_extract(text, "[", "]")` before consolidating.

## Verification

- black ✅ · ruff ✅ (repo-wide) · mypy ✅ (10 pre-existing, 0 new, 0 in
  refactored files) · pytest ✅ **312 passed** · docker ✅ · backend boot ✅
  (`/health` healthy) · frontend build ✅.

## Roadmap

No "Architecture Refactoring" section exists in
`docs/implementation_roadmap.md`; per the task instruction ("update the
roadmap only if an Architecture Refactoring section already exists"), the
roadmap was **not** modified and there is no roadmap SHA-stamp commit.

## What this unlocks for M14

M14 adds pipeline Stages 7–8 (LLMLingua compression + citation validation)
into the shared agent path. With citation validation now living in
`app/application/agents/base.py` as a single `validate_chunk_citations`
function (rather than three copies), M14's Stage-8 validator has one
correct home to extend instead of N places to re-patch — which was the
explicit pre-M14 prerequisite from the architecture review.
