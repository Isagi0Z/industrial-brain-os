# Industrial Brain OS — Claude Engineering Workflow

> **Mandatory.** Every milestone of Industrial Brain OS must follow this workflow exactly.
> No milestone may begin without completing the context loading phase.
> No milestone may end without completing all quality gates and artifact generation.
> This document supersedes any ad-hoc instructions given in individual milestone prompts.

---

## 1. Purpose

This document defines the permanent, session-to-session engineering workflow for building Industrial Brain OS with Claude as the implementation agent.

Its purpose is to eliminate inconsistency across sessions, prevent architecture drift, enforce quality standards automatically, and reduce the prompt overhead required to start each new milestone.

Every future Claude session working on this repository must read this document before touching any code. Following this workflow is not optional. It is the contract between the engineering team and the AI agent.

The workflow enforces:
- Architecture integrity (Clean Architecture, DDD, ADRs)
- Engineering Bible compliance
- Minimal context loading (token efficiency)
- Mandatory verification before commit
- Atomic, traceable commits
- Complete stop after each milestone

---

## 2. Model Policy

### Model Tiers

| Tier | Model | Best For |
|------|-------|----------|
| **Haiku** | `claude-haiku-4-5-20251001` | Mechanical tasks: formatting, renaming, simple scaffolding, grep-and-replace, doc generation from templates |
| **Sonnet** | `claude-sonnet-4-6` | Standard engineering work: feature implementation, unit tests, migrations, API endpoints, wiring use cases |
| **Opus** | `claude-opus-4-8` | High-stakes reasoning: architectural design, security reviews, complex debugging, multi-layer refactors, final demo prep |

### Effort Levels

| Level | When to Use |
|-------|-------------|
| `low` | Doc generation, file reads, simple scaffolding with no logic |
| `medium` | Standard feature implementation, well-understood patterns |
| `high` | Multi-file implementation, new domain boundaries, non-trivial bug diagnosis |
| `max` | Architectural decisions, security audit, cross-cutting refactors, root cause analysis on production failures |

### Task Recommendations

| Task | Model | Effort |
|------|-------|--------|
| Normal implementation (domain → infra → API) | Sonnet | `medium` |
| Architectural design (new bounded context, new ADR) | Opus | `max` |
| Refactoring (extract interface, reorganize layers) | Opus | `high` |
| Debugging (failing tests, tracing errors across layers) | Sonnet → Opus | `high` → `max` |
| Security review (auth flows, RBAC, secrets) | Opus | `max` |
| Final demo preparation (E2E, polish, screenshots) | Sonnet | `high` |
| Doc generation, migration stubs | Haiku | `low` |

---

## 3. RepoWise Verification

Run the following check **before every milestone** and **after every push**.

### What to verify

```
hook status       — Is the RepoWise post-commit hook installed and enabled?
queued updates    — Are there pending indexing updates in the queue?
last_sync_commit  — Does the indexed commit match the current HEAD?
current HEAD      — What is git rev-parse HEAD?
CLAUDE.md         — Has RepoWise regenerated CLAUDE.md since the last commit?
onboarding page   — Has RepoWise regenerated the onboarding page since the last commit?
```

### How to check

```bash
# HEAD vs last indexed commit
git rev-parse HEAD
# Compare against last_sync_commit shown in .claude/CLAUDE.md index header

# Hook presence
ls .git/hooks/post-commit

# Queue status
repowise status   # if CLI is installed
```

### Rules

- If `last_sync_commit == HEAD`: index is current. Proceed.
- If `last_sync_commit != HEAD` and the gap is one recent commit: pending sync. **Report only. Do not force.**
- If `last_sync_commit` is multiple commits behind HEAD and the gap has persisted across sessions: report the gap, note the stale index age, and recommend the user manually trigger sync if needed. Do not trigger it automatically.
- Never run `repowise sync --force` or equivalent without explicit user approval.

---

## 4. Context Loading Policy

**Read the minimum. Never scan blindly.**

### Mandatory reads at session start (every milestone)

Load in this order:

1. `CLAUDE.md` (project root) — project rules, source-of-truth pointers
2. RepoWise onboarding page — module map, architectural boundaries, hotspots
3. RepoWise generated architecture documentation — layer summaries, dependency graph
4. `docs/implementation_roadmap.md` — identify the current milestone, its dependencies and blockers
5. Engineering Bible — **only the sections relevant to the current milestone** (e.g. §8 coding standards, §15 RBAC, §26 testing — not all 32 sections every session)
6. ADRs — **only the ADRs referenced by the current milestone checklist** (e.g. ADR-001, ADR-005, ADR-009 for M4 — not all ADRs)
7. Source files — **only files that will actually change**. Use `get_context` and `get_symbol` before `Read`. Do not scan entire directories.

