"""EvaluationRunner (M16, architecture §5) — runs the golden dataset through
the real retrieval + generation pipeline and scores the four RAG metrics.

Reuses (no reimplementation):
  - GraphRAGEngine.retrieve (M8) for the retrieved chunks → Recall@k + the
    context judged for precision;
  - ChatUseCase (M14) for the generated answer *and* the Stage 8
    CitationValidationReport → hallucination signal;
  - an IEvaluationJudge (LLM-as-a-judge) for context precision + faithfulness.

Each item is scored independently and a failure in one item degrades that
item to a zero score rather than aborting the whole run.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import List

from app.application.chat.chat_use_case import ChatUseCase
from app.application.evaluation.metrics import (
    aggregate,
    context_precision,
    first_golden_hit_rank,
    mrr,
    ndcg_at_k,
)
from app.domain.chat.models import ChatRequest
from app.domain.evaluation.interfaces import (
    IEvaluationJudge,
    IEvaluationRepository,
    IMetricsRecorder,
)
from app.domain.evaluation.models import (
    EvaluationRun,
    GoldenQAItem,
    ItemEvaluation,
)
from app.domain.graphrag.interfaces import IGraphRAGEngine

logger = logging.getLogger(__name__)


class EvaluationRunner:
    def __init__(
        self,
        graphrag_engine: IGraphRAGEngine,
        chat_use_case: ChatUseCase,
        judge: IEvaluationJudge,
        repository: IEvaluationRepository,
        metrics_recorder: IMetricsRecorder,
        top_k: int = 10,
        role_scope: str = "public",
    ) -> None:
        self._graphrag = graphrag_engine
        self._chat = chat_use_case
        self._judge = judge
        self._repo = repository
        self._metrics = metrics_recorder
        self._top_k = top_k
        self._role_scope = role_scope

    async def run(self, golden_items: List[GoldenQAItem]) -> EvaluationRun:
        run_id = str(uuid.uuid4())
        t0 = time.monotonic()
        item_evals: List[ItemEvaluation] = []

        for item in golden_items:
            item_evals.append(await self._evaluate_item(run_id, item))

        recall, precision, faithfulness, hallucination_rate = aggregate(item_evals)
        ranks = [i.first_hit_rank for i in item_evals]
        run = EvaluationRun(
            run_id=run_id,
            retrieval_recall=recall,
            context_precision=precision,
            faithfulness=faithfulness,
            hallucination_rate=hallucination_rate,
            total_items=len(item_evals),
            items=item_evals,
            mrr=mrr(ranks),
            ndcg=ndcg_at_k(ranks),
        )

        try:
            self._repo.save(run)
        except Exception as exc:
            logger.error("Evaluation run persistence failed: %s", exc)
        try:
            self._metrics.record(run)
        except Exception as exc:
            logger.warning("Evaluation metrics publish failed: %s", exc)

        logger.info(
            "Evaluation run complete",
            extra={
                "run_id": run_id,
                "total_items": run.total_items,
                "retrieval_recall": recall,
                "context_precision": precision,
                "faithfulness": faithfulness,
                "hallucination_rate": hallucination_rate,
                "duration_ms": round((time.monotonic() - t0) * 1000, 1),
            },
        )
        return run

    async def _evaluate_item(self, run_id: str, item: GoldenQAItem) -> ItemEvaluation:
        try:
            hybrid = await self._graphrag.retrieve(
                item.question, self._role_scope, self._top_k
            )
            retrieved = [rc.result for rc in hybrid.ranked_chunks]

            hit_rank = first_golden_hit_rank(
                item.source_document_id,
                item.source_page,
                retrieved,
                item.alternate_sources,
            )
            recall_hit = hit_rank is not None

            relevance_flags = [
                await self._judge.judge_relevance(r.text, item.expected_answer)
                for r in retrieved
            ]
            precision = context_precision(relevance_flags)

            # Generate the answer through the M14 pipeline so the Stage 8
            # hallucination signal comes for free.
            request = ChatRequest(
                query=item.question,
                session_id=f"eval:{run_id}",
                top_k=self._top_k,
                role_scope=self._role_scope,
            )
            ctx = await self._chat.prepare(request)
            response = await self._chat.chat(ctx)
            hallucinated = bool(
                response.citation_validation
                and response.citation_validation.hallucinated_count > 0
            )

            context_text = "\n\n".join(r.text for r in retrieved)
            faithful = await self._judge.judge_faithfulness(
                response.answer, context_text
            )

            return ItemEvaluation(
                question=item.question,
                category=item.category,
                recall_hit=recall_hit,
                context_precision=precision,
                faithful=faithful,
                hallucinated=hallucinated,
                retrieved_count=len(retrieved),
                first_hit_rank=hit_rank,
            )
        except Exception as exc:
            logger.error(
                "Evaluation item failed — scoring zero: %s",
                exc,
                extra={"question": item.question},
            )
            return ItemEvaluation(
                question=item.question,
                category=item.category,
                recall_hit=False,
                context_precision=0.0,
                faithful=False,
                hallucinated=False,
                retrieved_count=0,
            )
