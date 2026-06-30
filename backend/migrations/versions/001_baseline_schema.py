"""Baseline schema: M1 full table set

Revision ID: 001
Revises:
Create Date: 2026-06-30

All CREATE TABLE statements use IF NOT EXISTS so this migration is safe to
run against a database that was already bootstrapped by the _ensure_tables()
calls in the repository layer during earlier development.
"""

from alembic import op

revision: str = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Core identity tables
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id           VARCHAR(50)  PRIMARY KEY,
            email        VARCHAR(255) UNIQUE NOT NULL,
            hashed_password TEXT      NOT NULL,
            full_name    VARCHAR(255),
            is_active    BOOLEAN      DEFAULT TRUE
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            id          VARCHAR(50)  PRIMARY KEY,
            name        VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            permissions JSONB        NOT NULL DEFAULT '[]',
            created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )

    # ------------------------------------------------------------------
    # Document pipeline tables
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id                VARCHAR(50)  PRIMARY KEY,
            original_filename VARCHAR(255) NOT NULL,
            mime_type         VARCHAR(100) NOT NULL,
            size_bytes        BIGINT       NOT NULL,
            sha256_hash       VARCHAR(64)  NOT NULL,
            status            VARCHAR(50)  NOT NULL,
            created_at        TIMESTAMP    NOT NULL,
            updated_at        TIMESTAMP    NOT NULL,
            created_by        VARCHAR(50)  NOT NULL,
            is_deleted        BOOLEAN      DEFAULT FALSE
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_versions (
            id             VARCHAR(50)  PRIMARY KEY,
            document_id    VARCHAR(50)  REFERENCES documents(id) ON DELETE CASCADE,
            version_number INT          NOT NULL,
            storage_path   VARCHAR(500) NOT NULL,
            size_bytes     BIGINT       NOT NULL,
            created_at     TIMESTAMP    NOT NULL,
            created_by     VARCHAR(50)  NOT NULL
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_metadata (
            id          VARCHAR(50) PRIMARY KEY,
            document_id VARCHAR(50) REFERENCES documents(id) ON DELETE CASCADE UNIQUE,
            metadata    JSONB       NOT NULL,
            created_at  TIMESTAMP   NOT NULL,
            updated_at  TIMESTAMP   NOT NULL
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_classifications (
            id          VARCHAR(50)  PRIMARY KEY,
            document_id VARCHAR(50)  REFERENCES documents(id) ON DELETE CASCADE,
            category    VARCHAR(100) NOT NULL,
            confidence  FLOAT        NOT NULL,
            created_at  TIMESTAMP    NOT NULL
        );
    """
    )

    # document_chunks — populated by the embedding pipeline (M4)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            id                    VARCHAR(50) PRIMARY KEY,
            document_id           VARCHAR(50) REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index           INTEGER     NOT NULL,
            chunk_type            VARCHAR(50) NOT NULL,
            text                  TEXT        NOT NULL,
            page_number           INTEGER,
            parent_section_header TEXT,
            bbox_json             JSONB,
            token_count           INTEGER,
            created_at            TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )

    # ------------------------------------------------------------------
    # Operations / observability tables
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id             VARCHAR(50) PRIMARY KEY,
            document_id    VARCHAR(50) REFERENCES documents(id) ON DELETE SET NULL,
            status         VARCHAR(50) NOT NULL DEFAULT 'PENDING',
            error_details  JSONB,
            created_at     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id            VARCHAR(50)  PRIMARY KEY,
            user_id       VARCHAR(50),
            action        VARCHAR(100) NOT NULL,
            resource_type VARCHAR(100),
            resource_id   VARCHAR(50),
            ip_address    VARCHAR(45),
            correlation_id VARCHAR(50),
            metadata      JSONB,
            created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )

    # ------------------------------------------------------------------
    # Indexes — all use IF NOT EXISTS (Postgres 9.5+)
    # ------------------------------------------------------------------
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_status      ON documents(status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_created_by  ON documents(created_by);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_document_id    ON document_chunks(document_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_document_id      ON jobs(document_id);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status           ON jobs(status);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_user_id         ON audit_logs(user_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_created_at      ON audit_logs(created_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_correlation_id  ON audit_logs(correlation_id);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs          CASCADE;")
    op.execute("DROP TABLE IF EXISTS jobs                CASCADE;")
    op.execute("DROP TABLE IF EXISTS document_chunks     CASCADE;")
    op.execute("DROP TABLE IF EXISTS document_classifications CASCADE;")
    op.execute("DROP TABLE IF EXISTS document_metadata   CASCADE;")
    op.execute("DROP TABLE IF EXISTS document_versions   CASCADE;")
    op.execute("DROP TABLE IF EXISTS documents           CASCADE;")
    op.execute("DROP TABLE IF EXISTS roles               CASCADE;")
    op.execute("DROP TABLE IF EXISTS users               CASCADE;")
