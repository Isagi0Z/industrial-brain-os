# M18 — PromptOps Finalization

## What this milestone delivers

Finalizes ADR-020 (version-controlled PromptOps): every prompt across the five
brains + evaluation + extraction + chat is now a schema-validated,
manifest-inventoried YAML file, guarded by a CI gate. A single `PromptLoader`
service loads, validates, and renders prompts with strict `{variable}`
injection — missing variables raise instead of shipping a half-formed prompt.

```
backend/ai/prompts/
├── prompt_schema.json      ← canonical JSON Schema (draft-07)
├── MANIFEST.yaml           ← inventory: prompt_id, version, owning_brain, path
├── knowledge_brain/synthesize_answer.yaml
├── maintenance_brain/synthesize_guidance.yaml
├── compliance_brain/{gap_detection,generate_evidence}.yaml
├── rca_brain/{suggest_why,fishbone,generate_report}.yaml
├── lessons_brain/{chat_answer,generate_summary}.yaml
├── evaluation/{faithfulness,context_precision}.yaml
├── relation_extraction.yaml
└── knowledge_copilot.yaml           (13 prompts total)

PromptLoader.load_file(rel) ─► jsonschema.validate ─► PromptSpec
PromptLoader.render(spec, field, **vars) ─► {var} injection or PromptValidationError

scripts/validate_prompts.py  (make validate-prompts / ci/prompts.yml)
  1. every YAML validates against the schema
  2. MANIFEST ↔ disk agree (path, version, owning_brain; unique ids)
  3. every template renders when its placeholders are supplied
  4. no hardcoded prompt assignments in backend/app or backend/ai
```

## Canonical prompt schema

Every prompt file must carry this metadata (enforced by `prompt_schema.json`):

| Field | Rule |
|-------|------|
| `prompt_id` | unique dotted id, `^[a-z0-9_]+(\.[a-z0-9_]+)+$` (e.g. `rca_brain.suggest_why`) |
| `version` | semver `MAJOR.MINOR[.PATCH]` — bump on any change |
| `description` | ≥ 8 chars |
| `owning_brain` | one of the five brains / `evaluation` / `extraction` / `chat` |
| `output_format` | `markdown` \| `json` \| `yes_no` \| `text` |
| `system` | the system instruction (non-empty) |

The **rendering body** is `system` plus one or more `*_template` fields. Their
names are kept exactly as the existing per-brain consumers read them
(`user_template`, `context_template`, `extraction_template`,
`uncertain_template`, `no_context_template`) — see *Backward compatibility*.

## PromptLoader (`app/infrastructure/prompts/prompt_loader.py`)

- `load_file(relative_path) -> PromptSpec` — parses YAML, validates against the
  schema, caches by `prompt_id`; raises `PromptValidationError` on any schema
  violation, missing file, or non-mapping.
- `render(spec, field, **variables) -> str` — extracts the `{placeholders}` a
  template references, and raises `PromptValidationError` listing any variable
  that was not supplied **before** formatting (Engineering Bible §1 — no silent
  failures). Only formats once all placeholders are present.
- `load_manifest()` / `template_fields(spec)` — helpers used by the CI gate.

## Backward compatibility (non-negotiable)

The audit found **no hardcoded prompt strings** — every prompt already lived in
YAML (ADR-020 was followed in M5–M16). The universal render field is `system`
(not `system_template`), and consumers read `system` / `user_template` /
`context_template` / `extraction_template` / `uncertain_template` directly.

M18 therefore **only adds metadata** to each YAML and standardizes it — no field
was renamed or removed. All existing loaders (`agents/base.load_prompt`,
`YamlPromptLoader`, `llm_judge`, `llm_relation_extractor`) keep reading the same
files unchanged. `PromptLoader` is the validated superset that governs the files
via CI + tests; runtime migration of consumers to it is incremental and
optional.

## CI gate

- `scripts/validate_prompts.py` (`make validate-prompts`) — the four checks
  above; exits non-zero on any failure, errors-first.
- `ci/prompts.yml` — runs the script + a redundant hardcoded-prompt grep on
  every PR/merge to `main` (lives in `ci/` pending a `workflow`-scoped token
  move, like `evaluation.yml`; see `ci/README.md`).

## Deviation from the roadmap's idealized field names

The roadmap checklist lists `system_template` / `user_template`. The codebase's
established convention (M5–M16) is `system` + `user_template`, and every
consumer reads `system`. Renaming to `system_template` would break backward
compatibility (an explicit M18 requirement), so the canonical schema keeps
`system` and the metadata standard is layered on top. This is a documented,
deliberate reconciliation — the *intent* of the checklist (standardized,
schema-validated, version-controlled prompts) is fully met.
