"""Redis-backed ingestion worker (M3).

Runs as a daemon thread started during FastAPI lifespan.
Consumes the ``ingestion:jobs`` list via BLPOP and calls
DocumentParsingUseCase.parse_document for each payload.

Replaced by Celery in M15.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Callable

import redis

logger = logging.getLogger(__name__)

QUEUE_KEY = "ingestion:jobs"
BLPOP_TIMEOUT_SEC = 5


class IngestionWorker:
    def __init__(
        self,
        get_redis_fn: Callable[[], redis.Redis],
        get_parsing_use_case_fn,
    ):
        self._get_redis = get_redis_fn
        self._get_use_case = get_parsing_use_case_fn
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, name="ingestion-worker", daemon=True
        )
        self._thread.start()
        logger.info("IngestionWorker started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=BLPOP_TIMEOUT_SEC + 2)
        logger.info("IngestionWorker stopped.")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                client = self._get_redis()
                result = client.blpop(QUEUE_KEY, timeout=BLPOP_TIMEOUT_SEC)
                if result is None:
                    continue
                _, raw = result
                payload = json.loads(raw)
                document_id = payload["document_id"]
                job_id = payload["job_id"]
                logger.info(
                    "Worker picked up job %s for document %s.", job_id, document_id
                )
                use_case = self._get_use_case()
                use_case.parse_document(document_id, job_id)
            except Exception as exc:
                logger.error("Worker loop error: %s", exc, exc_info=True)
