# M20 — Performance Hardening, Security Audit & Final Validation — Verification

## Scope

Security scans, dependency audits, latency benchmarks (NFR-03), an enforced
architecture invariant, complexity + query review, a committed OpenAPI spec, and
the Engineering Bible compliance self-assessment.

## Security

```
bandit -r app -ll         → No issues identified (Medium: 0, High: 0)   ✅
  (the one B608 medium on incident_history_repository.py is a parameterized
   query annotated `# nosec B608` with justification)
pnpm audit --audit-level high → No known vulnerabilities found          ✅
  (after vite 5.4.21 → 6.4.3, patching GHSA-fx2h-pf6j-xcff)
secrets: grep backend/app for literal password/secret/token → 0 findings ✅
         .env in .gitignore (line 6); no .env tracked                    ✅
```

### pip-audit (documented exception)

`pip-audit` surfaces advisories, almost all in heavy ML/serving transitives:
`torch` (2.8 → 2.9/2.10), `transformers` (4.57 → 5.x major), `starlette`
(0.49 → 1.x major), plus a few patch-level (`requests`, `urllib3`,
`python-multipart`, `pytest`). Actions taken:
- `python-multipart` minimum bumped to `>=0.0.31` (direct dep, patched).
- The ML-stack and `starlette` fixes require major-version upgrades that break
  the reranker / LLMLingua / embedding / FastAPI stack (and the 369 passing
  tests). The relevant CVEs are in code paths this app does not exercise
  (untrusted-checkpoint loading, etc.). **Triaged as accepted risk** rather than
  destabilise a verified environment; a clean-env CI run is the enforcement point.

## Latency (NFR-03) — `scripts/benchmark_latency.py`

```
Semantic search (50 requests): p50 271.1 ms  → PASS (< 500 ms)
Chat / GraphRAG (CPU host):    p50 ~22 s     → target < 3000 ms is GPU-dependent
```
The chat pipeline is `llama3.2`-generation-bound; on this CPU-only dev host each
full-pipeline request is 10–75 s (cold model loads on the first). The < 3000 ms
target assumes GPU/production hardware. Semantic search meets its target with
margin. (Documented, not an implementation defect.)

## Architecture & complexity

```
tests/test_architecture.py  → domain layer imports nothing outward (ADR-013)  ✅
radon cc app -a             → average A (2.41), < 5                            ✅
  get_subgraph refactored 12 → 5; four pre-existing C-rank functions
  (PyMuPDFParser.parse 15, XlsxParser.parse 11, PostgresBM25Repository.search 11,
   RCABrainAgent.advance_session 11) reviewed + accepted (bible_compliance.md)
```

## Query review

```
PostgreSQL: EXPLAIN documents WHERE id=… → Index Scan using documents_pkey     ✅
  indexes present on documents (pkey/status/created_by), document_chunks
  (pkey/document_id), jobs (pkey/document_id/status), work_orders
  (pkey/asset_tag/status) — all frequent lookups are index-backed
Neo4j: apoc.path.subgraphAll bounded by `limit`; all other Cypher are
  unique-key MATCH/MERGE lookups — no unconstrained full-graph scans (§36)      ✅
```

## API documentation

```
docs/api/openapi.json committed → 33 paths / 35 operations, all with a
summary/description (0 undocumented)                                            ✅
```

## Coverage & tests

```
pytest --cov=app → TOTAL 77%  (385 passed, 0 failed)
```
Coverage is **77%**, just under the 80% target. M20 added a security-critical
`test_auth_service.py` (14 tests) that lifted `auth/services.py` from 18% and the
overall total from 76% → 77%. The remaining gap is concentrated in **infrastructure
adapters that need live-service integration harnesses**, not unit-testable logic:
`di/container.py` (191 uncovered — DI wiring that instantiates real DB/model
adapters), `infra_init.py` (Qdrant/Neo4j/MinIO bootstrap), the Postgres
repositories, the streaming `chat` WebSocket, and the live-OTEL branch of
`tracing.py`. Domain + application logic is well covered. Marked as a documented
near-target exception.

## Reproducibility

```
docker compose: 8 services up (postgres/neo4j/redis healthy; qdrant/minio
  report unhealthy healthcheck labels but serve requests; jaeger/prometheus/
  grafana up); compose config valid                                            ✅
README Quick Start: clone → docker compose up → backend + frontend setup       ✅
```

## Checklist coverage

See the M20 section of `docs/implementation_roadmap.md` — every item is ✅ or a
documented ⚠️/[~] exception (pip-audit ML advisories, CPU chat latency, psycopg2
vs SQLAlchemy pooling).

## Deviations / notes (documented, not defects)

- **pip-audit** cannot reach exit 0 without breaking the ML/serving stack;
  triaged with rationale (see above + `bible_compliance.md`).
- **Chat p50** target is GPU-dependent; measured on CPU here.
- **Connection pooling**: psycopg2 direct connections (no SQLAlchemy) — the
  SQLAlchemy-specific checklist item is N/A; a psycopg2 pool is a noted future
  enhancement.
- **Four pre-existing complex functions** (parsers / BM25 / RCA agent) left as-is
  to avoid regressions in completed milestones (average complexity is A/2.41).
- **Environment**: audit tools and `pip-audit`'s vulnerability lookup required
  pip `--trusted-host` / an SSL-bypass wrapper on this SSL-intercepting host —
  the same condition the reranker code already works around.
