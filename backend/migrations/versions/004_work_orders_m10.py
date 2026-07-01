"""M10: create work_orders table for mock CMMS data.

Revision ID: 004
Revises: 003
Create Date: 2026-07-01
"""

from alembic import op

revision: str = "004"
down_revision: str = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS work_orders (
            wo_id           TEXT PRIMARY KEY,
            asset_tag       TEXT NOT NULL,
            description     TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'OPEN',
            priority        TEXT NOT NULL DEFAULT 'MEDIUM',
            scheduled_date  DATE,
            completed_date  DATE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_work_orders_asset_tag
            ON work_orders (asset_tag);
        CREATE INDEX IF NOT EXISTS idx_work_orders_status
            ON work_orders (status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS work_orders;")
