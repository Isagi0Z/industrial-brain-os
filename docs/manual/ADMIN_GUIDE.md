# Administrator Guide

For operators running and maintaining an Industrial Brain OS deployment.
Covers user management, ongoing operations, monitoring, performance tuning,
and security administration. For first-time deployment, see
[`DEPLOYMENT.md`](DEPLOYMENT.md).

---

## 1. User Management

Self-service account creation is available at `POST /auth/register` (see
[`API_REFERENCE.md`](API_REFERENCE.md#post-authregister)) and via the
console's **Sign up** page — anyone who can reach the login screen can create
an account. There is **no admin UI** yet for managing existing users
(deactivating, assigning roles, resetting a password) — those still require a
direct PostgreSQL `users` table update, and there is no email verification or
rate limiting on registration. If you need to lock down account creation for
a shared/production deployment before those controls exist, put the
`/auth/register` route behind your reverse proxy's auth or remove it from the
router.

### Default development admin

In `APP_ENV=development`, the backend's seeder
(`backend/app/infrastructure/database/seeder.py`) automatically creates:

```
email:    admin@industrialbrain.local
password: ChangeMe123!
```

> **This account must never exist with its default password outside a local
> dev environment.** The seeder only runs when `APP_ENV=development`, but if
> you ever seed a shared environment, change this password immediately via a
> direct database update (there is no "force password change" flow yet).

### Creating a new user

The normal path is self-service: `POST /auth/register` or the console's
**Sign up** page (see `API_REFERENCE.md`). Provision a user directly in
PostgreSQL only when you need to bypass that flow — e.g. scripting a batch of
accounts, or `/auth/register` has been disabled per §1 above:

```bash
cd backend
python -c "
from app.infrastructure.auth.password_hasher import PasswordHasher
print(PasswordHasher().get_password_hash('the-new-password'))
"
```

Then insert directly:

```sql
INSERT INTO users (id, email, hashed_password, full_name, is_active)
VALUES (gen_random_uuid()::text, 'engineer@example.com', '<hash from above>', 'Jane Engineer', true);
```

### Deactivating a user

```sql
UPDATE users SET is_active = false WHERE email = 'former.employee@example.com';
```
`User.has_permission()` and `AuthUseCase.verify_access_token()` both
short-circuit to deny for inactive users, so this immediately revokes access
even for an unexpired token.

### RBAC status (read before relying on roles)

A `roles` table exists (`id`, `name`, `description`, `permissions JSONB`) and
the domain model (`User.roles: List[Role]`) supports full RBAC, but **role
hydration from the database is not yet wired** —
`backend/app/infrastructure/auth/user_repository.py` has a documented
`# TODO: Hydrate roles and permissions when RBAC schema is finalized`. In the
current build, every authenticated user's `roles` list is empty, so:

- `User.has_permission(...)` always returns `False`.
- Endpoints that resolve a role scope from the user (e.g. the Knowledge Brain
  chat endpoint) fall back to the `"public"` role scope for everyone.

**If you need enforced RBAC before this is finished upstream**, the fix is
localized: extend `user_repository.py`'s `get_by_email`/`get_by_id` to join
`users` against a `user_roles` mapping table (not yet defined — you'll need a
migration for it) and `roles`, populating `User.roles`. Until then, treat this
deployment as **single-tier authenticated access** — anyone with a valid
account can reach anything a valid account can reach.

---

## 2. Monitoring & Dashboards

| Tool | URL | What it shows |
|---|---|---|
| Grafana | `http://localhost:3000` | Two auto-provisioned dashboards: **API Performance** (request rate, p50/p95/p99 latency, LLM token usage, Celery task rate, active WebSocket connections) and **RAG Quality** (hallucination rate, faithfulness, recall trend from the M16 evaluation gauges) |
| Prometheus | `http://localhost:9090` | Raw metrics + alerting rules (none configured by default — add your own) |
| Jaeger | `http://localhost:16686` | Distributed traces — search by service `industrial-brain-api` or `industrial-brain-worker`, or by a Correlation-ID copied from a log line |
| `/metrics` | `http://localhost:8000/metrics` | Raw Prometheus exposition (useful for `curl`-based spot checks) |

Grafana ships with default credentials `admin`/`admin`
(`GRAFANA_ADMIN_USER`/`GRAFANA_ADMIN_PASSWORD` env vars) — **change these**
before exposing Grafana beyond localhost.

### Correlating a slow/failed request

1. Find the `X-Correlation-ID` response header (or `correlation_id` field in
   the JSON logs) for the request in question.
2. Search that id in Jaeger — you'll see the full span tree (`llm.generate`,
   `vector_db.search`, `graph_db.traverse`, `celery.*`) with per-stage
   latency.
3. Cross-reference the same id in your log aggregator (stdout, in this
   project's default setup) — every log line the request touched carries the
   same `correlation_id` and (if OTel is enabled) `trace_id`.

---

## 3. Performance Tuning

| Symptom | Where to look | What to change |
|---|---|---|
| Slow semantic search (target: p50 < 500ms, NFR-03) | `vector_db.search` spans in Jaeger | Qdrant collection size/replication; consider a smaller `top_k` |
| Slow chat / GraphRAG (target: p50 < 3000ms on GPU hardware) | `llm.generate` span latency | This is almost always Ollama generation time on CPU — the single biggest lever is running Ollama with GPU acceleration; see `docs/verification/m20_verification.md` for measured CPU numbers (~10–75s per request without a GPU) |
| High reranker latency on first request | Cold model load — `BAAI/bge-reranker-large` and LLMLingua load lazily on first use | Warm them at startup with a health-check request, or accept the one-time cost |
| Ingestion backlog | `ib_celery_tasks_total` in Grafana; Celery worker logs | Increase `CELERY_WORKER_CONCURRENCY`; run multiple `ib_worker` replicas (they're stateless — see `ARCHITECTURE.md` §7) |
| Elevated hallucination rate | `GET /api/v1/eval/report`, Grafana RAG Quality dashboard | Increase `GRAPHRAG_TOKEN_BUDGET`, tune `GRAPHRAG_COMPRESSION_RATIO`, or investigate specific golden-QA failures via `python scripts/run_eval.py` |
| PostgreSQL slow queries | `EXPLAIN ANALYZE` the query | Every high-frequency query already hits a PK/unique index (documents by id, chunks by document_id, jobs by document_id/status, work_orders by asset_tag/status) — see `docs/verification/m20_verification.md` for the baseline review |

Run the benchmark suite to get current numbers:

```bash
make benchmark          # scripts/benchmark_latency.py
```

Run a full security + dependency audit periodically:

```bash
make security-audit     # bandit + pip-audit + pnpm audit
```

---

## 4. Security Administration

- **Rotate `SECRET_KEY`** (JWT signing) whenever a deployment moves beyond
  local development — a leaked key lets an attacker forge tokens for any
  user.
- **Rotate infrastructure passwords** (`POSTGRES_PASSWORD`,
  `NEO4J_PASSWORD`, `REDIS_PASSWORD`, `MINIO_ROOT_PASSWORD`,
  `GRAFANA_ADMIN_PASSWORD`) — the shipped `.env.example` defaults are for
  local development only.
- **Review audit logs** — every login success/failure, token refresh, and
  logout is recorded by `infrastructure/logging/audit.py` with correlation
  id, user id, IP, and user agent. These currently go to the same structured
  JSON log stream as everything else; route them to a dedicated sink if you
  need longer retention or tamper-evidence.
- **Run `make security-audit` on a schedule** (weekly, or on every dependency
  bump) — see `docs/bible_compliance.md` for the currently-accepted risk
  exceptions (a small set of ML-library CVEs whose fixes require breaking
  major-version bumps).
- **Never commit `.env`** — it's gitignored; verify with `git check-ignore
  .env` if you're ever unsure.
- See [`ARCHITECTURE.md` §11](ARCHITECTURE.md#11-security) for the full
  security architecture, and [`DEPLOYMENT.md`](DEPLOYMENT.md#4-production-checklist)
  for the pre-launch checklist.

---

## 5. Routine Operations

| Task | Command |
|---|---|
| Check all service health | `curl http://localhost:8000/api/v1/health` |
| Check container status | `docker compose ps` |
| Tail backend logs | `docker compose logs -f ib_backend` |
| Tail worker logs | `docker compose logs -f ib_worker` |
| Apply new migrations after a pull | `cd backend && alembic upgrade head` |
| Re-run the evaluation baseline | `make eval` |
| Validate prompts after an edit | `make validate-prompts` |
| Back up all data | See [`DEPLOYMENT.md` §Backup & Restore](DEPLOYMENT.md#5-backup-and-restore) |

---

## 6. Capacity Notes

- **Neo4j Community** is single-node (no clustering) — this is a deliberate,
  documented trade-off (ADR-004); all KG traversals are depth/edge-bounded to
  keep this safe at scale (`GRAPHRAG_MAX_KG_DEPTH`, `GRAPHRAG_KG_TRAVERSAL_LIMIT`).
- **Celery workers are stateless** and can be scaled horizontally by running
  additional `ib_worker` replicas against the same Redis broker.
- **The reranker and LLMLingua models are loaded once per backend process**
  (not per request) — each `ib_backend` replica pays the model-load cost once
  at first use, then serves from memory.
