# API Reference

Base URL (local dev): `http://localhost:8000/api/v1`

**Interactive docs** (always the most current source of truth, generated
directly from the FastAPI app): `http://localhost:8000/docs` (Swagger UI) or
`http://localhost:8000/redoc`. A generated snapshot is also committed at
[`docs/api/openapi.json`](../api/openapi.json) (33 paths / 35 operations, all
with a summary/description — M20).

This document is a verified, human-readable index of every route. Field-level
schemas are best read from `/docs` since they render live from the Pydantic
models.

---

## Authentication

All endpoints except `POST /auth/login`, `POST /auth/refresh`, and
`GET /health` require a Bearer JWT:

```
Authorization: Bearer <access_token>
```

### `POST /auth/login`

Form-encoded (OAuth2 password grant shape) — **not JSON**:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=you@example.com&password=yourpassword"
```

`username` is matched against the user's **email**. Response:

```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }
```

### `POST /auth/refresh`

```json
{ "refresh_token": "<refresh_token>" }
```
→ new `{ access_token, refresh_token, token_type }` (old refresh token is
revoked — sliding session).

### `POST /auth/logout`

```json
{ "refresh_token": "<refresh_token>" }   // optional
```
Revokes the active access token's `jti` (and the refresh token's, if
supplied). Never raises even if the token is already expired.

### `GET /auth/me`

Returns the current user: `{ id, email, full_name, is_active }`.

There is currently no self-service `POST /auth/register` endpoint — users are
provisioned directly in the `users` table (see
[`ADMIN_GUIDE.md`](ADMIN_GUIDE.md#1-user-management)).

---

## Health

### `GET /health`

No auth required.

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development",
  "databases": {
    "postgres": "healthy",
    "neo4j": "healthy",
    "qdrant": "healthy",
    "redis": "healthy",
    "minio": "healthy"
  }
}
```

Each database is checked with a real, cheap query (`SELECT 1`, etc.); a
failure sets that entry to `"unhealthy: <error>"` and the overall response
still returns 200 so uptime monitors can distinguish "service up" from
"service degraded" by inspecting the body.

---

## Documents — `/documents`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/documents/` | Upload a file (`multipart/form-data`, field name `file`) — creates a job and dispatches ingestion |
| `GET` | `/documents/` | List documents, paginated (`?limit=`, `?status=`) |
| `GET` | `/documents/{id}` | Document detail (status, metadata, versions) |
| `GET` | `/documents/{id}/status` | Ingestion job status + progress percentage |
| `GET` | `/documents/{id}/download` | Download the stored file |
| `GET` | `/documents/{id}/chunks` | List parsed chunks for a document |
| `POST` | `/documents/{id}/retry` | Re-queue a failed/any job for (re)processing |
| `POST` | `/documents/{id}/restore` | Un-delete a soft-deleted document |
| `PUT` | `/documents/{id}/metadata` | Replace the document's custom metadata JSON |
| `DELETE` | `/documents/{id}` | Soft-delete a document |

```bash
curl -X POST http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@manual.pdf"
```

---

## Search — `/search`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/search/semantic?q=&limit=&role_scope=` | Dense vector search over indexed chunks (Qdrant) |
| `GET` | `/search/keyword?q=&limit=&role_scope=` | BM25 keyword search (PostgreSQL) |

---

## Chat Copilot — `/chat`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/chat` | Single-shot GraphRAG chat (request/response, no streaming) |
| `WS` | `/chat/stream?token=<jwt>` | Streaming chat over WebSocket |

`POST /chat` body:
```json
{ "query": "What is the rated pressure of P-102A?", "session_id": "s1", "top_k": 5, "role_scope": "public" }
```
Response includes `answer`, `citations[]` (chunk_id, document_title,
page_number, excerpt, score), `token_usage`, and `session_id`.