### Prohibited

- Reading files "just to be safe"
- Rereading an unchanged file already in context
- Running directory-wide greps to discover structure when RepoWise answers the question
- Loading all ADRs when the milestone references only two or three
- Reading the full Engineering Bible linearly every session

### RepoWise tool priority

Before any `Read` or `Grep`, prefer:

| Question | Tool |
|----------|------|
| "How does X work?" | `get_answer(question)` |
| "What is in file Y?" | `get_context(["path"])` — skeleton first |
| "Show me the body of function Z" | `get_symbol("path.py::ClassName.method")` |
| "Where is symbol W defined?" | `search_codebase("W", mode="symbol")` |
| "Why is this designed this way?" | `get_why(query, targets=[...])` |
| "Is it safe to change F?" | `get_risk(targets=["F"])` |

Only fall back to `Read` when `verified: true` is absent, `confidence` is `low`, or `_meta.stale_warning` is set.

---

## 5. Planning Phase

Before writing a single line of code, complete the planning phase.

### Steps

1. Read the milestone checklist from `docs/implementation_roadmap.md`.
2. Identify all dependencies: which prior milestones must be complete, which services must be healthy.
3. Identify risks: blocking calls, external library constraints, version conflicts, migration order.
4. Identify architectural impact: which bounded contexts are affected, which ADRs apply.
5. List every file that will be created or modified.
6. Produce a concise implementation plan:

```
Phase 1: Domain — new models, new interfaces (no infra imports)
Phase 2: Application — use case orchestration, no framework dependencies
Phase 3: Infrastructure — DB repositories, external client wrappers, migrations
Phase 4: Presentation — FastAPI routes, request/response schemas
Phase 5: Frontend — React components, hooks, API calls
Phase 6: Tests — unit (all new classes), integration (live services), E2E
```

7. If there is no architectural blocker, proceed automatically. Do not wait for permission to code.
8. If a true architectural blocker exists (e.g. a required ADR decision that has not been recorded, or a dependency milestone that is incomplete), stop and report before proceeding.

---

## 6. Implementation Policy

### Layer order (mandatory)

Implement strictly in this order. Never skip ahead.

```
Domain
  └─ models.py       — dataclasses, enums, value objects (no framework imports)
  └─ interfaces.py   — abstract base classes only

Application
  └─ use_case.py     — orchestration, calls domain interfaces, no DB/HTTP imports

Infrastructure
  └─ repository.py   — concrete DB implementations of domain interfaces
  └─ service.py      — concrete external service wrappers
  └─ migrations/     — Alembic migrations (run after infrastructure is written)

Presentation
  └─ endpoints/      — FastAPI routers, Pydantic request/response models
  └─ router.py       — register new router

Frontend
  └─ components/     — React components
  └─ hooks/          — data-fetching hooks
  └─ api/            — typed fetch wrappers
```

### Rules

- **Never** import an infrastructure class inside a domain or application file.
- **Never** import FastAPI or SQLAlchemy inside a domain file.
- **Never** refactor unrelated modules during a milestone.
- **Never** redesign the architecture to fit a new library.
- **Never** hardcode secrets, connection strings, or model paths.
- Keep all blocking calls (model inference, heavy I/O) inside `run_in_threadpool` (ADR-001).
- Use `upsert` over `insert` for all idempotent writes (safe re-ingestion).
- All function signatures must carry explicit type annotations (Engineering Bible §8).
- No `Any` typing in Python. No `any` in TypeScript (Engineering Bible §8).
- Log every significant state transition with a structured JSON log entry including `correlation_id`.

---

## 7. Quality Gates

All gates are mandatory. A milestone is not complete until every gate passes with zero errors.

Run in this order:

### Backend

```bash
# 1. Formatting
python -m black .

# 2. Lint
python -m ruff check .

# 3. Type checking
python -m mypy app/ --ignore-missing-imports --explicit-package-bases

# 4. Unit tests
python -m pytest tests/ -m "not integration" -v

# 5. Integration tests (requires live Docker services)
python -m pytest tests/ -m "integration" -v

# 6. Full suite
python -m pytest tests/ -v
```

### Frontend

