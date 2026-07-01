#!/usr/bin/env python3
"""Load mock CMMS work order data into PostgreSQL (M10 — Maintenance Brain).

Usage (from repo root):
    python scripts/load_mock_cmms.py [path/to/csv]

Defaults to scripts/mock_cmms_data.csv. Idempotent — re-running upserts by
wo_id rather than duplicating rows. Requires PostgreSQL to be running and
migration 004_work_orders_m10 to have been applied (alembic upgrade head).

Exits 0 on success, 1 on any failure.
"""

from __future__ import annotations

import csv
import sys
import os
from datetime import date
from typing import Optional

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.infrastructure.logging.logger import setup_logging  # noqa: E402
from app.infrastructure.di.container import DIContainer  # noqa: E402

setup_logging()

_DEFAULT_CSV = os.path.join(os.path.dirname(__file__), "mock_cmms_data.csv")


def _parse_date(value: str) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def main() -> int:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_CSV

    print("Industrial Brain OS — Mock CMMS Loader")
    print("=" * 45)
    print(f"Source CSV: {csv_path}")

    if not os.path.isfile(csv_path):
        print(f"FAILED CSV file not found: {csv_path}")
        return 1

    container = DIContainer()
    try:
        conn = container.get_postgres()
    except Exception as exc:
        print(f"FAILED Could not connect to PostgreSQL: {exc}")
        return 1

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(
                (
                    row["wo_id"],
                    row["asset_tag"],
                    row["description"],
                    row["status"],
                    row["priority"],
                    _parse_date(row.get("scheduled_date", "")),
                    _parse_date(row.get("completed_date", "")),
                )
            )

    if not rows:
        print("No rows found in CSV — nothing to load.")
        return 0

    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO work_orders
                    (wo_id, asset_tag, description, status, priority,
                     scheduled_date, completed_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (wo_id) DO UPDATE SET
                    asset_tag = EXCLUDED.asset_tag,
                    description = EXCLUDED.description,
                    status = EXCLUDED.status,
                    priority = EXCLUDED.priority,
                    scheduled_date = EXCLUDED.scheduled_date,
                    completed_date = EXCLUDED.completed_date
                """,
                rows,
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"FAILED Load failed: {exc}")
        return 1

    print(f"OK Loaded {len(rows)} work orders into 'work_orders'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
