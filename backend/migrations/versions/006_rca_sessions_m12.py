"""M12: create rca_sessions table for Root Cause Analysis session audit trail.

Revision ID: 006
Revises: 005
Create Date: 2026-07-01
"""

from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rca_sessions (
            session_id           TEXT PRIMARY KEY,
            asset_tag            TEXT NOT NULL,
            incident_description TEXT NOT NULL,
            status               TEXT NOT NULL DEFAULT 'AWAITING_INPUT',
            rca_report_json      JSONB,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_rca_sessions_asset_tag
            ON rca_sessions (asset_tag);
        CREATE INDEX IF NOT EXISTS idx_rca_sessions_status
            ON rca_sessions (status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rca_sessions;")
