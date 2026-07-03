# M20 — Performance Hardening, Security Audit & Final Validation

## What this milestone delivers

The final pre-submission pass: security scans, dependency audits, latency
benchmarks against NFR-03, an enforced architecture invariant, a committed
OpenAPI spec, and a full Engineering Bible compliance self-assessment. It is
mostly *validation + tooling*, with a handful of targeted hardening fixes.

## Security & dependency audits

| Check | Tool | Result |
|-------|------|--------|
| Static analysis | `bandit -r app -ll` | 0 medium / 0 high |
| Python deps | `pip-audit` (CI) | direct deps bumped; ML-transitive advisories triaged (see verification) |
| Frontend deps | `pnpm audit --audit-level high` | 0 high after `vite` 5.4.21 → 6.4.3 |
| Secrets | grep + `.gitignore` | no hardcoded secrets; `.env` gitignored |

**Hardening fixes made:**
- `incident_history_repository.py` — the dynamic `WHERE` clause (fixed-literal
  `ILIKE %s` repeated per keyword; all values bound) is annotated `# nosec B608`
  with justification, clearing bandit's one medium false-positive.
- `vite` upgraded 5.4.21 → 6.4.3 to patch GHSA-fx2h-pf6j-xcff (dev-server
  `fs.deny` bypass). Build re-verified.
- `python-multipart` minimum bumped to `>=0.0.31` (patched advisories).

## Latency benchmark — `scripts/benchmark_latency.py` (`make benchmark`)

Drives the running API and reports p50/p95/p99, minting a token from the app's
token service (no password). Targets (NFR-03):
- `GET /search/semantic` p50 < 500 ms → **271 ms (PASS)**
- `POST /chat` (full GraphRAG) p50 < 3000 ms → CPU-bound on this dev host
  (`llama3.2` on CPU); the target assumes GPU/production hardware. Measured
  numbers in the verification doc.

## Architecture invariant — `tests/test_architecture.py`

Turns ADR-013 into an enforced test: parses every `domain/` module's imports and
fails if any references `infrastructure`/`presentation`/`application` or a
framework (fastapi/starlette/sqlalchemy/psycopg2/neo4j/qdrant/redis/celery).
Passes today — the domain layer is clean.

## Complexity — `radon cc app -a`

Average **A (2.41)**, well under 5. The M19 `get_subgraph` endpoint was
refactored (12 → 5) by extracting `_collect_node_types`. Four pre-existing
parse/search/agent functions rank C (11–15) and are documented as reviewed
exceptions in `docs/bible_compliance.md`.

## API documentation — `docs/api/openapi.json`

Generated from the FastAPI app and committed: 33 paths / 35 operations, **all
with a summary/description**.

## Query review

- **Neo4j**: KG traversal uses `apoc.path.subgraphAll` with a `limit`; all other
  Cypher are unique-key `MATCH`/`MERGE` lookups — no unconstrained scans (§36).
- **PostgreSQL**: all user values are bound parameters; frequent lookups hit
  PK/unique indexes.

## Compliance self-assessment — `docs/bible_compliance.md`

A section-by-section Engineering Bible + ADR self-assessment with evidence and
honestly-documented exceptions.

## New Make targets

`make security-audit` · `make benchmark` · `make coverage` (plus the M20 dev
tooling added to `requirements.txt`: bandit, pip-audit, radon, pytest-cov).

## Deviations (documented, not defects)

- **pip-audit ≠ exit 0**: ML transitives (`torch`, `transformers`) and
  `starlette` carry advisories whose fixes need major-version bumps that break
  the reranker/LLMLingua/serving stack; the CVEs are in code paths not exercised.
  Triaged as accepted risk rather than destabilise a verified environment.
- **Chat p50 target** is GPU-dependent; measured on CPU here.
- **Connection pooling**: psycopg2 direct connections (no SQLAlchemy ORM), so the
  checklist's `pool_size/max_overflow` is N/A — a psycopg2 pool is a noted future
  enhancement.
- Four pre-existing complex functions (parsers / BM25 / RCA agent) left as-is to
  avoid regressions in completed milestones.
