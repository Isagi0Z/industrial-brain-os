# M18 — PromptOps Finalization — Verification

## Scope

Every prompt is a schema-validated, manifest-inventoried YAML file; a
`PromptLoader` service loads/validates/renders them with strict `{variable}`
injection; a CI gate enforces schema + manifest + no-hardcoded-prompts (ADR-020).

## Hardcoded-prompt audit

```
grep -rnE '^\s*(system_prompt|system)\s*=\s*["'](You |Answer |Respond )' \
  backend/app backend/ai --include=*.py
  → 0 findings
```
Prompts were already externalized to YAML in M5–M16; M18 formalizes + enforces.

## CI gate (`scripts/validate_prompts.py` / `make validate-prompts`)

```
PASS: 13 prompts validated against schema + manifest;
      all templates render; no hardcoded prompts.
exit 0
```
Checks: (1) every YAML validates against `prompt_schema.json`; (2) MANIFEST ↔
disk agree on path/version/owning_brain and prompt_ids are unique; (3) every
`*_template` renders when its placeholders are supplied; (4) no hardcoded
prompt assignment in `backend/app` or `backend/ai`.

## Unit tests (`tests/test_prompts.py` — 9)

| Test | Asserts |
|------|---------|
| `test_valid_prompt_loads_and_exposes_metadata` | metadata parsed from a real prompt |
| `test_render_injects_variables` | `{context}`/`{answer}` substituted |
| `test_render_missing_variable_raises` | `PromptValidationError` names the missing var |
| `test_invalid_schema_raises` | metadata-less prompt rejected |
| `test_missing_file_raises` | unknown path → `PromptValidationError` |
| `test_bad_prompt_id_pattern_rejected` | non-dotted id rejected |
| `test_bad_version_pattern_rejected` | non-semver version rejected |
| `test_every_shipped_prompt_validates` | all 13 prompts pass the schema |
| `test_manifest_matches_disk` | manifest ids == disk ids; every path resolves |

**Full backend suite: 366 passed, 0 failed** (357 prior + 9 new), run with a
writable pytest basetemp (see environment note).

## Live end-to-end verification (backward compatibility)

```
1. app.application.agents.base.load_prompt (shared by all 5 brains)
   → parses all 13 normalized YAMLs; system + metadata present            ✅
2. YamlPromptLoader (M5 chat)
   → system_prompt() + wrap_context() still return the expected content   ✅
3. PromptLoader.render (new) on rca_brain/suggest_why.yaml
   → real prompt rendered, no leftover {placeholders}                     ✅
```
Confirms the metadata additions did not break any existing consumer — the
render field stays `system`, no field was renamed or removed.

## Checklist coverage

- [x] Audit codebase for hardcoded prompt strings — 0 findings; enforced by the gate
- [x] `PromptLoader` reads YAML from `ai/prompts/`, validates against JSON Schema, injects `{variable}`
- [x] `PromptLoader` raises `PromptValidationError` on missing required variables — no silent failures (Eng. Bible §1)
- [x] Prompt YAML schema fields: `prompt_id` (unique), `version` (semver), `description`, `system` (render field; see deviation), `output_format`, `owning_brain`
- [x] All prompts inventoried in `ai/prompts/MANIFEST.yaml` with prompt_id, version, owning brain
- [x] CI step `python scripts/validate_prompts.py` fails on schema / manifest / render / hardcoded violations (`ci/prompts.yml`, `make validate-prompts`)
- [x] CI step greps for hardcoded prompts and fails the build if found (`ci/prompts.yml`)
- [x] Version bump discipline: `version` is a required semver field checked file↔manifest by the gate
- [x] Unit tests: PromptLoader with valid template, missing variable, invalid schema (+ manifest/all-prompts coverage)

## Quality gates

- `make validate-prompts` → PASS
- Ruff: clean; black: formatted; mypy (`app/infrastructure/prompts/`): no issues
- 366 tests pass

## Deviations / notes (documented, not defects)

- **`system` vs `system_template`**: the roadmap's idealized field name is
  `system_template`, but every existing consumer reads `system` and renaming
  would break backward compatibility (an explicit M18 requirement). The
  canonical schema keeps `system`; the standardized metadata is layered on top.
  The intent of the checklist (standardized, schema-validated, version-controlled
  prompts) is fully met.
- **PromptLoader is additive**: it governs the files via CI + tests; the runtime
  brains keep their existing loaders (`agents/base.load_prompt`, etc.). Migrating
  consumers onto PromptLoader is incremental and out of M18 scope.
- **Environment**: `jsonschema` install required pip `--trusted-host` flags on
  this host (SSL-intercepting proxy — the same condition the reranker code
  already works around). The full suite's `tmp_path`-using tests need a writable
  `--basetemp` (Windows `%TEMP%` ACL issue); with it, 366 pass. Neither is an
  M18 code issue.
