# Troubleshooting Guide

Real issues encountered while building and operating this project, with the
verified fix for each — not speculative advice.

---

## Installation & Environment

### `pip install` fails with `SSLCertVerificationError` / `CERTIFICATE_VERIFY_FAILED`

Common on corporate networks with an SSL-inspecting proxy. Retry with
trusted hosts:

```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org -r backend/requirements.txt
```

The same flags work for `pip install <single-package>` and for `pip-audit`.

### `pytest` fails with `PermissionError: [WinError 5] Access is denied` on Windows

This is a Windows temp-directory ACL issue with pytest's `tmp_path` fixture,
not a code bug — every test using `tmp_path` fails identically regardless of
what it does. Work around it with an explicit, writable basetemp:

```powershell
pytest --basetemp=C:\temp\pytest-tmp
```

### `ModuleNotFoundError: No module named 'jsonschema'` (or another dev-only package) even though it's in `requirements.txt`

The package wasn't actually installed in your active venv yet — re-run
`pip install -r backend/requirements.txt` inside the **activated** venv,
watching for the SSL issue above. Confirm which Python you're using with
`python -c "import sys; print(sys.executable)"`.

### `mypy` reports `Source file found twice under different module names`

This happens when you pass mypy a bare file path from inside `backend/`
without package context (e.g. `mypy app/foo.py` from `backend/`). Use
`mypy --explicit-package-bases app/foo.py`, or run mypy against the whole
`app` package rather than an individual file.

---

## Docker & Infrastructure

### `docker compose up` — a service shows `(unhealthy)` but seems to be responding

`ib_qdrant` and `ib_minio` are known to occasionally report an unhealthy
Docker healthcheck label while still serving requests correctly (their
healthcheck probes are stricter than what the application actually needs).
Verify the service directly before assuming it's actually down:

```bash
curl http://localhost:6333/collections     # Qdrant
curl http://localhost:9000/minio/health/live  # MinIO
```

If both respond, the app is fine — the label is cosmetic in this setup.

### Port 3000 conflict between Grafana and the Vite dev server

Both default to port 3000. Either:
- Stop Grafana while doing frontend dev: `docker stop ib_grafana` (restart
  with `docker start ib_grafana` when done), or
- Change one port — e.g. run Vite on a different port:
  `pnpm exec vite --port 5199`, or edit `frontend/vite.config.ts`'s
  `server.port`.

### `docker compose down -v` and now nothing works

`-v` deletes the named volumes — all data is gone by design. Re-run:
```bash
docker compose up -d
cd backend && alembic upgrade head && cd ..
python scripts/init_infra.py
```

### Docker Desktop never comes up (engine "starting" forever, `docker info` hangs)

Two distinct failure modes were hit and verified on Windows:

1. **Backend crash-loop on a corrupted socket.** Check
   `%LOCALAPPDATA%\Docker\log\host\com.docker.backend.exe.log` (or
   `docker-desktop.exe.log` on newer versions) for
   `initializing Inference manager: ... dockerInference: The file cannot be
   accessed by the system`. The AI-inference unix socket in
   `%LOCALAPPDATA%\Docker\run\` is corrupted and Windows cannot delete it
   directly (`del` and `Remove-Item` both fail). Fix: stop all Docker
   processes, then **rename the parent directory** —
   `Rename-Item "$env:LOCALAPPDATA\Docker\run" run_corrupted` — Docker
   recreates it fresh on the next launch.

2. **Engine VM won't start under memory pressure.** On a 16 GB machine with
   Ollama models resident, the `docker-desktop` WSL distro can fail to boot
   silently. Free RAM first: unload Ollama models
   (`curl -d '{"model":"llama3.2","keep_alive":0}' localhost:11434/api/generate`)
   and `wsl --terminate <unused distro>`.

**Reliable fallback — run the stack in a WSL distro's own Docker.** If the
Ubuntu distro has docker-ce installed (`wsl -d Ubuntu -- docker ps` works),
Docker Desktop is not needed at all; WSL2 forwards every published container
port to Windows `localhost` automatically:

```bash
wsl -d Ubuntu -- bash -lc "cd /mnt/d/industrial-brain && \
  docker compose up -d --no-deps postgres neo4j qdrant redis minio jaeger prometheus grafana"
```

`--no-deps` matters: `prometheus` declares `depends_on: ib_backend`, and the
containerized backend image build currently fails on a Python-version pin
(python:3.9 base vs. py3.10-only wheels) — the backend and worker are run
natively on the host instead (see [INSTALLATION.md](INSTALLATION.md)).

---

## Ollama

### `curl http://127.0.0.1:11434/api/version` fails / connection refused

