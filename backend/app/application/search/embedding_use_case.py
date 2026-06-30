"""Embedding use case: CHUNKED → EMBEDDING → INDEXED job transition.

Reads all DocumentChunks for a document, embeds them in batches of 32,
upserts into Qdrant, and builds the BM25 index in PostgreSQL.
"""

from __future__ import annotations

import logging
from typing import List

from starlette.concurrency import run_in_threadpool

from app.domain.document.constants import JobStatus
from app.domain.document.interfaces import (
    IChunkRepository,
    IDocumentRepository,
    IJobRepository,
)
from app.domain.search.interfaces import (
    IBM25Repository,
    IEmbeddingService,
    IVectorRepository,
)
from app.domain.search.models import SearchResult

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32
_DEFAULT_ROLE_SCOPE = "public"
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 50
_COLLECTION = "document_chunks"


class EmbeddingUseCase:
    def __init__(
        self,
        document_repo: IDocumentRepository,
        chunk_repo: IChunkRepository,
        job_repo: IJobRepository,
        embedding_service: IEmbeddingService,
        vector_repo: IVectorRepository,
        bm25_repo: IBM25Repository,
        vector_dim: int = 1024,
    ) -> None:
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._job_repo = job_repo
        self._embedding_service = embedding_service
        self._vector_repo = vector_repo
        self._bm25_repo = bm25_repo
        self._vector_dim = vector_dim

    def embed_document(self, document_id: str, job_id: str) -> None:
        def _fail(msg: str) -> None:
            self._job_repo.update_status(job_id, JobStatus.FAILED, error_message=msg)
            logger.error("Embed failed for doc %s: %s", document_id, msg)

        doc = self._document_repo.get_by_id(document_id)
        if not doc:
            _fail(f"Document {document_id} not found.")
            return

        chunks = self._chunk_repo.get_by_document_id(document_id)
        if not chunks:
            _fail(f"No chunks found for document {document_id}.")
            return

        self._job_repo.update_status(job_id, JobStatus.EMBEDDING)

        try:
            self._vector_repo.ensure_collection(_COLLECTION, self._vector_dim)
            self._vector_repo.delete_by_document(_COLLECTION, document_id)

            document_title = doc.original_filename
            role_scope = _DEFAULT_ROLE_SCOPE

            for batch_start in range(0, len(chunks), _BATCH_SIZE):
                batch = chunks[batch_start : batch_start + _BATCH_SIZE]
                texts = [c.text for c in batch]
                vectors = self._embedding_service.embed_batch(texts)
                points = [
                    {
                        "id": chunk.id,
                        "vector": vector,
                        "payload": {
                            "document_id": document_id,
                            "chunk_index": chunk.chunk_index,
                            "chunk_type": chunk.chunk_type.value,
                            "page_number": chunk.page_number,
                            "parent_section_header": chunk.parent_section_header,
                            "role_scope": role_scope,
                            "document_title": document_title,
                            "revision_date": None,
                            "text": chunk.text,
                            "bbox_json": chunk.bbox_json,
                        },
                    }
                    for chunk, vector in zip(batch, vectors)
                ]
                self._vector_repo.batch_upsert(_COLLECTION, points)
                logger.info(
                    "Embedded batch %d-%d for doc %s",
                    batch_start,
                    batch_start + len(batch),
                    document_id,
                )

            self._bm25_repo.delete_by_document(document_id)
            self._bm25_repo.build_index(document_id, chunks, role_scope)

        except Exception as exc:
            _fail(f"Embedding raised: {exc}")
            return

        self._job_repo.update_status(job_id, JobStatus.INDEXED)
        logger.info("Document %s indexed successfully.", document_id)

    async def search_semantic(
        self,
        query: str,
        role_scope: str = _DEFAULT_ROLE_SCOPE,
        limit: int = _DEFAULT_LIMIT,
    ) -> List[SearchResult]:
        limit = min(limit, _MAX_LIMIT)
        vector: List[float] = await run_in_threadpool(
            self._embedding_service.embed_one, query
        )
        return self._vector_repo.search(_COLLECTION, vector, role_scope, limit)

    async def search_keyword(
        self,
        query: str,
        role_scope: str = _DEFAULT_ROLE_SCOPE,
        limit: int = _DEFAULT_LIMIT,
    ) -> List[SearchResult]:
        limit = min(limit, _MAX_LIMIT)
        return await run_in_threadpool(self._bm25_repo.search, query, role_scope, limit)
