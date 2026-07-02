"""PostgreSQL-backed evaluation-run repository (M16).

Persists one row per evaluation run (migration 007_evaluation_runs_m16).
Per-item detail is not stored — the run row holds the four aggregate
headline metrics that the `/eval/report` endpoint and the CI gate consume.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from app.domain.evaluation.interfaces import IEvaluationRepository
from app.domain.evaluation.models import EvaluationRun

logger = logging.getLogger(__name__)


class PostgresEvaluationRepository(IEvaluationRepository):
    def __init__(self, get_conn_fn: Callable) -> None:
        self._get_conn = get_conn_fn

    def save(self, run: EvaluationRun) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_runs
                    (id, run_date, retrieval_recall, context_precision,
                     faithfulness, hallucination_rate, total_items)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run.run_id,
                    run.run_date,
                    run.retrieval_recall,
                    run.context_precision,
                    run.faithfulness,
                    run.hallucination_rate,
                    run.total_items,
                ),
            )
        conn.commit()
        logger.info(
            "Evaluation run persisted",
            extra={"run_id": run.run_id, "total_items": run.total_items},
        )

    def get_latest(self) -> Optional[EvaluationRun]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, run_date, retrieval_recall, context_precision,
                       faithfulness, hallucination_rate, total_items
                FROM evaluation_runs
                ORDER BY run_date DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        if row is None:
            return None
        run_date = row[1]
        if isinstance(run_date, datetime) and run_date.tzinfo is None:
            run_date = run_date.replace(tzinfo=timezone.utc)
        return EvaluationRun(
            run_id=row[0],
            run_date=run_date,
            retrieval_recall=row[2],
            context_precision=row[3],
            faithfulness=row[4],
            hallucination_rate=row[5],
            total_items=row[6],
        )
