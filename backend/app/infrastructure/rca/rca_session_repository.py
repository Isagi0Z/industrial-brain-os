"""PostgreSQL-backed RCA session repository (M12 — durable audit trail).

Table schema created by migration 006_rca_sessions_m12.py:
    session_id, asset_tag, incident_description, status, rca_report_json, created_at
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from app.domain.rca_brain.interfaces import IRCASessionRepository
from app.domain.rca_brain.models import RCAReport, RCASession, RCAStatus, WhyStep

logger = logging.getLogger(__name__)


class PostgresRCASessionRepository(IRCASessionRepository):
    def __init__(self, get_conn_fn: Callable) -> None:
        self._get_conn = get_conn_fn

    def create(self, session: RCASession) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rca_sessions
                    (session_id, asset_tag, incident_description, status, rca_report_json)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO NOTHING
                """,
                (
                    session.session_id,
                    session.asset_tag,
                    session.incident_description,
                    session.status.value,
                    session.report.model_dump_json() if session.report else None,
                ),
            )
        conn.commit()

    def update(self, session: RCASession) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rca_sessions
                SET status = %s, rca_report_json = %s
                WHERE session_id = %s
                """,
                (
                    session.status.value,
                    session.report.model_dump_json() if session.report else None,
                    session.session_id,
                ),
            )
        conn.commit()

    def get(self, session_id: str) -> Optional[RCASession]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id, asset_tag, incident_description, status,
                       rca_report_json, created_at
                FROM rca_sessions WHERE session_id = %s
                """,
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            return None

        report: Optional[RCAReport] = None
        if row[4]:
            raw = row[4] if isinstance(row[4], dict) else json.loads(row[4])
            report = RCAReport.model_validate(raw)

        # The Postgres row does not store the intermediate whys chain (that
        # lives in the Redis live-state store); a session reloaded purely from
        # Postgres therefore carries an empty whys list, which is correct for
        # audit/report retrieval.
        return RCASession(
            session_id=row[0],
            asset_tag=row[1],
            incident_description=row[2],
            status=RCAStatus(row[3]),
            whys=[] if report is None else _report_placeholder_whys(),
            report=report,
            created_at=row[5],
        )


def _report_placeholder_whys() -> list[WhyStep]:
    # Kept as a named helper so the intent (whys are not rehydrated from
    # Postgres) is explicit rather than a bare empty-list literal.
    return []
