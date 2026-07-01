"""M11: create compliance_reports table for audit trail.

Revision ID: 005
Revises: 004
Create Date: 2026-07-01
"""

from alembic import op

revision: str = "005"
down_revision: str = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS compliance_reports (
            id                  TEXT PRIMARY KEY,
            session_id          TEXT NOT NULL,
            query               TEXT NOT NULL,
            report_json         JSONB NOT NULL,
            has_critical_gaps   BOOLEAN NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_compliance_reports_session
            ON compliance_reports (session_id);
        CREATE INDEX IF NOT EXISTS idx_compliance_reports_critical
            ON compliance_reports (has_critical_gaps);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS compliance_reports;")
