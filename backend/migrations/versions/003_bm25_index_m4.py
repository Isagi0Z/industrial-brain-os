"""M4: create bm25_index table for keyword search.

Revision ID: 003
Revises: 002
Create Date: 2026-06-30
"""

from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bm25_index (
            id          TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_id    TEXT NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            chunk_type  TEXT NOT NULL DEFAULT 'paragraph',
            term        TEXT NOT NULL,
            tf          FLOAT NOT NULL,
            role_scope  TEXT NOT NULL DEFAULT 'public',
            document_title TEXT NOT NULL DEFAULT '',
            page_number INTEGER,
            parent_section_header TEXT,
            bbox_json   JSONB,
            chunk_text  TEXT NOT NULL DEFAULT '',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_bm25_term_scope
            ON bm25_index (term, role_scope);
        CREATE INDEX IF NOT EXISTS idx_bm25_document
            ON bm25_index (document_id);
        CREATE INDEX IF NOT EXISTS idx_bm25_chunk
            ON bm25_index (chunk_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bm25_index;")
