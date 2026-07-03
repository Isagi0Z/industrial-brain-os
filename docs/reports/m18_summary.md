# M18 — PromptOps Finalization — Summary

## Objective

Audit all agent/system prompts across the five brains and ensure every prompt
is a version-controlled YAML file with schema validation and no hardcoded
prompt strings in Python code (ADR-020).

## What was built

- **Canonical schema** — `backend/ai/prompts/prompt_schema.json` (JSON Schema
  draft-07): requires `prompt_id`, `version` (semver), `description`,
  `owning_brain`, `output_format`, `system`.
- **PromptLoader service** — `app/infrastructure/prompts/prompt_loader.py`:
  schema-validated loading (`PromptValidationError` on any violation) and strict
  `{variable}` injection that raises on a missing variable rather than emitting a
  half-rendered prompt.
- **13 prompts normalized** — every prompt across knowledge / maintenance /
  compliance / rca / lessons brains + evaluation + extraction + chat now carries
  the full metadata block; **no existing field renamed or removed** (backward
  compatible).
- **MANIFEST.yaml** — a single-source inventory (prompt_id, version,
  owning_brain, path) kept in sync with disk by the gate.
- **CI gate** — `scripts/validate_prompts.py` (`make validate-prompts`) +
  `ci/prompts.yml`: validates schema, MANIFEST↔disk consistency, template
  rendering, and the no-hardcoded-prompts rule.
- **Unit tests** — `tests/test_prompts.py` (9 tests).

## Audit result

`grep` for hardcoded prompt assignments (`system_prompt = "…"` / `system = "…"`)
across `backend/app` + `backend/ai` returned **zero findings** — prompts were
already externalized to YAML in M5–M16. M18 formalizes and enforces this.

## Files

```
backend/ai/prompts/prompt_schema.json                 — canonical JSON Schema (new)
backend/ai/prompts/MANIFEST.yaml                       — prompt inventory (new)
backend/ai/prompts/**/*.yaml (13 files)                — +metadata (prompt_id/description/owning_brain/output_format)
backend/app/infrastructure/prompts/prompt_loader.py    — PromptLoader + PromptValidationError (new)
backend/app/infrastructure/prompts/__init__.py         — package (new)
scripts/validate_prompts.py                            — CI gate (new)
ci/prompts.yml                                         — PromptOps workflow (new)
ci/README.md                                           — documents the new gate
Makefile                                              — +validate-prompts target
backend/requirements.txt                              — +jsonschema>=4.0.0
backend/tests/test_prompts.py                          — 9 unit tests (new)
```

## Design notes

- **Backward compatibility** — the render field stays `system` (the codebase
  convention every consumer reads); M18 only *adds* metadata. Existing loaders
  (`agents/base.load_prompt`, `YamlPromptLoader`, `llm_judge`,
  `llm_relation_extractor`) are untouched and keep working.
- **No silent failures** — `PromptLoader.render` raises `PromptValidationError`
  when a template variable is missing (Engineering Bible §1).
- **Clean Architecture** — `PromptLoader` is an infrastructure service; the
  schema/manifest are data; the CI script + tests are the enforcement layer.
- **Documented deviation** — the roadmap's idealized `system_template` field
  name is reconciled to the codebase's `system` convention to preserve backward
  compatibility (see the walkthrough).

## Verified

- `make validate-prompts` → PASS (13 prompts: schema + manifest + render + no
  hardcoded prompts).
- 9 PromptLoader unit tests pass; full backend suite green (no regression — the
  brain/chat/eval tests exercise the real prompt consumers).
- Ruff clean, black formatted, mypy clean on the new module.
