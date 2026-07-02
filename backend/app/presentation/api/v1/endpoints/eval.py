"""Evaluation Layer API (M16, architecture §5).

- GET  /api/v1/eval/report  → latest evaluation run's headline RAG metrics
- POST /api/v1/eval/run     → run the golden dataset now and return the result

The Prometheus gauges are exposed separately at the root `/metrics` endpoint
(mounted in main.py).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.application.evaluation.dataset import load_golden_dataset
from app.domain.auth.models import User
from app.domain.evaluation.models import EvaluationRun
from app.infrastructure.config.settings import settings
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/eval", tags=["Evaluation"])
logger = logging.getLogger(__name__)


class EvalReportResponse(BaseModel):
    run_id: str
    run_date: str
    retrieval_recall: float
    context_precision: float
    faithfulness: float
    hallucination_rate: float
    total_items: int


def _to_response(run: EvaluationRun) -> EvalReportResponse:
    return EvalReportResponse(
        run_id=run.run_id,
        run_date=run.run_date.isoformat(),
        retrieval_recall=run.retrieval_recall,
        context_precision=run.context_precision,
        faithfulness=run.faithfulness,
        hallucination_rate=run.hallucination_rate,
        total_items=run.total_items,
    )


def _resolve_dataset_path() -> Path:
    path = Path(settings.EVAL_GOLDEN_DATASET)
    if not path.is_absolute():
        # backend/app/... — parents[4] of this file is the repo root.
        path = Path(__file__).parents[5] / settings.EVAL_GOLDEN_DATASET
    return path


@router.get("/report", response_model=EvalReportResponse)
def get_report(current_user: User = Depends(get_current_user)) -> EvalReportResponse:
    run = container.get_evaluation_repository().get_latest()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No evaluation run found. Trigger one with POST /eval/run.",
        )
    return _to_response(run)


@router.post("/run", response_model=EvalReportResponse)
async def run_evaluation(
    current_user: User = Depends(get_current_user),
) -> EvalReportResponse:
    items = load_golden_dataset(_resolve_dataset_path())
    run = await container.get_evaluation_runner().run(items)
    return _to_response(run)
