"""PostgreSQL-backed incident history repository (M12).

Reuses the `work_orders` table (created by M10's migration 004) as the
historical incident record, searching by description keywords to surface
prior similar failures as RCA evidence. Does not modify any M10 code.
"""

from __future__ import annotations

import logging
from typing import Callable, List

from app.domain.maintenance_brain.models import WorkOrder
from app.domain.rca_brain.interfaces import IIncidentHistoryRepository

logger = logging.getLogger(__name__)


class PostgresIncidentHistoryRepository(IIncidentHistoryRepository):
    def __init__(self, get_conn_fn: Callable) -> None:
        self._get_conn = get_conn_fn

    def search_by_keywords(self, keywords: List[str], limit: int) -> List[WorkOrder]:
        cleaned = [k.strip() for k in keywords if k and k.strip()]
        if not cleaned:
            return []

        # One ILIKE clause per keyword, OR-combined. Parameterized to avoid
        # any injection from free-text incident descriptions.
        clauses = " OR ".join(["description ILIKE %s"] * len(cleaned))
        params: List[object] = [f"%{k}%" for k in cleaned]
        params.append(limit)

        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT wo_id, asset_tag, description, status, priority,
                       scheduled_date, completed_date
                FROM work_orders
                WHERE {clauses}
                ORDER BY completed_date DESC NULLS LAST
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()

        return [
            WorkOrder(
                wo_id=r[0],
                asset_tag=r[1],
                description=r[2],
                status=r[3],
                priority=r[4],
                scheduled_date=r[5],
                completed_date=r[6],
            )
            for r in rows
        ]
