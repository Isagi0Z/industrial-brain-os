# M20 — Performance Hardening, Security Audit & Final Validation — Summary

## Objective

Final pre-submission hardening: security scans clean, latency validated against
NFR-03, Engineering Bible compliance assessed, and the stack reproducible.

## What was done

- **Security scans**
  - `bandit -r app -ll` → 0 medium / 0 high (one medium false-positive on a
    parameterized SQL clause annotated `# nosec B608`).
  - `pnpm audit --audit-level high` → 0 high after upgrading `vite` 5.4.21 →
    6.4.3 (patches GHSA-fx2h-pf6j-xcff); build re-verified.
  - `pip-audit` wired for CI; `python-multipart` bumped to `>=0.0.31`; remaining
    ML-transitive advisories triaged as accepted risk (documented).
  - No hardcoded secrets; `.env` gitignored.
- **Latency benchmark** — `scripts/benchmark_latency.py` (`make benchmark`):
  semantic search p50 **271 ms** (target < 500 ms, PASS); chat p50 measured
  (GPU-dependent target — see verification).
- **Architecture invariant** — `tests/test_architecture.py` enforces ADR-013
  (domain layer imports nothing outward); passes.
- **Complexity** — `radon cc app -a` average **A (2.41)**; refactored the M19
  `get_subgraph` 12 → 5.
- **OpenAPI** — `docs/api/openapi.json` committed (33 paths / 35 ops, all
  described).
- **Compliance** — `docs/bible_compliance.md` section-by-section self-assessment.
- **Query review** — Neo4j bounded (traversal `limit`; unique-key lookups);
  PostgreSQL parameterized + index-backed.
- **Tooling** — bandit/pip-audit/radon/pytest-cov added to `requirements.txt`;
  `make security-audit` / `benchmark` / `coverage` targets.

## Files

```
backend/app/presentation/api/v1/endpoints/graph.py    — get_subgraph refactor (12→5)
backend/app/infrastructure/rca/incident_history_repository.py — nosec B608 + safe query
backend/tests/test_architecture.py                    — ADR-013 guard (new)
backend/requirements.txt                              — +bandit/pip-audit/radon/pytest-cov; python-multipart>=0.0.31
frontend/package.json, pnpm-lock.yaml                 — vite 6.4.3 (security)
scripts/benchmark_latency.py                          — NFR-03 latency benchmark (new)
docs/api/openapi.json                                 — committed API spec (new)
docs/bible_compliance.md                              — compliance self-assessment (new)
Makefile                                              — +security-audit/benchmark/coverage
```

## Design notes

- **Backward compatible**: the vite bump and python-multipart bump keep the build
  and API working (both re-verified); no runtime behaviour changed.
- **Honest triage over risky churn**: heavy ML-dependency CVEs and four pre-existing
  complex functions are documented and accepted rather than force-fixed at the
  cost of breaking the verified stack / completed milestones.
- **Clean Architecture** now has a test guarding it, not just a convention.

## Verified

- Full backend suite green (incl. 2 new architecture tests + the graph refactor).
- bandit 0 med/high; pnpm audit 0 high; tsc + eslint + vite build clean.
- Semantic-search p50 271 ms; live compose stack healthy.
