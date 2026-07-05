"""M3 — Document Parsing Use Case.

Orchestrates the full extraction pipeline for a single document:
  1. Download binary from MinIO
  2. Route to the correct IDocumentParser
  3. Finalize chunks via the hierarchical chunker
  4. Persist to PostgreSQL via IChunkRepository
  5. Update JobStatus through EXTRACTING → EXTRACTED → PARSING → CHUNKED
"""

from __future__ import annotations

import logging
from typing import List

from app.domain.document.constants import DocumentStatus, JobStatus
from app.domain.document.interfaces import (
    IChunkRepository,
    IDocumentParser,
    IDocumentRepository,
    IJobRepository,
    IStorageService,
)
from app.domain.document.models import DocumentChunk
from app.domain.document.parser_registry import ParserRegistry

logger = logging.getLogger(__name__)

_BUCKET = "industrial-documents"


class DocumentParsingUseCase:
    def __init__(
        self,
        document_repo: IDocumentRepository,
        storage_service: IStorageService,
        job_repo: IJobRepository,
        chunk_repo: IChunkRepository,
        parsers: List[IDocumentParser],
    ):
        self._doc_repo = document_repo
        self._storage = storage_service
        self._job_repo = job_repo
        self._chunk_repo = chunk_repo
        self._parsers = parsers
        self._registry = ParserRegistry(parsers)

    def parse_document(self, document_id: str, job_id: str) -> List[DocumentChunk]:
        """Full parse pipeline. Raises on unrecoverable errors after marking job FAILED."""
        job_repo = self._job_repo

        def _fail(msg: str) -> None:
            logger.error("Parse failed for doc %s: %s", document_id, msg)
            job_repo.update_status(job_id, JobStatus.FAILED, error_message=msg)
            self._doc_repo.update_status(document_id, DocumentStatus.FAILED)

        # ── 1. EXTRACTING ─────────────────────────────────────────────────
        job_repo.update_status(job_id, JobStatus.EXTRACTING)
        self._doc_repo.update_status(document_id, DocumentStatus.PROCESSING)

        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            _fail(f"Document {document_id} not found.")
            return []

        versions = self._doc_repo.get_versions(document_id)
        if not versions:
            _fail("No stored version found for document.")
            return []

        storage_path = versions[0].storage_path
        try:
            file_bytes = self._storage.download_file(_BUCKET, storage_path)
        except Exception as exc:
            _fail(f"Storage download failed: {exc}")
            return []

        job_repo.update_status(job_id, JobStatus.EXTRACTED)
        logger.info(
            "Downloaded %d bytes for document %s.", len(file_bytes), document_id
        )

        # ── 2. PARSING ────────────────────────────────────────────────────
        job_repo.update_status(job_id, JobStatus.PARSING)

        # Resolve the real document type (extension + content sniff), so files
        # with a generic/wrong declared MIME (Markdown, CSV, JSON, ...) still
        # route to the right parser.
        resolved_mime, parser = self._registry.resolve(
            doc.mime_type, doc.original_filename, file_bytes
        )
        if parser is None:
            _fail(
                f"No parser registered for '{doc.original_filename}' "
                f"(declared '{doc.mime_type}', resolved '{resolved_mime}')."
            )
            return []

        try:
            chunks = parser.parse(
                document_id=document_id,
                filename=doc.original_filename,
                mime_type=resolved_mime,
                file_bytes=file_bytes,
            )
        except Exception as exc:
            _fail(f"Parser raised: {exc}")
            return []

        logger.info(
            "Parser produced %d chunks for document %s.", len(chunks), document_id
        )

        # ── 3. CHUNKED ────────────────────────────────────────────────────
        try:
            self._chunk_repo.delete_by_document_id(document_id)
            self._chunk_repo.bulk_insert(chunks)
        except Exception as exc:
            _fail(f"Chunk persistence failed: {exc}")
            return []

        job_repo.update_status(job_id, JobStatus.CHUNKED)
        self._doc_repo.update_status(document_id, DocumentStatus.PROCESSED)
        logger.info(
            "Document %s successfully chunked into %d chunks.", document_id, len(chunks)
        )
        return chunks
