# CI workflows

`evaluation.yml` is the M16 RAG-evaluation merge gate (runs the golden-dataset
evaluation on every PR/merge to `main` and fails if `hallucination_rate > 0.15`).

It lives here rather than under `.github/workflows/` because the repository's
push token does not carry the GitHub `workflow` scope required to create files
in `.github/workflows/`. **To activate it, a maintainer with a `workflow`-scoped
token should move it:**

```
mkdir -p .github/workflows
git mv ci/evaluation.yml .github/workflows/evaluation.yml
git commit -m "ci: activate RAG evaluation workflow"
git push
```

The workflow content is complete and unchanged — only its location is a
placeholder pending that token-scoped move.
