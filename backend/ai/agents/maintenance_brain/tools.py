"""Maintenance Brain tool registry (M10).

Thin, independently-testable wrappers around domain interfaces, kept
separate from the LangGraph state machine definition
(app/application/maintenance_brain/maintenance_brain_agent.py), matching
the pattern established for the Knowledge Brain (M9).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import List, Optional

from app.domain.document.constants import ChunkType
from app.domain.document.models import DocumentChunk
from app.domain.extraction.interfaces import IEntityExtractor
from app.domain.graphrag.interfaces import IGraphRAGEngine
from app.domain.graphrag.models import HybridSearchResult
from app.domain.maintenance_brain.interfaces import (
    IFailureHistoryRepository,
    IWorkOrderRepository,
)
from app.domain.maintenance_brain.models import FailureRecord, WorkOrder

# Document titles are matched case-insensitively against these keywords as a
# stand-in for a real document_category filter — no current write path in
# this codebase populates DocumentClassification.category or indexes it
# into Qdrant, so "document_category = OEM Manual" cannot yet be enforced
# at the retrieval layer itself. See docs/verification/m10_verification.md.
_OEM_MANUAL_KEYWORDS = (
    "manual",
    "oem",
    "datasheet",
    "data sheet",
    "spec sheet",
    "specification",
    "installation guide",
    "operation guide",
    "service guide",
)


def _wrap_as_chunk(text: str) -> DocumentChunk:
    """Wrap raw free text (a user query) in a throwaway DocumentChunk so it
    can be run through the same entity extractor used at ingestion time."""
    return DocumentChunk(
        id="query",
        document_id="query",
        chunk_index=0,
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=None,
        parent_section_header=None,
        bbox_json=None,
        token_count=len(text.split()),
        created_at=datetime.now(timezone.utc),
        table_data_json=None,
        figure_storage_key=None,
    )


def extract_asset_tag_tool(
    entity_extractor: IEntityExtractor, query: str
) -> Optional[str]:
    """Extract the primary asset/equipment tag mentioned in free text
    (reuses the same SpacyEntityExtractor, M7, used at ingestion time)."""
    chunk = _wrap_as_chunk(query)
    for entity in entity_extractor.extract(chunk):
        if entity.tag_number:
            return entity.tag_number
    return None


def work_order_lookup(
    work_order_repo: IWorkOrderRepository,
    asset_tag: Optional[str] = None,
    wo_id: Optional[str] = None,
) -> List[WorkOrder]:
    """Look up work orders by explicit id, or all work orders for an asset."""
    if wo_id:
        wo = work_order_repo.find_by_wo_id(wo_id)
        return [wo] if wo else []
    if asset_tag:
        return work_order_repo.find_by_asset_tag(asset_tag)
    return []


def maintenance_schedule_query(
    work_order_repo: IWorkOrderRepository, asset_tag: Optional[str]
) -> List[WorkOrder]:
    """Open work orders for an asset, sorted by scheduled_date ascending."""
    if not asset_tag:
        return []
    return work_order_repo.find_open_by_asset_tag(asset_tag)


def failure_history_search(
    failure_history_repo: IFailureHistoryRepository, asset_tag: Optional[str]
) -> List[FailureRecord]:
    """(Equipment)-[:EXHIBITS]->(FailureMode) records for an asset (M6/M7 ontology)."""
    if not asset_tag:
        return []
    return failure_history_repo.search_by_asset_tag(asset_tag)


async def oem_manual_lookup(
    graphrag_engine: IGraphRAGEngine,
    query: str,
    role_scope: str,
    top_k: int,
) -> HybridSearchResult:
    """Full hybrid retrieval (M8) filtered to chunks that look like OEM
    manual content, via a document-title keyword heuristic (see module
    docstring — no document_category indexing pipeline exists yet)."""
    result = await graphrag_engine.retrieve(query, role_scope, top_k)
    filtered = [
        rc
        for rc in result.ranked_chunks
        if _looks_like_oem_manual(rc.result.document_title)
    ]
    return dataclasses.replace(result, ranked_chunks=filtered)


def _looks_like_oem_manual(document_title: str) -> bool:
    lowered = document_title.lower()
    return any(keyword in lowered for keyword in _OEM_MANUAL_KEYWORDS)
