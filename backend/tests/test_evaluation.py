"""Unit tests for M16 — RAG Evaluation Layer.

Metric functions are pure and tested with known inputs. The runner, judge,
and repository are exercised with mocks — no live services or LLM calls.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.domain.document.constants import ChunkType
from app.domain.evaluation.models import GoldenQAItem, ItemEvaluation
from app.domain.search.models import SearchResult


def _result(document_id="doc-1", page=3, text="chunk"):
    return SearchResult(
        chunk_id=str(uuid.uuid4()),
        document_id=document_id,
        document_title="Doc",
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=page,
        parent_section_header=None,
        bbox_json=None,
        score=0.9,
        role_scope="public",
    )


# ---------------------------------------------------------------------------
# Metric functions (pure)
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_recall_hit_document_and_page(self):
        from app.application.evaluation.metrics import retrieval_recall_hit

        retrieved = [_result("doc-9", 1), _result("doc-1", 3)]
        assert retrieval_recall_hit("doc-1", 3, retrieved) is True

    def test_recall_miss_wrong_page(self):
        from app.application.evaluation.metrics import retrieval_recall_hit

        retrieved = [_result("doc-1", 5)]
        assert retrieval_recall_hit("doc-1", 3, retrieved) is False

    def test_recall_page_none_matches_any_page(self):
        from app.application.evaluation.metrics import retrieval_recall_hit

        retrieved = [_result("doc-1", 99)]
        assert retrieval_recall_hit("doc-1", None, retrieved) is True

    def test_recall_empty_is_false(self):
        from app.application.evaluation.metrics import retrieval_recall_hit

        assert retrieval_recall_hit("doc-1", 3, []) is False

    def test_context_precision_fraction(self):
        from app.application.evaluation.metrics import context_precision

        assert context_precision([True, True, False, False]) == 0.5
        assert context_precision([True, True]) == 1.0

    def test_context_precision_empty_is_zero(self):
        from app.application.evaluation.metrics import context_precision

        assert context_precision([]) == 0.0

    def test_aggregate(self):
        from app.application.evaluation.metrics import aggregate

        items = [
            ItemEvaluation("q1", "c", True, 1.0, True, False, 3),
            ItemEvaluation("q2", "c", False, 0.5, True, True, 2),
            ItemEvaluation("q3", "c", True, 0.0, False, False, 0),
            ItemEvaluation("q4", "c", False, 0.5, True, False, 2),
        ]
        recall, precision, faithfulness, halluc = aggregate(items)
        assert recall == 0.5  # 2/4
        assert precision == 0.5  # (1.0+0.5+0.0+0.5)/4
        assert faithfulness == 0.75  # 3/4
        assert halluc == 0.25  # 1/4

    def test_aggregate_empty(self):
        from app.application.evaluation.metrics import aggregate

        assert aggregate([]) == (0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# LLM judge — response parsing
# ---------------------------------------------------------------------------


class TestJudgeParsing:
    def test_parse_yes_variants(self):
        from app.infrastructure.evaluation.llm_judge import _parse_yes

        assert _parse_yes("YES") is True
        assert _parse_yes("yes, it is grounded") is True
        assert _parse_yes("**YES**") is True
        assert _parse_yes("No, unsupported") is False
        assert _parse_yes("The answer is not faithful") is False
        assert _parse_yes("") is False

    def test_judge_degrades_to_false_on_error(self):
        from app.infrastructure.evaluation.llm_judge import LLMJudge

        gateway = MagicMock()
        gateway.generate = AsyncMock(side_effect=RuntimeError("llm down"))
        judge = LLMJudge.__new__(LLMJudge)
        judge._gateway = gateway
        judge._faith_prompt = {"system": "s", "user_template": "{answer}{context}"}
        judge._rel_prompt = {
            "system": "s",
            "user_template": "{chunk_text}{expected_answer}",
        }
        judge._max_tokens = 32

        assert asyncio.run(judge.judge_faithfulness("a", "c")) is False
        assert asyncio.run(judge.judge_relevance("chunk", "expected")) is False


# ---------------------------------------------------------------------------
# EvaluationRunner (mocked graphrag / chat / judge / repo / metrics)
# ---------------------------------------------------------------------------


class TestEvaluationRunner:
    def _runner(self, retrieved, hallucinated, faithful, relevant):
        from app.application.evaluation.evaluation_runner import EvaluationRunner
        from app.domain.graphrag.models import HybridSearchResult, RankedChunk

        graphrag = MagicMock()

        async def _retrieve(q, role, k):
            return HybridSearchResult(
                ranked_chunks=[
                    RankedChunk(result=r, rerank_score=0.9) for r in retrieved
                ]
            )

        graphrag.retrieve = _retrieve

        chat = MagicMock()

        async def _prepare(req):
            return MagicMock()

        report = MagicMock()
        report.hallucinated_count = 1 if hallucinated else 0
        response = MagicMock()
        response.answer = "answer"
        response.citation_validation = report

        async def _chat(ctx):
            return response

        chat.prepare = _prepare
        chat.chat = _chat

        judge = MagicMock()
        judge.judge_relevance = AsyncMock(return_value=relevant)
        judge.judge_faithfulness = AsyncMock(return_value=faithful)

        repo = MagicMock()
        metrics = MagicMock()

        return (
            EvaluationRunner(graphrag, chat, judge, repo, metrics, top_k=10),
            repo,
            metrics,
        )

    def test_run_scores_and_persists(self):
        item = GoldenQAItem(
            question="What is P-102A pressure?",
            expected_answer="12 bar",
            source_document_id="doc-1",
            source_page=3,
            category="equipment_lookup",
        )
        runner, repo, metrics = self._runner(
            retrieved=[_result("doc-1", 3)],
            hallucinated=False,
            faithful=True,
            relevant=True,
        )
        run = asyncio.run(runner.run([item]))

        assert run.total_items == 1
        assert run.retrieval_recall == 1.0  # doc-1 p.3 was retrieved
        assert run.context_precision == 1.0  # the one chunk judged relevant
        assert run.faithfulness == 1.0
        assert run.hallucination_rate == 0.0
        repo.save.assert_called_once_with(run)
        metrics.record.assert_called_once_with(run)

    def test_run_flags_hallucination_and_recall_miss(self):
        item = GoldenQAItem(
            question="q",
            expected_answer="a",
            source_document_id="doc-1",
            source_page=3,
            category="general",
        )
        runner, _, _ = self._runner(
            retrieved=[_result("doc-OTHER", 1)],
            hallucinated=True,
            faithful=False,
            relevant=False,
        )
        run = asyncio.run(runner.run([item]))
        assert run.retrieval_recall == 0.0  # golden source not retrieved
        assert run.hallucination_rate == 1.0
        assert run.context_precision == 0.0  # the chunk judged irrelevant

    def test_item_failure_scores_zero(self):
        from app.application.evaluation.evaluation_runner import EvaluationRunner

        graphrag = MagicMock()

        async def _boom(q, role, k):
            raise RuntimeError("retrieval down")

        graphrag.retrieve = _boom
        runner = EvaluationRunner(
            graphrag, MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        item = GoldenQAItem("q", "a", "doc-1", 3)
        run = asyncio.run(runner.run([item]))
        assert run.total_items == 1
        assert run.retrieval_recall == 0.0
        assert run.faithfulness == 0.0