The server isn't running. Start it:
```bash
ollama serve
```
(On Windows/macOS, the installer normally runs this as a background service
automatically — check Task Manager / Activity Monitor for an `ollama`
process if `ollama serve` says the port is already in use.)

### Ollama responds but `llama3.2` inference fails / model not found

The model wasn't pulled (or was wiped by a reinstall — Ollama reinstalls do
**not** preserve previously pulled models). Re-pull it:
```bash
ollama pull llama3.2
```

### Chat/brain responses are extremely slow (10–75+ seconds)

Expected on CPU-only hardware — `llama3.2` generation is the dominant cost in
the pipeline. This is a hardware constraint, not a bug (see
`docs/verification/m20_verification.md` for measured numbers). GPU
acceleration is the fix; see `ADMIN_GUIDE.md` §3.

---

## Backend / API

### `401 Unauthorized` on an endpoint you were previously calling successfully

Your JWT access token expired. Re-authenticate via `POST /auth/login`, or use
`POST /auth/refresh` with your refresh token. Frontend sessions store the
token in `localStorage` (`ib_auth_token`) — clearing it and logging in again
also resolves this.

### `psycopg2.errors.UndefinedColumn: column "created_at" does not exist` on the `users` table

The baseline `users` table (see `ARCHITECTURE.md` §2 folder structure →
migrations) does **not** have a `created_at` column — don't assume every
table has audit timestamp columns; check the actual migration
(`backend/migrations/versions/001_baseline_schema.py`) before writing a query
against it.

### The reranker or LLMLingua model is very slow (or silently not compressing) on first use

Both are lazy-loaded from HuggingFace on first call and cached in the backend
process afterward — the first request after a cold start pays the download +
load cost. If a model fails to download entirely (offline environment, disk
space, blocked registry), both degrade to a **pass-through no-op** rather
than failing the request — check the backend logs for a
"reranker/LLMLingua unavailable" warning to confirm this is what happened.

### Bandit flags a "possible SQL injection" on a query that only uses fixed literals

