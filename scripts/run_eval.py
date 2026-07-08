"""Evaluation Layer runner (M16) — `make eval`.

Runs the golden dataset through the real retrieval + generation pipeline,
prints the four headline RAG metrics, persists the run to PostgreSQL, and
writes ``docs/eval_baseline.json``. Exits non-zero when the hallucination
rate exceeds ``EVAL_HALLUCINATION_THRESHOLD`` — this is the CI merge gate.

Usage:
    python scripts/run_eval.py [--limit N] [--output PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.application.evaluation.dataset import load_golden_dataset  # noqa: E402
from app.infrastructure.config.settings import settings  # noqa: E402
from app.infrastructure.di.container import container  # noqa: E402


async def _main(limit: int | None, output: Path) -> int:
    dataset_path = _REPO_ROOT / settings.EVAL_GOLDEN_DATASET
    items = load_golden_dataset(dataset_path)
    if limit is not None:
        items = items[:limit]

    print(f"Running evaluation over {len(items)} golden QA item(s)…")
    run = await container.get_evaluation_runner().run(items)

    report = {
        "run_id": run.run_id,
        "run_date": run.run_date.astimezone(timezone.utc).isoformat(),
        "total_items": run.total_items,
        "retrieval_recall": run.retrieval_recall,
        "context_precision": run.context_precision,
        "faithfulness": run.faithfulness,
        "hallucination_rate": run.hallucination_rate,
        # Per-question detail for the in-app Evaluation Dashboard.
        "items": [
            {
                "question": it.question,
                "category": it.category,
                "recall_hit": it.recall_hit,
                "context_precision": it.context_precision,
                "faithful": it.faithful,
                "hallucinated": it.hallucinated,
                "retrieved_count": it.retrieved_count,
            }
            for it in run.items
        ],
    }
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=2))

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"Baseline written to {output}")

    threshold = settings.EVAL_HALLUCINATION_THRESHOLD
    if run.hallucination_rate > threshold:
        print(
            f"FAIL: hallucination_rate {run.hallucination_rate} "
            f"exceeds threshold {threshold}"
        )
        return 1
    print(f"PASS: hallucination_rate {run.hallucination_rate} <= {threshold}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAG evaluation suite.")
    parser.add_argument(
        "--limit", type=int, default=None, help="evaluate only the first N items"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPO_ROOT / "docs" / "eval_baseline.json",
        help="where to write the baseline report",
    )
    args = parser.parse_args()
    try:
        code = asyncio.run(_main(args.limit, args.output))
    finally:
        container.close_all()
    sys.exit(code)


if __name__ == "__main__":
    main()
