"""Hierarchical token-aware chunker (ADR-012).

Splits paragraphs that exceed CHUNK_HARD_MAX_TOKENS into overlapping sub-chunks
while keeping tables and figures as single atomic chunks.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List

import tiktoken

from app.domain.document.constants import (
    CHUNK_HARD_MAX_TOKENS,
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SOFT_MAX_TOKENS,
    ChunkType,
)
from app.domain.document.models import DocumentChunk

logger = logging.getLogger(__name__)

_ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _split_text_with_overlap(
    text: str,
    soft_max: int = CHUNK_SOFT_MAX_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> List[str]:
    """Split text into token windows with overlap. Only called for oversized paragraphs."""
    tokens = _ENC.encode(text)
    if len(tokens) <= soft_max:
        return [text]

    segments: List[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + CHUNK_HARD_MAX_TOKENS, len(tokens))
        segments.append(_ENC.decode(tokens[start:end]))
        if end >= len(tokens):
            break
        start = end - overlap
    return segments


def finalize_chunks(
    raw_chunks: List[DocumentChunk],
) -> List[DocumentChunk]:
    """
    Post-process raw chunks:
    - Tables and figures pass through unchanged (single atomic chunk).
    - Paragraphs / headings exceeding CHUNK_HARD_MAX_TOKENS are split with overlap.
    - Re-indexes chunk_index sequentially.
    """
    now = datetime.now(timezone.utc)
    result: List[DocumentChunk] = []
    idx = 0

    for chunk in raw_chunks:
        atomic_types = {ChunkType.TABLE, ChunkType.FIGURE}
        if (
            chunk.chunk_type in atomic_types
            or count_tokens(chunk.text) <= CHUNK_HARD_MAX_TOKENS
        ):
            result.append(
                DocumentChunk(
                    id=chunk.id if not result else str(uuid.uuid4()),
                    document_id=chunk.document_id,
                    chunk_index=idx,
                    chunk_type=chunk.chunk_type,
                    text=chunk.text,
                    page_number=chunk.page_number,
                    parent_section_header=chunk.parent_section_header,
                    bbox_json=chunk.bbox_json,
                    token_count=count_tokens(chunk.text),
                    created_at=now,
                    table_data_json=chunk.table_data_json,
                    figure_storage_key=chunk.figure_storage_key,
                )
            )
            idx += 1
        else:
            for seg in _split_text_with_overlap(chunk.text):
                result.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=chunk.document_id,
                        chunk_index=idx,
                        chunk_type=chunk.chunk_type,
                        text=seg,
                        page_number=chunk.page_number,
                        parent_section_header=chunk.parent_section_header,
                        bbox_json=chunk.bbox_json,
                        token_count=count_tokens(seg),
                        created_at=now,
                    )
                )
                idx += 1

    return result
