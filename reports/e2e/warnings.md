# Warnings

Non-fatal issues observed during validation (6).

- **uploads a real industrial PDF through the browser and cleans up** — Ingestion did not reach PROCESSED within 60s (last: UNKNOWN). The Celery worker (ib_worker) is likely not running, so uploads queue but are not indexed.
- **connects over WebSocket and answers a grounded question** — Copilot 'done' frame carried 1 citation(s) but no citation card rendered in the UI. The answer used "[source_1]"-style inline references rather than the backend's expected [[chunk:<id>]] markers — investigate the citation display / prompt marker format.
- **accessibility scan (axe-core) of core authenticated pages** — a11y[documents]: 1 serious/critical violation(s) — color-contrast
- **accessibility scan (axe-core) of core authenticated pages** — a11y[knowledge]: 1 serious/critical violation(s) — color-contrast
- **accessibility scan (axe-core) of core authenticated pages** — a11y[knowledge-graph]: 1 serious/critical violation(s) — color-contrast
- **accessibility scan (axe-core) of core authenticated pages** — a11y[settings]: 1 serious/critical violation(s) — color-contrast