WebSocket protocol: connect to `/api/v1/chat/stream?token=<jwt>`, send
`{"query": "...", "session_id": "...", "top_k": 5, "role_scope": "public"}`,
receive a stream of `{"type": "token", "content": "..."}` messages followed by
a final `{"type": "done", "citations": [...], "token_usage": {...}, "session_id": "..."}`
(or `{"type": "error", "message": "..."}` on failure).

---

## Knowledge Graph — `/graph`

### `GET /graph/subgraph?entity_tag=&depth=&limit=`

Returns a bounded Neo4j subgraph as Cytoscape-compatible JSON, powering the
frontend's Knowledge Graph visualizer (M19).

- `entity_tag` (required) — seed tag, e.g. `P-102A`
- `depth` (1–3, default 1) — traversal depth
- `limit` (≤200, default 200) — max edges returned

```json
{
  "seed": "P-102A",
  "depth": 1,
  "nodes": [{ "data": { "id": "P-102A", "label": "P-102A", "type": "Equipment", "seed": true } }],
  "edges": [{ "data": { "id": "P-102A|MONITORS|FT-101", "source": "FT-101", "target": "P-102A", "label": "MONITORS" } }],
  "stats": { "node_count": 8, "edge_count": 8 }
}
```

---

## Ontology — `/ontology`

### `GET /ontology/schema`

Returns the loaded `industrial_ontology.yaml` as JSON: `version`,
`node_types` (each with `required_properties`/`optional_properties`), and
`allowed_relations` (`source`/`relation`/`target` triples).

---

## The Five Brains — `/brain/*`

Each brain exposes a `POST .../chat` (or session) endpoint that routes
through its full LangGraph agent (retrieve → synthesize → validate citations
→ format), distinct from the simpler `/chat` endpoint above.

| Brain | Endpoint | Notes |
|---|---|---|
| Knowledge | `POST /brain/knowledge/chat` | `{query, session_id}` → `{answer, citations[], session_id, error_flag, step_count, proactive_warning}` |
| Maintenance | `POST /brain/maintenance/chat` | Adds work-order + failure-history context |
| Compliance | `POST /brain/compliance/chat` | Regulation-vs-procedure gap detection + evidence |
| RCA | `POST /brain/rca/session` | Starts/advances a structured 5-Whys session (stateful — see `rca_sessions` table) |
| Lessons Learned | `POST /brain/lessons/chat` | Q&A over historical lessons |

Legacy scaffold status endpoints (pre-brain-agent placeholders, still mounted
for backward compatibility): `GET /knowledge/status`, `/maintenance/status`,
`/compliance/status`, `/rca/status`, `/lessons-learned/status`.

---

## Incidents — `/incidents`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/incidents` | Record an incident (feeds the Lessons Learned brain) |

---

## Jobs — `/jobs`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/jobs/{job_id}` | Ingestion job status by id (same shape as `/documents/{id}/status`) |

---

## Evaluation — `/eval`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/eval/report` | Latest evaluation run's headline metrics |
| `POST` | `/eval/run` | Run the golden dataset now and return the result (long-running — prefer `make eval` / `scripts/run_eval.py` for CI) |

```json
{
  "run_id": "...", "run_date": "...", "total_items": 22,
  "retrieval_recall": 0.0, "context_precision": 0.0,
  "faithfulness": 0.27, "hallucination_rate": 0.0
}
```

---

## Metrics — `/metrics` (root, not under `/api/v1`)

Prometheus exposition format. Includes HTTP/LLM/Celery/WebSocket runtime
metrics (M17) and the three evaluation gauges (`ib_hallucination_rate`,
`ib_faithfulness_score`, `ib_retrieval_recall`) from M16.

---

## Error Shape

FastAPI's standard error envelope:

```json
{ "detail": "human-readable message" }
```

Validation errors (422) use FastAPI's default `detail: [{loc, msg, type}]`
array shape. Domain exceptions are mapped to appropriate HTTP status codes by
`app/presentation/middleware/error_handler.py` (`DomainException` → its
declared status; unhandled exceptions → 500 with no internal detail leaked).

See [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for common error codes and
what causes them.
