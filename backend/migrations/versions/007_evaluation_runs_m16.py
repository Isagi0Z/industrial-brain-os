"""M16: create evaluation_runs table for the RAG Evaluation Layer.

Revision ID: 007
Revises: 006
Create Date: 2026-07-02
"""

from alembic import op

revision: str = "007"
down_revision: str = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id                 TEXT PRIMARY KEY,
            run_date           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            retrieval_recall   DOUBLE PRECISION NOT NULL,
            context_precision  DOUBLE PRECISION NOT NULL,
            faithfulness       DOUBLE PRECISION NOT NULL,
            hallucination_rate DOUBLE PRECISION NOT NULL,
            total_items        INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_evaluation_runs_run_date
            ON evaluation_runs (run_date DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evaluation_runs;")
