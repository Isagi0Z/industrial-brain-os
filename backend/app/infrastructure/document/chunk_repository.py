"""PostgreSQL implementation of IChunkRepository."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IChunkRepository
from app.domain.document.models import DocumentChunk

logger = logging.getLogger(__name__)


class PostgresChunkRepository(IChunkRepository):
    def __init__(self, get_connection_fn):
        self.get_connection_fn = get_connection_fn

    @staticmethod
    def _row_to_chunk(row: tuple) -> DocumentChunk:
        created_at = row[9]
        if isinstance(created_at, datetime) and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        table_data = row[10]
        if isinstance(table_data, str):
            table_data = json.loads(table_data)

        return DocumentChunk(
            id=row[0],
            document_id=row[1],
            chunk_index=row[2],
            chunk_type=ChunkType(row[3]),
            text=row[4],
            page_number=row[5],
            parent_section_header=row[6],
            bbox_json=row[7],
            token_count=row[8],
            created_at=created_at,
            table_data_json=table_data,
            figure_storage_key=row[11],
        )

    def bulk_insert(self, chunks: List[DocumentChunk]) -> None:
        if not chunks:
            return
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            for chunk in chunks:
                table_json = (
                    json.dumps(chunk.table_data_json) if chunk.table_data_json else None
                )
                bbox_json = json.dumps(chunk.bbox_json) if chunk.bbox_json else None
                cur.execute(
                    """
                    INSERT INTO document_chunks
                        (id, document_id, chunk_index, chunk_type, text,
                         page_number, parent_section_header, bbox_json,
                         token_count, created_at, table_data_json, figure_storage_key)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.chunk_index,
                        chunk.chunk_type.value,
                        chunk.text,
                        chunk.page_number,
                        chunk.parent_section_header,
                        bbox_json,
                        chunk.token_count,
                        chunk.created_at,
                        table_json,
                        chunk.figure_storage_key,
                    ),
                )
            conn.commit()
        logger.info(
            "Inserted %d chunks for document %s.",
            len(chunks),
            chunks[0].document_id if chunks else "?",
        )

    def get_by_document_id(self, document_id: str) -> List[DocumentChunk]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, document_id, chunk_index, chunk_type, text,
                       page_number, parent_section_header, bbox_json,
                       token_count, created_at, table_data_json, figure_storage_key
                FROM document_chunks
                WHERE document_id = %s
                ORDER BY chunk_index
                """,
                (document_id,),
            )
            return [self._row_to_chunk(r) for r in cur.fetchall()]

    def delete_by_document_id(self, document_id: str) -> None:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM document_chunks WHERE document_id = %s", (document_id,)
            )
            conn.commit()
        logger.info("Deleted all chunks for document %s.", document_id)
