"""Search domain models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.document.constants import ChunkType


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    document_title: str
    chunk_type: ChunkType
    text: str
    page_number: Optional[int]
    parent_section_header: Optional[str]
    bbox_json: Optional[dict]
    score: float
    role_scope: str
