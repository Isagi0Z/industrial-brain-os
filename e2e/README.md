# Autonomous End-to-End Browser Validation

A self-contained [Playwright](https://playwright.dev) suite that validates the
running Industrial Brain OS application the way a real operator would — driving
**real Google Chrome** (`channel: 'chrome'`), with human-like mouse movement,
variable-cadence typing, scrolling, and think-time.

It is deliberately **not** an API test suite: every workflow is exercised
through the browser (uploads use a real file picker, chat is observed on the live
WebSocket, the knowledge graph is clicked on its canvas, dark mode is toggled
from the UI, etc.).

## What it validates

| Area | Coverage |
|------|----------|
| Auth & authz | Login happy-path, bad-credential rejection, signup duplicate/validation, route-guard redirects, session-end re-guard |
| Navigation | All 7 sidebar routes + Settings, active state, infra health widget |
| Documents | Library list, search, status filter, empty state, real PDF upload, ingestion poll, details view, delete (with confirm dialog) |
| Copilot chat | WebSocket connect, streamed answer (observed on the wire), citations, input guards, conversation reset |
| Knowledge graph | Seeded P-102A subgraph render, depth expansion, node inspection, graceful unknown-tag handling |
| Intelligence brains | Live status panels for Maintenance / Compliance / RCA / Lessons Learned |
| Settings & theming | Settings cards, dark-mode toggle, `<html>` class application, persistence across reload |
| Responsiveness | Mobile off-canvas sidebar, tablet overflow check |
| Accessibility | axe-core (WCAG 2 A/AA) scans of core pages |
| Resilience | 404 route, aborted-API graceful degradation, multi-tab parallel sessions |
| Cross-cutting | Console/pageerror capture, 5xx capture, performance timings, screenshots, video, traces — on every test |

## Prerequisites

- **Backend** healthy on `:8000` (`make dev` / uvicorn). Global setup waits for
  `/api/v1/health` and attempts to start uvicorn if it is down.
- **Ollama** running (for chat generation) — optional; chat degrades gracefully.
- **Demo data** seeded so the graph/chat are meaningful:
  `python scripts/load_demo_data.py` (seeds the Neo4j P-102A subgraph and
  generates the `demo_data/` PDFs used for upload).
- The frontend is started automatically by Playwright's `webServer` on port
  `5199` (reused if already running).

> **Ingestion note:** full document indexing runs on the Celery worker
> (`celery -A app.worker worker`, or the `ib_worker` container). If it is not
> running, uploads are accepted and queued but never reach `PROCESSED`; the
> upload test records that as a warning and continues.

## Running

```bash
cd e2e
pnpm install --ignore-workspace
pnpm exec playwright install ffmpeg   # once, for video capture (system Chrome needs no chromium download)

pnpm test                 # full suite
pnpm run report:build     # regenerate reports/e2e/*.md from results.json
pnpm run report:open      # open the interactive HTML report
```

Useful filters:

```bash
pnpm exec playwright test --project=setup            # just establish the session
pnpm exec playwright test tests/04-chat.spec.ts      # one spec
E2E_HEADED=1 pnpm test                               # watch it drive Chrome
```

Overridable env: `E2E_BACKEND`, `E2E_BASE_URL`, `E2E_PORT`, `E2E_USER`, `E2E_PASS`.

## Layout

```
e2e/
  playwright.config.ts     # Chrome channel, trace/video/screenshot=on, 3 projects
  global-setup.ts          # backend health gate + idempotent test-user provisioning
  tests/
    auth.setup.ts          # logs in via the UI, saves the shared storage state
    01-auth.spec.ts        # guest project (no session)
    02..09-*.spec.ts       # app project (authenticated via storage state)
    fixtures.ts            # auto console/network observation per test
  pages/                   # page objects (AppShell, Auth, Documents, Chat, Graph)
  utils/                   # human behaviour, findings, a11y, media, config, paths
  scripts/build-report.mjs # results.json -> reports/e2e/*.md
```

## Output

Everything lands in [`../reports/e2e/`](../reports/e2e/): `summary.md`,
`failures.md`, `warnings.md`, `suggestions.md`, `performance.md`, `coverage.md`,
curated `screenshots/`, the interactive `html-report/`, and per-test
`artifacts/` (traces + videos). The bulky `html-report/` and `artifacts/` are
git-ignored and regenerated on each run; the markdown reports and screenshots
are committed.
