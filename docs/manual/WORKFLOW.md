# Development Workflow, Contribution & Release Guide

This document covers git conventions, the PR checklist, CI, and how a release
is cut. It codifies §10–13 of `docs/engineering_bible.md` with the concrete
commands used in this repository.

---

## 1. Branching Strategy

Trunk-based development with short-lived branches off `main` (this repo's
active integration branch during the build-out was `feature/bootstrap`, which
plays the same role).

| Prefix | Use for |
|---|---|
| `feature/<desc>` | New functionality |
| `bugfix/<desc>` | Non-urgent bug fixes |
| `hotfix/<desc>` | Urgent production fixes |
| `docs/<desc>` | Documentation-only changes |

Rules:

- No generic names (`test-code`, `updates`, `fix`) — the branch name should
  describe the change.
- Never commit directly to `main`/`master`/`production`.
- Rebase onto the latest `main` regularly to avoid large, conflict-prone
  merges.
- Delete branches from the remote after merge.

```bash
git checkout -b feature/add-inspection-brain
# ... work, commit ...
git fetch origin && git rebase origin/main
git push -u origin feature/add-inspection-brain
```

---

## 2. Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>
```

| Type | Meaning |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no logic change |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `test` | Adding/adjusting tests |
| `build` | Build system / dependency changes |
| `ci` | CI configuration changes |
| `chore` | Everything else (tooling, housekeeping) |

Examples actually used in this repo's history:

```
feat(m19): KG visualizer, document viewer, mobile UI + demo dataset
fix(security): patch vite dev-server fs.deny bypass (GHSA-fx2h-pf6j-xcff)
docs(m20): stamp commit SHA 9d751dc in roadmap
```

- No generic messages (`fixes`, `changes`, `wip`).
- Breaking changes must include a `BREAKING CHANGE:` footer.
- Squash fixup commits before merging so `main` reads as logical units.

---

## 3. Pull Request Checklist

Before opening a PR:

- [ ] `make lint` passes (black, ruff, eslint)
- [ ] `make test` passes (`pytest`, backend)
- [ ] `npx tsc --noEmit` and `pnpm run build` pass (frontend, if touched)
- [ ] `make validate-prompts` passes (if any prompt YAML changed)
- [ ] `make eval` still meets the hallucination-rate gate (if retrieval/
      generation code changed)
- [ ] New/changed behavior has test coverage
- [ ] PR description lists what changed, how it was tested, and links the
      relevant issue/milestone
- [ ] At least one reviewer approval
- [ ] CI is green

Do not merge with failing tests or unresolved review comments.

---

## 4. Continuous Integration

CI workflows are defined in `ci/` (see `ci/README.md` for why they live there
instead of `.github/workflows/` — the repo's push token lacks the `workflow`
scope; a maintainer with a workflow-scoped token can `git mv` them in):

| Workflow | Trigger | What it checks |
|---|---|---|
| `ci/evaluation.yml` | PR to `main`, push to `main` | Spins up Postgres/Redis/Qdrant/Neo4j service containers, applies migrations, runs `python scripts/run_eval.py`. **Fails if `hallucination_rate > 0.15`.** |
| `ci/prompts.yml` | PR to `main`, push to `main` | Runs `python scripts/validate_prompts.py` (schema + manifest + template-render checks) and a hardcoded-prompt grep. |

Run both locally before pushing:

```bash
python scripts/run_eval.py
python scripts/validate_prompts.py
```

---

## 5. Code Review Standards

From `docs/engineering_bible.md` §13 and this project's actual practice:

- Reviewers check for: Clean Architecture violations (does anything in
  `domain/` import outward?), missing tests, prompt changes without a version
  bump, and any hardcoded secret or prompt string.
- Prefer requesting changes with a concrete alternative over a vague
  "needs work."
- Architectural changes should reference (or add) an ADR in
  `docs/architecture_decision_records.md`.

---

## 6. Release Process

This project does not yet use semantic version tags or a changelog generator
— releases are tracked as **milestones** in
`docs/implementation_roadmap.md`, each ending with three committed artifacts:

1. `docs/walkthroughs/m<N>_walkthrough.md` — what was built and how it works.
2. `docs/verification/m<N>_verification.md` — how it was verified (test
   counts, benchmark numbers, live checks).
3. `docs/reports/m<N>_summary.md` — a concise summary for reviewers.

The pattern for "cutting" a milestone:

```bash
# 1. Implement + verify (lint, test, eval, security-audit as applicable)
make lint && make test

# 2. Write the three artifacts above

# 3. Commit the implementation
git add <files>
git commit -m "feat(mN): <milestone summary>"

# 4. Stamp the roadmap with the resulting commit SHA
#    (edit docs/implementation_roadmap.md's "**Commit**: <sha>" line)
git add docs/implementation_roadmap.md
git commit -m "docs(mN): stamp commit SHA <sha> in roadmap"

# 5. Push
git push origin feature/bootstrap
```

If/when this project adopts semantic versioning for external releases, tag
the commit that completes the milestone (`git tag v1.<N>.0`) and generate
release notes from the Conventional Commit history between tags.

---

## 7. Contributor Guide Summary

1. Read `docs/engineering_bible.md` and the relevant ADR(s) in
   `docs/architecture_decision_records.md` before an architectural change.
2. Keep the domain layer pure (`backend/tests/test_architecture.py` enforces
   this in CI-equivalent form locally).
3. Any new prompt goes in `backend/ai/prompts/` with full metadata — never a
   hardcoded string (see `DEVELOPER_GUIDE.md` §6 for the full recipe when
   adding a brain, and `ARCHITECTURE.md` §10 for the PromptOps model).
4. Run `make lint && make test` before every push.
5. Keep commits small and logically scoped; prefer several focused PRs over
   one large one.