```bash
# 7. TypeScript
npx tsc --noEmit

# 8. Lint
npx eslint src/

# 9. Format
npx prettier --check src/
```

### Infrastructure

```bash
# 10. Docker health
docker compose ps   # all services: healthy

# 11. Migration integrity
alembic upgrade head
alembic check   # no pending migrations
```

### Backend runtime

```bash
# 12. Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 13. Health check
curl http://localhost:8000/api/v1/health   # → {"status": "healthy"}
```

### Frontend runtime

```bash
# 14. Start frontend
cd frontend && pnpm dev

# 15. Verify page loads
# Navigate to http://localhost:5173 — no blank page, no console errors
```

### End-to-end

```
# 16. Upload a test document
# 17. Verify full job pipeline reaches the terminal state for this milestone
# 18. Exercise each new endpoint with curl or the UI
# 19. Verify RBAC: unauthenticated requests return 401
```

**Never commit until all 19 gates pass.**

---

## 8. Preview Requirements

Every milestone verification report must include:

| Item | Value |
|------|-------|
| Backend URL | `http://localhost:8000` |
| Frontend URL | `http://localhost:5173` |
| Swagger UI | `http://localhost:8000/docs` |
| Health endpoint | `http://localhost:8000/api/v1/health` |
| New endpoints | List every new route with method, path, auth requirement |
| Demo instructions | Step-by-step: what to upload, what to query, what to expect |

Demo instructions must be specific enough that a non-technical stakeholder can reproduce the result.

---

## 9. Artifact Generation

Generate three artifact documents after every milestone. Generate them **after** all quality gates pass, **before** committing.

### `docs/walkthroughs/mX_walkthrough.md`

Contents:
- Architecture diagram (ASCII)
- Domain layer: new models, new interfaces
- Application layer: use case logic, state transitions
- Infrastructure layer: concrete implementations, external APIs used
- Presentation layer: new endpoints with request/response schemas
- Frontend (if applicable): new components, hooks
- Environment notes: required env vars, version constraints, known workarounds

### `docs/verification/mX_verification.md`

Contents:
- Test suite results (paste `pytest` summary)
- Code quality results (black, ruff, mypy, tsc — all must show clean)
- Infrastructure status (docker compose ps output)
- Integration test result
- End-to-end test result with actual API responses
- Acceptance criteria checklist (all `[x]`)

### `docs/reports/mX_summary.md`

Contents:
- One-paragraph summary of what was built
- Table of files created
- Table of files modified
- Key technical decisions made during implementation
- Blockers encountered and how they were resolved
- What the next milestone unlocks

### `docs/implementation_roadmap.md` update

After generating the three artifacts, update the roadmap:
1. Change milestone status to `✅ Complete`
2. Add `**Status**: ✅ Complete`
3. Add `**Completion Date**: YYYY-MM-DD`
4. Add `**Commit SHA**: TBD` (fill in after commit)
5. Mark all checklist items `[x]`

---

## 10. Git Workflow

### Commit format (Conventional Commits — Engineering Bible §12)

```
<type>(<scope>): <short description>

<body — what changed and why, not a list of files>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`

Scope: use the milestone tag (e.g. `m4`, `m5`) or the module name (e.g. `auth`, `search`).

### Commit sequence per milestone

```bash
# 1. Stage only milestone files (never git add -A blindly)
git add <specific files>

# 2. Commit implementation
git commit -m "feat(mX): <description>"

# 3. Stage roadmap
git add docs/implementation_roadmap.md

# 4. Commit SHA stamp
git commit -m "docs(mX): stamp commit SHA <sha> in roadmap"

# 5. Push
git push origin feature/bootstrap

# 6. Verify RepoWise sync status (Section 3)
# Report whether the index has updated to HEAD
```

### Rules

- Never commit with `--no-verify`.
- Never force-push to `main`.
- Never include `.env`, credentials, or binary assets in commits.
- One logical unit of work per commit. Do not bundle unrelated changes.
- The roadmap SHA stamp is always a separate commit.

---

## 11. Stop Conditions

After the push in Section 10:

**Stop. Do not begin M(X+1).**

Wait for explicit user approval before starting the next milestone.

This applies even if:
- The next milestone appears simple.
- The next milestone's dependencies are satisfied.
- The user has previously asked to "keep going."

The rule is: **one milestone per session**. The next milestone begins in the next explicit user instruction.

Report the following at the stop point:

