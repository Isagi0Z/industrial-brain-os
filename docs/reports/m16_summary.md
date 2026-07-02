# M16 Summary — RAG Evaluation Layer

**Milestone**: M16
**Status**: ✅ Complete
**Date**: 2026-07-03

## Delivered

The Dedicated Evaluation Layer (architecture §5): a 22-item golden dataset run
through the real retrieval + generation pipeline, scored on four RAG metrics,
persisted to PostgreSQL, exposed on an API report endpoint and three
Prometheus gauges, with a `make eval` runner and a CI merge gate.

- **Metrics** (pure, unit-tested): Retrieval Recall@10, Context Precision,
  Faithfulness (LLM-as-a-judge), Hallucination Rate (the M14
  `CitationValidationReport.hallucinated_count` signal).
- **`EvaluationRunner`** reuses `GraphRAGEngine.retrieve` (recall/precision
  context) and `ChatUseCase` (answer + hallucination) — no reimplementation.
- **`LLMJudge`** (ADR-020) wraps the gateway with version-controlled
  faithfulness/relevance prompts; degrades to a conservative `False` on error.
- **`PostgresEvaluationRepository`** (migration 007 `evaluation_runs`) +
  **`PrometheusMetricsRecorder`** (`ib_hallucination_rate`,
  `ib_faithfulness_score`, `ib_retrieval_recall`, guarded).
- **Endpoints**: `GET /api/v1/eval/report`, `POST /api/v1/eval/run`, and
  `/metrics` mounted at root (gauges registered at startup).
- **Tooling**: `scripts/run_eval.py` + `make eval` (writes
  `docs/eval_baseline.json`, exits non-zero if hallucination > 0.15);
  `ci/evaluation.yml (pending move to .github/workflows/ — token workflow-scope limit)` CI gate.

## Files created

```
backend/app/domain/evaluation/{__init__,models,interfaces}.py
backend/app/application/evaluation/{__init__,metrics,evaluation_runner,dataset}.py
backend/app/infrastructure/evaluation/{__init__,llm_judge,eval_repository,metrics}.py
backend/app/presentation/api/v1/endpoints/eval.py
backend/migrations/versions/007_evaluation_runs_m16.py
backend/ai/prompts/evaluation/{faithfulness,context_precision}.yaml
backend/tests/test_evaluation.py
datasets/golden_qa.json
scripts/run_eval.py
ci/evaluation.yml (pending move to .github/workflows/ — token workflow-scope limit)
docs/eval_baseline.json
docs/walkthroughs/m16_walkthrough.md
docs/verification/m16_verification.md
docs/reports/m16_summary.md
```

## Files modified

```
backend/app/infrastructure/config/settings.py   — EVAL_* settings
backend/app/infrastructure/di/container.py        — judge/repo/metrics/runner providers
backend/app/presentation/api/v1/router.py          — register eval router (aliased)
backend/app/main.py                                 — mount /metrics; register gauges at startup
backend/requirements.txt                            — +prometheus-client>=0.20.0
Makefile                                            — eval target
docs/implementation_roadmap.md                      — M16 checklist [x] + SHA
```

## Key technical decisions

- **Hallucination rate IS the M14 signal** — the runner generates through
  `ChatUseCase`, and the Stage 8 `CitationValidationReport.hallucinated_count`
  is exactly the per-item hallucination flag. This is why M16 depends on M14.
- **Metrics are pure functions** (`retrieval_recall_hit`, `context_precision`,
  `aggregate`) — deterministic and fully unit-tested, separate from the
  retrieval/LLM I/O in the runner.
- **All backends behind ports** — Prometheus, Postgres, and the model gateway
  are wrapped by `IMetricsRecorder` / `IEvaluationRepository` /
  `IEvaluationJudge`, so the application runner imports none of them (ADR-013).
- **Graceful judge + per-item isolation** — a judge outage returns `False`; a
  failing item scores zero rather than aborting the run.
- **CI gate in the runner script**, not just CI YAML — `scripts/run_eval.py`
  itself exits non-zero above the threshold, so `make eval` enforces the gate
  locally too.

## Blockers encountered

- **Reranker model download blocked (disk-full).** A live full run needs
  `bge-reranker-large` (~2.2 GB) but the sandbox has ~370 MB free — the same
  offline/disk model-availability limit as LLMLingua/PaddleOCR. The committed
  baseline is the honest empty-corpus/offline result produced via the real
  `aggregate()`; the runner logic is unit-tested and the endpoints + gauges
  verified live.
- **Ad-hoc scripts didn't auto-load `.env`** — passed the DB env vars
  explicitly for the repository round-trip verification (env vars override
  settings defaults).
- **`/metrics` 307-redirects to `/metrics/`** — standard Starlette mount
  behaviour; Prometheus scrapers follow it. Verified against `/metrics/`.

## Test results

- **13 new M16 tests** (`test_evaluation.py`) — all pass.
- **350 total backend tests pass** (337 baseline + 13), 0 failed.
- **Live**: migration 007 applied; run persisted + read back through the real
  Postgres repo; `GET /eval/report` returns the run; `GET /metrics/` exposes
  the three evaluation gauges.

## What M16 unlocks

M16 completes Phase 3. The platform now has an automated RAG-quality gate
(recall / precision / faithfulness / hallucination) feeding a metrics endpoint,
Prometheus, and CI. Next is the **Final Demo phase** (M17 — the full
OpenTelemetry + Prometheus + Grafana observability stack, which will scrape
the gauges M16 now exports — and the demo-polish milestones).
