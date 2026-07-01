"""Redis-backed ingestion worker (M3+M4+M7).

Runs as a daemon thread started during FastAPI lifespan.
Consumes the ``ingestion:jobs`` list via BLPOP and calls:
  1. DocumentParsingUseCase.parse_document  (QUEUED → CHUNKED)
  2. EmbeddingUseCase.embed_document        (CHUNKED → INDEXED)
  3. ExtractionUseCase.run_for_document     (INDEXED → KG_POPULATED → COMPLETED)

Per-chunk failures in step 3 are isolated inside ExtractionUseCase — the
worker only sees a completed (possibly partial) extraction, never a crash
from a single bad chunk.

Replaced by Celery in M15.
"""

from __future__ import annotations

import asyncio
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
        get_parsing_use_case_fn: Callable,
        get_embedding_use_case_fn: Callable,
        get_extraction_use_case_fn: Callable,
    ) -> None:
        self._get_redis = get_redis_fn
        self._get_parsing_uc = get_parsing_use_case_fn
        self._get_embedding_uc = get_embedding_use_case_fn
        self._get_extraction_uc = get_extraction_use_case_fn
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
                chunks = self._get_parsing_uc().parse_document(document_id, job_id)
                if chunks:
                    self._get_embedding_uc().embed_document(document_id, job_id)
                    asyncio.run(
                        self._get_extraction_uc().run_for_document(
                            document_id, job_id
                        )
                    )
            except Exception as exc:
                logger.error("Worker loop error: %s", exc, exc_info=True)
