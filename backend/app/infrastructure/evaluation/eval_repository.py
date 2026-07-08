"""PostgreSQL-backed evaluation-run repository (M16).

Persists one row per evaluation run (migration 007_evaluation_runs_m16).
Per-item detail is not stored — the run row holds the four aggregate
headline metrics that the `/eval/report` endpoint and the CI gate consume.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from app.domain.evaluation.interfaces import IEvaluationRepository
from app.domain.evaluation.models import EvaluationRun


def _as_utc(run_date: datetime) -> datetime:
    if isinstance(run_date, datetime) and run_date.tzinfo is None:
        return run_date.replace(tzinfo=timezone.utc)
    return run_date

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
        return EvaluationRun(
            run_id=row[0],
            run_date=_as_utc(row[1]),
            retrieval_recall=row[2],
            context_precision=row[3],
            faithfulness=row[4],
            hallucination_rate=row[5],
            total_items=row[6],
        )

    def list_runs(self, limit: int = 20) -> List[EvaluationRun]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, run_date, retrieval_recall, context_precision,
                       faithfulness, hallucination_rate, total_items
                FROM evaluation_runs
                ORDER BY run_date DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            EvaluationRun(
                run_id=r[0],
                run_date=_as_utc(r[1]),
                retrieval_recall=r[2],
                context_precision=r[3],
                faithfulness=r[4],
                hallucination_rate=r[5],
                total_items=r[6],
            )
            for r in rows
        ]
