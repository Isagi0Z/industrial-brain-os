import json
import logging

import redis

from app.domain.document.interfaces import IQueueService

logger = logging.getLogger(__name__)

INGESTION_QUEUE_KEY = "ingestion:jobs"


class RedisQueueService(IQueueService):
    """Pushes ingestion job payloads onto a Redis list for Celery workers (ADR-015)."""

    def __init__(self, get_redis_fn):
        self.get_redis_fn = get_redis_fn

    def enqueue_ingestion_job(self, document_id: str, job_id: str) -> None:
        """Append a job descriptor to the right end of the ingestion queue."""
        client: redis.Redis = self.get_redis_fn()
        payload = json.dumps({"document_id": document_id, "job_id": job_id})
        client.rpush(INGESTION_QUEUE_KEY, payload)
        logger.info(
            "Enqueued ingestion job %s for document %s onto '%s'",
            job_id,
            document_id,
            INGESTION_QUEUE_KEY,
        )