`backend/app/infrastructure/rca/incident_history_repository.py` builds its
`WHERE` clause from a fixed, repeated literal (`"description ILIKE %s"`) with
every actual value passed as a bound parameter — this is bandit's B608
pattern-matcher being overly broad, not a real vulnerability. It's already
annotated `# nosec B608` with the justification inline; if you hit this
pattern elsewhere, the fix is the same: separate the query-string
construction (comment explaining why it's safe) from parameter binding, and
annotate.

### A prompt change fails `make validate-prompts`

Check the specific error:
- `[schema]` — the YAML is missing required metadata (`prompt_id`, `version`,
  `description`, `owning_brain`, `output_format`, `system`). See
  `backend/ai/prompts/prompt_schema.json`.
- `[manifest]` — you edited the prompt file but not
  `backend/ai/prompts/MANIFEST.yaml` (or vice versa) — they must agree on
  `prompt_id`, `version`, `owning_brain`, and `path`.
- `[render]` — a `*_template` field references a `{variable}` that can't be
  supplied, usually a typo in the placeholder name.
- `[hardcoded]` — a `system_prompt = "You are..."`-shaped literal was found
  in Python source; move it into a prompt YAML.

---

## Frontend

### The UI renders with no styling at all (or looks like plain HTML)

Tailwind isn't compiling. Verify both `frontend/tailwind.config.js` **and**
`frontend/postcss.config.js` exist — Vite silently serves unprocessed CSS if
either is missing, since the `@tailwind` directives in `index.css` never get
expanded (this exact bug existed until M-UI-transform; if you see it again,
one of these two config files went missing).

### Dark mode / light mode doesn't match the toggle, or looks like the wrong theme is "stuck"

Check `frontend/index.html` — the `<body>` tag must **not** hardcode any
`bg-*`/`text-*` Tailwind classes. Theme switching works by toggling a `.dark`
class on `<html>` (see `frontend/src/context/ThemeContext.tsx`) and letting
CSS custom properties in `frontend/src/index.css` cascade; a hardcoded class
on `<body>` overrides the theme system entirely (this was a real regression
— see `docs/reports/` for the UI-transformation report).

### PDF viewer fails to load / worker error in the console

`react-pdf`'s PDF.js worker needs a matching `pdfjs-dist` version resolvable
at the top level of `node_modules` (pnpm doesn't hoist nested deps by
default). Check `frontend/package.json` has `pdfjs-dist` pinned to the exact
version `react-pdf` bundles internally, then `pnpm install` again.

### `pnpm build` warns about a chunk larger than 500 kB

Expected today — the app is a single-bundle SPA (framer-motion, cytoscape,
react-pdf, and the full route table all ship in one chunk). This is a known,
accepted trade-off, not a build failure; code-splitting via
`React.lazy()`/dynamic `import()` per route is the fix if bundle size becomes
a real problem.

### `pnpm audit --audit-level high` reports a vite vulnerability

Check the currently pinned `vite` version in `frontend/package.json` against
the advisory's patched range — this project has already been bumped once
(5.4.21 → 6.4.3) to clear GHSA-fx2h-pf6j-xcff. If a new one appears, bump
`vite` again and re-run `pnpm build` + `pnpm run lint` to confirm nothing
broke.

---

## Ingestion Pipeline

### An uploaded document is stuck in `QUEUED` / `READY_FOR_PROCESSING` and never starts processing

This is the most common local-setup issue. The upload succeeds (HTTP 201) and
the API dispatches the ingestion chain onto the Redis `ingestion` queue — but
**nothing consumes that queue unless a worker is running.** With the default
`INGESTION_BACKEND=celery`, the API does *not* process documents itself; a
separate Celery worker must be running.

Fix — start the worker in its own terminal (leave it running alongside the
backend and frontend):

```bash
python scripts/run_worker.py          # make-free launcher (recommended)
# or:  make worker
# or:  cd backend && celery -A app.worker worker -Q ingestion --pool=solo
```

On Windows the `--pool=solo` flag is required (Celery's default prefork pool
cannot `fork`). Once the worker is up it drains the backlog automatically; watch
its log for `Task ingestion.parse … succeeded`. Large PDFs (hundreds of chunks)
embed slowly on CPU and can hold the single-process worker for several minutes —
that is throughput, not an error. To confirm work is flowing, check the queue
depth (`redis-cli -n 1 LLEN ingestion`) is falling and Qdrant's
`document_chunks` point count is rising.

Alternatively, for a single-node demo you can skip the separate worker entirely
by running ingestion in-process: set `INGESTION_BACKEND=redis-queue` and restart
the backend — the API then starts an in-process worker thread automatically (see
`ADR-015`; Celery remains the default for scaled/production deployments).

### A document is stuck in `PROCESSING` / never finishes

1. Check the Celery worker is actually running:
   `docker compose logs ib_worker` (or your local `python scripts/run_worker.py`
   / `celery -A app.worker worker` terminal).
2. Check `GET /api/v1/documents/{id}/status` for an `error_message`.
3. Check Jaeger for the `celery.parse_task`/`embed_task`/`kg_task` spans for
   that document's correlation id to see exactly which stage is stuck or
   failed.
4. Retry: `POST /api/v1/documents/{id}/retry` (up to 3 automatic retries with
   60/120/240s backoff already happen before it's marked `FAILED`).

### KG traversal / Knowledge Graph view returns an empty graph for a tag you know exists

- Confirm the document mentioning that tag has fully finished ingestion
  (`PROCESSED`, not just `PROCESSING`) — KG writes happen in the last stage
  of the Celery chain (`kg_task`).
- Confirm the tag format matches exactly what's in Neo4j — traversal MATCHes
  on exact `tag_number`, not a fuzzy/partial match.
- Try `depth=2` or `3` — depth 1 only shows directly connected nodes.

---

## Evaluation

### `make eval` fails or reports `hallucination_rate` above threshold

1. Read `docs/eval_baseline.json` for the last run's numbers.
2. If `retrieval_recall`/`context_precision` are 0, check whether the golden
   dataset's documents (`datasets/golden_qa.json` references e.g. `P-102A`,
   `FT-101`) are actually ingested — an empty/mismatched corpus produces 0
   recall by construction, which is expected and documented, not a bug.
3. If `hallucination_rate` is genuinely elevated, inspect individual failing
   items — the runner logs enough to identify which golden question produced
   an uncited/miscited answer.

---

## Still Stuck?

- Check the relevant milestone's verification doc under `docs/verification/`
  — many "is this expected?" questions are already answered there with the
  exact numbers/behavior that was verified at build time.
- Check `docs/architecture_decision_records.md` for *why* something is built
  the way it is before assuming it's a bug.
- See [`FAQ.md`](FAQ.md) for shorter, common questions.
