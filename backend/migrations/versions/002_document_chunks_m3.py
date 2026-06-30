"""M3: add table_data_json and figure_storage_key to document_chunks

Revision ID: 002
Revises: 001
Create Date: 2026-06-30
"""

from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE document_chunks
            ADD COLUMN IF NOT EXISTS table_data_json  JSONB,
            ADD COLUMN IF NOT EXISTS figure_storage_key TEXT;
    """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE document_chunks
            DROP COLUMN IF EXISTS table_data_json,
            DROP COLUMN IF EXISTS figure_storage_key;
    """
    )