```
M(X) complete.
Commit: <SHA>
Push: ✅ origin/feature/bootstrap
RepoWise sync: <current | pending — N commits behind>
Next: M(X+1) — <title> — requires explicit approval to begin.
```

---

## 12. Token Optimization Policy

### Prefer RepoWise over source reads

- Use `get_answer` before `Read` for any "how does X work" question.
- Use `get_context` skeleton before reading a full file.
- Use `get_symbol` to fetch a function body rather than reading the whole file.
- Never read a file the index already answers with `confidence: high` or `verified: true`.

### Avoid redundant loads

- Do not re-read a file you already have in context unless it has changed.
- Do not re-derive architecture from source when the RepoWise onboarding page already describes it.
- Do not explain the same concept twice in a session.

### Responses

- Keep implementation updates concise. State what changed and what is next.
- Do not produce multi-paragraph summaries of code that the diff already shows.
- Do not re-list all files created in every response — save that for the summary artifact.

### ADR and Engineering Bible loading

Load only the sections that the milestone checklist explicitly references. If a checklist item cites "Engineering Bible §8", read §8 only. Do not load §1–32 to "be thorough."

---

## 13. Failure Recovery

If any quality gate fails:

1. **Do not commit.**
2. Read the error message completely. Identify the root cause.
3. Check whether the error is:
   - A code bug in the new implementation → fix in the relevant layer
   - A version conflict with an existing library → pin the compatible version; update `requirements.txt`
   - A Docker service issue → check `docker compose ps`, restart if unhealthy
   - A migration conflict → check `alembic history`, resolve ordering
   - A type annotation error → add explicit types; remove `Any`
4. Fix the root cause. Do not suppress errors with `# type: ignore`, `# noqa`, or `--no-verify` unless the suppression is justified and documented with a comment explaining why.
5. Re-run the full quality gate sequence from the beginning (Section 7).
6. Only commit when all gates pass.

If a fix requires changing the architecture (new interface, new dependency direction, new migration), stop and describe the change before implementing it. Architecture changes may require a new ADR.

---

## 14. Engineering Principles

The following principles are non-negotiable. They apply to every line of code written in this project.

### From CLAUDE.md

- Follow Clean Architecture.
- Follow SOLID.
- Follow Domain Driven Design.
- Keep modules loosely coupled.
- Never hardcode secrets.
- Never skip testing.
- Verify every milestone before committing.
- One milestone per session.
- Commit and push after milestone completion.
- Stop after successful verification.
- Never redesign the architecture.

### From Engineering Bible

| § | Rule |
|---|------|
| §1 | Keep it simple. Fail fast at boundaries. No dead code. |
| §2 | Dependency direction: Domain ← Application ← Infrastructure ← Presentation. |
| §3 | SOLID: single responsibility, open/closed, dependency inversion. |
| §4 | DDD: ubiquitous language, aggregates, bounded contexts, no raw entity mutation. |
| §5 | Commit only clean, linted code. No env files or secrets in commits. |
| §8 | Explicit types on all signatures. No `Any`. Black + ruff for Python. |
| §12 | Conventional Commits. No generic messages. |
| §14 | No secrets in source. Validate at application boundaries. |
| §15 | RBAC on every API route. Filter context by user permissions. |
| §16 | Structured JSON logs. Correlation-ID on every log entry. |
| §26 | 80% test coverage. Separate unit, integration, E2E suites. No skipped tests. |
| §29 | Structured error responses at all API interfaces. No raw stack traces to clients. |

### From ADRs

| ADR | Constraint |
|-----|-----------|
| ADR-001 | Wrap blocking I/O and model inference in `run_in_threadpool`. |
| ADR-005 | Qdrant payload filtering enforces RBAC. `role_scope` on every query. |
| ADR-007 | Agent workflows use LangGraph state machines with explicit step limits. |
| ADR-008 | GraphRAG: combine vector + graph retrieval. No raw subgraph to LLM. |
| ADR-009 | Hybrid retrieval: BM25 + vector + graph + rerank. Not vector-only. |
| ADR-010 | Graph schema enforces ISO 14224/ISO 15926 ontology. No ad-hoc nodes. |

### Absolute prohibitions

- Never redesign the architecture to avoid complexity.
- Never bypass RBAC in any query or route.
- Never store secrets in source files, Docker images, or migration scripts.
- Never call a blocking library from the async event loop without `run_in_threadpool`.
- Never skip a quality gate because "it probably passes."
- Never continue into the next milestone without explicit user approval.
