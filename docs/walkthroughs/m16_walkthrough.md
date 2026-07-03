# M16 Walkthrough — RAG Evaluation Layer

## Overview

M16 implements the Dedicated Evaluation Layer (architecture §5): a golden
dataset of industrial QA pairs is run through the real retrieval + generation
pipeline, scored on four RAG metrics, persisted, and exposed on an API report
endpoint plus Prometheus gauges.

```
datasets/golden_qa.json (22 items)
        │
EvaluationRunner.run(items)          per item:
        │   GraphRAGEngine.retrieve(top_k=10) ──► Recall@10 (golden source in top-k?)
        │        │                          └──► IEvaluationJudge.judge_relevance ──► Context Precision
        │   ChatUseCase.chat (M14) ──► answer + CitationValidationReport ──► Hallucination (hallucinated_count>0)
        │        │
        │   IEvaluationJudge.judge_faithfulness(answer, context) ──► Faithfulness
        │
   aggregate() → EvaluationRun{retrieval_recall, context_precision,
                               faithfulness, hallucination_rate, total_items}
        │
        ├─ IEvaluationRepository.save → PostgreSQL evaluation_runs (migration 007)
        └─ IMetricsRecorder.record → Prometheus gauges

GET  /api/v1/eval/report  → latest run's metrics
POST /api/v1/eval/run     → run now and return the result
GET  /metrics/            → ib_hallucination_rate / ib_faithfulness_score / ib_retrieval_recall
make eval / scripts/run_eval.py → run + write docs/eval_baseline.json (CI gate)
```

## Reuse (no reimplementation)

- **GraphRAGEngine.retrieve** (M8) supplies the retrieved chunks used for
  Recall@10 and the context judged for precision.
- **ChatUseCase** (M14) generates the answer *and* yields the Stage 8
  `CitationValidationReport` — so the **hallucination metric is exactly the
  M14 signal** (`hallucinated_count > 0`), which was the stated reason M16
  depends on M14.
- The metric machinery is pure and independent of both.

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `evaluation/models.py` (`GoldenQAItem`, `ItemEvaluation`, `EvaluationRun`), `evaluation/interfaces.py` (`IEvaluationJudge`, `IEvaluationRepository`, `IMetricsRecorder`) |
| Application | `evaluation/metrics.py` (pure: `retrieval_recall_hit`, `context_precision`, `aggregate`), `evaluation/evaluation_runner.py` (orchestration), `evaluation/dataset.py` (golden loader) |
| Infrastructure | `evaluation/llm_judge.py` (`LLMJudge` — gateway + prompts), `evaluation/eval_repository.py` (`PostgresEvaluationRepository`), `evaluation/metrics.py` (`PrometheusMetricsRecorder`) |
| Presentation | `endpoints/eval.py` — `GET /eval/report`, `POST /eval/run`; `/metrics` mounted in `main.py` |
| Data | `migrations/versions/007_evaluation_runs_m16.py` |
| Prompts / Data | `ai/prompts/evaluation/{faithfulness,context_precision}.yaml`; `datasets/golden_qa.json`; `docs/eval_baseline.json` |
| Tooling | `scripts/run_eval.py`, `Makefile` `eval` target, `ci/evaluation.yml (pending move to .github/workflows/ — token workflow-scope limit)` |

## The four metrics

- **Retrieval Recall@10** — per item: does any of the top-10 retrieved chunks
  match the golden `(source_document_id, source_page)`? The run's recall is
  the fraction of items that hit.
- **Context Precision** — per item: the fraction of retrieved chunks the LLM
  judge deems relevant to the expected answer; averaged over items.
- **Faithfulness** — per item: the LLM judge decides whether the generated
  answer is derivable from the retrieved context alone (a "no information in
  the documents" answer over empty context is faithful); the run's score is
  the fraction judged faithful.
- **Hallucination Rate** — the fraction of items whose answer cited a
  `[source_N]` marker that did not resolve to a retrieved chunk — i.e. the M14
  `CitationValidationReport.hallucinated_count > 0`.

## LLM-as-a-judge (ADR-020)

`LLMJudge` wraps the model gateway with two version-controlled prompts
(`faithfulness.yaml`, `context_precision.yaml`) that require a YES/NO first
token; `_parse_yes` interprets the response. Both methods degrade to a
conservative `False` on any gateway error, so a judge outage never aborts a
run. Each evaluation item is scored independently — one failing item drops to
a zero score rather than failing the whole run.

## Golden dataset

`datasets/golden_qa.json` — 22 industrial QA pairs across the four required
categories: equipment lookup, procedure query, failure-mode query, and
multi-hop entity-relationship. Each item carries
`{question, expected_answer, source_document_id, source_page,
expected_entity_mentions, category}`.

## Prometheus + CI gate (ADR-017)

- `PrometheusMetricsRecorder` publishes three gauges on the default registry —
  `ib_hallucination_rate`, `ib_faithfulness_score`, `ib_retrieval_recall` —
  updated after every run. `main.py` mounts them at `/metrics` and registers
  them at startup so they read from boot. Guarded so a missing
  `prometheus_client` degrades to a no-op recorder.
- `scripts/run_eval.py` (`make eval`) runs the suite, prints and persists the
  report, writes `docs/eval_baseline.json`, and **exits non-zero when
  `hallucination_rate > EVAL_HALLUCINATION_THRESHOLD` (0.15)** — the CI merge
  gate wired in `ci/evaluation.yml (pending move to .github/workflows/ — token workflow-scope limit)`.

## Configuration

| Setting | Default |
|---------|---------|
| `EVAL_GOLDEN_DATASET` | `datasets/golden_qa.json` |
| `EVAL_TOP_K` | `10` |
| `EVAL_HALLUCINATION_THRESHOLD` | `0.15` |
| `EVAL_FAITHFULNESS_PROMPT_FILE` / `EVAL_CONTEXT_PRECISION_PROMPT_FILE` | `ai/prompts/evaluation/*.yaml` |

## Environment notes

`prometheus-client>=0.20.0` added to `requirements.txt`. Migration 007 creates
`evaluation_runs`. A **live full 22-item run has been executed** with the
cross-encoder reranker (`bge-reranker-large`) and the `llama3.2` judge restored
locally. The committed `docs/eval_baseline.json` reflects the honest
**empty-corpus** condition (recall 0, precision 0 — golden documents not
ingested), with a **model-backed faithfulness of 0.2727**: with no retrieved
context the LLM answers from parametric knowledge and the judge flags most as
ungrounded, while Stage 8 citation validation reports **0 hallucinations** (no
phantom citations to validate). Produced via the real `aggregate()` over all 22
items (`run_id 550c49be`); the runner, judge, metrics, repository, and endpoints
are fully unit-tested and verified live (report + gauges). A model-backed CI run
against an indexed corpus overwrites the recall/precision figures with grounded
values.
