"""PostgreSQL-backed work order repository (M10 — mock CMMS data).

Table schema created by migration 004_work_orders_m10.py:
    wo_id, asset_tag, description, status, priority,
    scheduled_date, completed_date
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from app.domain.maintenance_brain.interfaces import IWorkOrderRepository
from app.domain.maintenance_brain.models import WorkOrder

logger = logging.getLogger(__name__)

_OPEN_STATUSES = ("OPEN", "IN_PROGRESS")


class PostgresWorkOrderRepository(IWorkOrderRepository):
    def __init__(self, get_conn_fn: Callable) -> None:
        self._get_conn = get_conn_fn

    def find_by_wo_id(self, wo_id: str) -> Optional[WorkOrder]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT wo_id, asset_tag, description, status, priority,
                       scheduled_date, completed_date
                FROM work_orders WHERE wo_id = %s
                """,
                (wo_id,),
            )
            row = cur.fetchone()
        return _row_to_work_order(row) if row else None

    def find_by_asset_tag(self, asset_tag: str) -> List[WorkOrder]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT wo_id, asset_tag, description, status, priority,
                       scheduled_date, completed_date
                FROM work_orders WHERE asset_tag = %s
                ORDER BY scheduled_date ASC NULLS LAST
                """,
                (asset_tag,),
            )
            rows = cur.fetchall()
        return [_row_to_work_order(r) for r in rows]

    def find_open_by_asset_tag(self, asset_tag: str) -> List[WorkOrder]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT wo_id, asset_tag, description, status, priority,
                       scheduled_date, completed_date
                FROM work_orders
                WHERE asset_tag = %s AND status = ANY(%s)
                ORDER BY scheduled_date ASC NULLS LAST
                """,
                (asset_tag, list(_OPEN_STATUSES)),
            )
            rows = cur.fetchall()
        return [_row_to_work_order(r) for r in rows]


def _row_to_work_order(row) -> WorkOrder:
    return WorkOrder(
        wo_id=row[0],
        asset_tag=row[1],
        description=row[2],
        status=row[3],
        priority=row[4],
        scheduled_date=row[5],
        completed_date=row[6],
    )
