import logging
import json
from typing import Optional, List, Tuple, Any
import psycopg2
from app.domain.document.interfaces import IDocumentRepository
from app.domain.document.models import Document, DocumentVersion, DocumentMetadata, DocumentClassification
from app.domain.document.constants import DocumentStatus

logger = logging.getLogger(__name__)


class PostgresDocumentRepository(IDocumentRepository):
    def __init__(self, get_connection_fn):
        self.get_connection_fn = get_connection_fn
        self._ensure_tables()

    def _ensure_tables(self):
        conn = self.get_connection_fn()
        try:
            with conn.cursor() as cur:
                # Documents Table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id VARCHAR(50) PRIMARY KEY,
                    original_filename VARCHAR(255) NOT NULL,
                    mime_type VARCHAR(100) NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    sha256_hash VARCHAR(64) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    created_by VARCHAR(50) NOT NULL,
                    is_deleted BOOLEAN DEFAULT FALSE
                );
                """)
                # Document Versions Table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS document_versions (
                    id VARCHAR(50) PRIMARY KEY,
                    document_id VARCHAR(50) REFERENCES documents(id) ON DELETE CASCADE,
                    version_number INT NOT NULL,
                    storage_path VARCHAR(500) NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    created_by VARCHAR(50) NOT NULL
                );
                """)
                # Document Metadata Table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS document_metadata (
                    id VARCHAR(50) PRIMARY KEY,
                    document_id VARCHAR(50) REFERENCES documents(id) ON DELETE CASCADE UNIQUE,
                    metadata JSONB NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                );
                """)
                # Document Classifications Table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS document_classifications (
                    id VARCHAR(50) PRIMARY KEY,
                    document_id VARCHAR(50) REFERENCES documents(id) ON DELETE CASCADE,
                    category VARCHAR(100) NOT NULL,
                    confidence FLOAT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                );
                """)
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Failed to create document tables: {e}")

    def create(self, document: Document) -> Document:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO documents (id, original_filename, mime_type, size_bytes, sha256_hash, status, created_at, updated_at, created_by, is_deleted)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                document.id, document.original_filename, document.mime_type, document.size_bytes,
                document.sha256_hash, document.status.value, document.created_at, document.updated_at,
                document.created_by, document.is_deleted
            ))
            conn.commit()
            return document

    def get_by_id(self, document_id: str) -> Optional[Document]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, original_filename, mime_type, size_bytes, sha256_hash, status, created_at, updated_at, created_by, is_deleted
                FROM documents WHERE id = %s
            """, (document_id,))
            row = cur.fetchone()
            if not row:
                return None
            return Document(
                id=row[0], original_filename=row[1], mime_type=row[2], size_bytes=row[3],
                sha256_hash=row[4], status=DocumentStatus(row[5]), created_at=row[6],
                updated_at=row[7], created_by=row[8], is_deleted=row[9]
            )

    def get_by_sha256(self, sha256_hash: str) -> Optional[Document]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, original_filename, mime_type, size_bytes, sha256_hash, status, created_at, updated_at, created_by, is_deleted
                FROM documents WHERE sha256_hash = %s AND is_deleted = FALSE
            """, (sha256_hash,))
            row = cur.fetchone()
            if not row:
                return None
            return Document(
                id=row[0], original_filename=row[1], mime_type=row[2], size_bytes=row[3],
                sha256_hash=row[4], status=DocumentStatus(row[5]), created_at=row[6],
                updated_at=row[7], created_by=row[8], is_deleted=row[9]
            )

    def update_status(self, document_id: str, status: DocumentStatus) -> None:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("UPDATE documents SET status = %s WHERE id = %s", (status.value, document_id))
            conn.commit()

    def soft_delete(self, document_id: str) -> None:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("UPDATE documents SET is_deleted = TRUE WHERE id = %s", (document_id,))
            conn.commit()

    def restore(self, document_id: str) -> None:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("UPDATE documents SET is_deleted = FALSE WHERE id = %s", (document_id,))
            conn.commit()

    def list_documents(
        self, skip: int = 0, limit: int = 50, status: Optional[DocumentStatus] = None, include_deleted: bool = False
    ) -> Tuple[List[Document], int]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            query = "SELECT id, original_filename, mime_type, size_bytes, sha256_hash, status, created_at, updated_at, created_by, is_deleted FROM documents WHERE 1=1"
            count_query = "SELECT COUNT(*) FROM documents WHERE 1=1"
            params: List[Any] = []
            
            if not include_deleted:
                query += " AND is_deleted = FALSE"
                count_query += " AND is_deleted = FALSE"
            if status:
                query += " AND status = %s"
                count_query += " AND status = %s"
                params.append(status.value)
            
            # Get total count
            cur.execute(count_query, tuple(params))
            total = cur.fetchone()[0]

            query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, skip])
            
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            documents = []
            for row in rows:
                documents.append(Document(
                    id=row[0], original_filename=row[1], mime_type=row[2], size_bytes=row[3],
                    sha256_hash=row[4], status=DocumentStatus(row[5]), created_at=row[6],
                    updated_at=row[7], created_by=row[8], is_deleted=row[9]
                ))
            return documents, total

    def add_version(self, version: DocumentVersion) -> DocumentVersion:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO document_versions (id, document_id, version_number, storage_path, size_bytes, created_at, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (version.id, version.document_id, version.version_number, version.storage_path, version.size_bytes, version.created_at, version.created_by))
            conn.commit()
            return version

    def get_versions(self, document_id: str) -> List[DocumentVersion]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, document_id, version_number, storage_path, size_bytes, created_at, created_by
                FROM document_versions WHERE document_id = %s ORDER BY version_number DESC
            """, (document_id,))
            rows = cur.fetchall()
            return [DocumentVersion(id=r[0], document_id=r[1], version_number=r[2], storage_path=r[3], size_bytes=r[4], created_at=r[5], created_by=r[6]) for r in rows]

    def upsert_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO document_metadata (id, document_id, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (document_id) DO UPDATE SET
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
            """, (metadata.id, metadata.document_id, json.dumps(metadata.metadata), metadata.created_at, metadata.updated_at))
            conn.commit()
            return metadata

    def get_metadata(self, document_id: str) -> Optional[DocumentMetadata]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute("SELECT id, document_id, metadata, created_at, updated_at FROM document_metadata WHERE document_id = %s", (document_id,))
            row = cur.fetchone()
            if not row:
                return None
            return DocumentMetadata(id=row[0], document_id=row[1], metadata=row[2], created_at=row[3], updated_at=row[4])
