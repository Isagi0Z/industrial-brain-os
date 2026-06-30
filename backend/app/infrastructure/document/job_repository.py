import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict


from app.domain.document.interfaces import IJobRepository
from app.domain.document.models import ProcessingJob
from app.domain.document.constants import JobStatus

logger = logging.getLogger(__name__)


class PostgresJobRepository(IJobRepository):
    """PostgreSQL implementation of IJobRepository using the `jobs` table."""

    def __init__(self, get_connection_fn):
        self.get_connection_fn = get_connection_fn

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_job(row: tuple) -> ProcessingJob:
        """Map a DB row to a ProcessingJob domain object.

        Row order: id, document_id, status, error_details (JSONB), created_at, updated_at
        """
        error_details = row[3]
        error_message: Optional[str] = None
        if error_details:
            if isinstance(error_details, dict):
                error_message = error_details.get("message")
            elif isinstance(error_details, str):
                try:
                    error_message = json.loads(error_details).get("message")
                except (json.JSONDecodeError, AttributeError):
                    error_message = error_details

        created_at = row[4]
        updated_at = row[5]
        # Ensure timezone-aware datetimes for consistency
        if isinstance(created_at, datetime) and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        return ProcessingJob(
            id=row[0],
            document_id=row[1],
            status=JobStatus(row[2]),
            error_message=error_message,
            created_at=created_at,
            updated_at=updated_at,
        )

    # ------------------------------------------------------------------
    # IJobRepository implementation
    # ------------------------------------------------------------------

    def create(self, job: ProcessingJob) -> ProcessingJob:
        conn = self.get_connection_fn()
        error_details = (
            json.dumps({"message": job.error_message}) if job.error_message else None
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (id, document_id, status, error_details, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    job.id,
                    job.document_id,
                    job.status.value,
                    error_details,
                    job.created_at,
                    job.updated_at,
                ),
            )
            conn.commit()
        logger.info(
            "Created job %s (status=%s) for document %s",
            job.id,
            job.status.value,
            job.document_id,
        )
        return job

    def get_by_document_id(self, document_id: str) -> Optional[ProcessingJob]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, document_id, status, error_details, created_at, updated_at
                FROM jobs
                WHERE document_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            )
            row = cur.fetchone()
        return self._row_to_job(row) if row else None

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> None:
        conn = self.get_connection_fn()
        error_details = (
            json.dumps({"message": error_message}) if error_message else None
        )
        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET status = %s, error_details = %s, updated_at = %s
                WHERE id = %s
                """,
                (status.value, error_details, now, job_id),
            )
            conn.commit()
        logger.info("Job %s transitioned to %s", job_id, status.value)

    def get_latest_statuses(self, document_ids: List[str]) -> Dict[str, JobStatus]:
        """Batch-fetch the most recent job status for each document."""
        if not document_ids:
            return {}
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (document_id) document_id, status
                FROM jobs
                WHERE document_id = ANY(%s)
                ORDER BY document_id, created_at DESC
                """,
                (document_ids,),
            )
            rows = cur.fetchall()
        return {row[0]: JobStatus(row[1]) for row in rows}
