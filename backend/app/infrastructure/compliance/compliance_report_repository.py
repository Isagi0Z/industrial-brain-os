"""PostgreSQL-backed compliance report repository (M11 — audit trail).

Table schema created by migration 005_compliance_reports_m11.py:
    id, session_id, query, report_json, has_critical_gaps, created_at
"""

from __future__ import annotations

import logging
import uuid
from typing import Callable

from app.domain.compliance_brain.interfaces import IComplianceReportRepository
from app.domain.compliance_brain.models import ComplianceGapReport

logger = logging.getLogger(__name__)


class PostgresComplianceReportRepository(IComplianceReportRepository):
    def __init__(self, get_conn_fn: Callable) -> None:
        self._get_conn = get_conn_fn

    def save(self, session_id: str, query: str, report: ComplianceGapReport) -> str:
        report_id = str(uuid.uuid4())
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO compliance_reports
                    (id, session_id, query, report_json, has_critical_gaps)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    report_id,
                    session_id,
                    query,
                    report.model_dump_json(),
                    report.has_critical_gaps,
                ),
            )
        conn.commit()
        logger.info(
            "Compliance report saved",
            extra={
                "report_id": report_id,
                "session_id": session_id,
                "gap_count": len(report.gaps),
                "has_critical_gaps": report.has_critical_gaps,
            },
        )
        return report_id
