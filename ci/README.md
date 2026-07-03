# CI workflows

- `evaluation.yml` — the M16 RAG-evaluation merge gate (runs the golden-dataset
  evaluation on every PR/merge to `main` and fails if `hallucination_rate > 0.15`).
- `prompts.yml` — the M18 PromptOps gate (validates every prompt YAML against
  `backend/ai/prompts/prompt_schema.json`, checks the MANIFEST agrees with the
  files on disk, render-tests every template, and fails if any hardcoded prompt
  string is found in the Python sources). Locally: `make validate-prompts`.

They live here rather than under `.github/workflows/` because the repository's
push token does not carry the GitHub `workflow` scope required to create files
in `.github/workflows/`. **To activate them, a maintainer with a `workflow`-scoped
token should move them:**

```
mkdir -p .github/workflows
git mv ci/evaluation.yml .github/workflows/evaluation.yml
git mv ci/prompts.yml .github/workflows/prompts.yml
git commit -m "ci: activate evaluation + prompts workflows"
git push
```

The workflow content is complete and unchanged — only its location is a
placeholder pending that token-scoped move.
