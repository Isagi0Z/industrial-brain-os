"""Unit tests for M15 — event-driven ingestion (Celery + Redis).

No broker is required: the Celery chain is exercised in eager mode, and the
retry/backoff + failure logic is tested through the `_handle_failure` helper
with a fake task object. All use cases and repositories are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.document.constants import JobStatus


# ---------------------------------------------------------------------------
# CeleryQueueService — dispatch + correlation propagation
# ---------------------------------------------------------------------------


class TestCeleryQueueService:
    def test_dispatches_chain_with_correlation_id(self):
        from app.infrastructure.document import celery_queue_service as mod
        from app.infrastructure.logging.logger import correlation_id_ctx

        token = correlation_id_ctx.set("corr-123")
        try:
            with patch.object(mod, "chain") as mock_chain, patch.object(
                mod, "parse_task"
            ) as mock_parse, patch.object(mod, "embed_task"), patch.object(
                mod, "kg_task"
            ):
                mock_chain.return_value.apply_async.return_value = None
                svc = mod.CeleryQueueService()
                svc.enqueue_ingestion_job("doc-1", "job-1")

                # parse_task.s received the payload with the correlation id
                payload = mock_parse.s.call_args.args[0]
                assert payload["document_id"] == "doc-1"
                assert payload["job_id"] == "job-1"
                assert payload["correlation_id"] == "corr-123"
                mock_chain.return_value.apply_async.assert_called_once()
        finally:
            correlation_id_ctx.reset(token)

    def test_implements_queue_service_interface(self):
        from app.domain.document.interfaces import IQueueService
        from app.infrastructure.document.celery_queue_service import CeleryQueueService

        assert issubclass(CeleryQueueService, IQueueService)


# ---------------------------------------------------------------------------
# Correlation-ID restore inside tasks
# ---------------------------------------------------------------------------


def test_restore_correlation_sets_contextvar():
    from app.infrastructure.celery.tasks import _restore_correlation
    from app.infrastructure.logging.logger import correlation_id_ctx

    _restore_correlation({"correlation_id": "abc-789"})
    assert correlation_id_ctx.get() == "abc-789"


def test_restore_correlation_defaults_to_dash():
    from app.infrastructure.celery.tasks import _restore_correlation
    from app.infrastructure.logging.logger import correlation_id_ctx

    _restore_correlation({})
    assert correlation_id_ctx.get() == "-"


# ---------------------------------------------------------------------------
# Retry / backoff / FAILED-on-exhaustion logic
# ---------------------------------------------------------------------------


def _fake_task(retries: int):
    task = MagicMock()
    task.request.retries = retries

    class _Retry(Exception):
        pass

    def _retry(exc, countdown, max_retries):
        raise _Retry(f"retry:{countdown}")

    task.retry.side_effect = _retry
    return task, _Retry


class TestRetryBackoff:
    @pytest.mark.parametrize(
        "retries,expected_countdown", [(0, 60), (1, 120), (2, 240)]
    )
    def test_exponential_backoff(self, retries, expected_countdown):
        from app.infrastructure.celery import tasks

        task, RetryExc = _fake_task(retries)
        with pytest.raises(RetryExc):
            tasks._handle_failure(task, "parse_task", "job-1", RuntimeError("boom"))
        _, kwargs = task.retry.call_args
        assert kwargs["countdown"] == expected_countdown

    def test_exhausted_retries_marks_job_failed(self):
        from app.infrastructure.celery import tasks

        task, _ = _fake_task(retries=3)  # == _MAX_RETRIES

        job_repo = MagicMock()
        fake_container = MagicMock()
        fake_container.get_job_repository.return_value = job_repo

        with patch.object(tasks, "container", fake_container):
            with pytest.raises(RuntimeError):
                tasks._handle_failure(
                    task, "embed_task", "job-9", RuntimeError("kaboom")
                )

        job_repo.update_status.assert_called_once()
        args, kwargs = job_repo.update_status.call_args
        assert args[0] == "job-9"
        assert args[1] == JobStatus.FAILED
        # error_details carries the task name + exception message
        err = kwargs.get("error_message") or (args[2] if len(args) > 2 else "")
        assert "embed_task" in err and "kaboom" in err


# ---------------------------------------------------------------------------
# Task success — status transitions + payload threading (eager mode)
# ---------------------------------------------------------------------------


class TestTaskExecution:
    def test_chain_runs_all_stages_and_transitions_status(self):
        from app.infrastructure.celery import tasks
        from app.infrastructure.celery.celery_app import celery_app

        job_repo = MagicMock()
        parsing_uc = MagicMock()
        parsing_uc.parse_document.return_value = ["chunk1", "chunk2"]
        embedding_uc = MagicMock()
        extraction_uc = MagicMock()

        async def _run_for_document(document_id, job_id):
            return None

        extraction_uc.run_for_document = _run_for_document

        fake_container = MagicMock()
        fake_container.get_job_repository.return_value = job_repo
        fake_container.get_parsing_use_case.return_value = parsing_uc
        fake_container.get_embedding_use_case.return_value = embedding_uc
        fake_container.get_extraction_use_case.return_value = extraction_uc

        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        try:
            with patch.object(tasks, "container", fake_container):
                payload = {
                    "document_id": "doc-1",
                    "job_id": "job-1",
                    "correlation_id": "c",
                }
                # run the three tasks in sequence (threading the payload)
                p1 = tasks.parse_task.apply(args=[payload]).get()
                p2 = tasks.embed_task.apply(args=[p1]).get()
                tasks.kg_task.apply(args=[p2]).get()
        finally:
            celery_app.conf.task_always_eager = False
            celery_app.conf.task_eager_propagates = False

        parsing_uc.parse_document.assert_called_once_with("doc-1", "job-1")
        embedding_uc.embed_document.assert_called_once_with("doc-1", "job-1")

        transitions = [c.args[1] for c in job_repo.update_status.call_args_list]
        assert JobStatus.EXTRACTING in transitions
        assert JobStatus.EMBEDDING in transitions
        assert JobStatus.KG_EXTRACTING in transitions

    def test_embed_skipped_when_no_chunks(self):
        from app.infrastructure.celery import tasks
        from app.infrastructure.celery.celery_app import celery_app

        job_repo = MagicMock()
        embedding_uc = MagicMock()
        fake_container = MagicMock()
        fake_container.get_job_repository.return_value = job_repo
        fake_container.get_embedding_use_case.return_value = embedding_uc

        celery_app.conf.task_always_eager = True
        try:
            with patch.object(tasks, "container", fake_container):
                out = tasks.embed_task.apply(
                    args=[{"document_id": "d", "job_id": "j", "chunk_count": 0}]
                ).get()
        finally:
            celery_app.conf.task_always_eager = False

        embedding_uc.embed_document.assert_not_called()
        assert out["job_id"] == "j"


# ---------------------------------------------------------------------------
# Job lookup use case (GET /api/v1/jobs/{job_id})
# ---------------------------------------------------------------------------


class TestJobLookup:
    def _use_case(self, job):
        from app.application.document.services import DocumentUseCase

        job_repo = MagicMock()
        job_repo.get_by_id.return_value = job
        return (
            DocumentUseCase(MagicMock(), MagicMock(), job_repo, MagicMock()),
            job_repo,
        )

    def test_get_job_by_id_returns_job(self):
        job = MagicMock()
        uc, job_repo = self._use_case(job)
        assert uc.get_job_by_id("job-1") is job
        job_repo.get_by_id.assert_called_once_with("job-1")

    def test_get_job_by_id_not_found_raises(self):
        from app.presentation.middleware.error_handler import DomainException

        uc, _ = self._use_case(None)
        with pytest.raises(DomainException):
            uc.get_job_by_id("missing")
