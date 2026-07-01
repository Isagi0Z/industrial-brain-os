"""Knowledge Brain tool registry (M9).

Thin, independently-testable wrappers around domain interfaces, kept
separate from the LangGraph state machine definition
(app/application/knowledge_brain/knowledge_brain_agent.py) per the M9
checklist. Each tool takes the domain interface it needs as a parameter —
no container/DI imports here, so every function is pure and unit-testable
with plain mocks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IDocumentRepository
from app.domain.document.models import Document, DocumentChunk
from app.domain.extraction.interfaces import IEntityExtractor
from app.domain.extraction.models import ExtractedEntity
from app.domain.graphrag.interfaces import IGraphRAGEngine, IKGTraversalService
from app.domain.graphrag.models import HybridSearchResult, KGPath


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


async def semantic_search_tool(
    graphrag_engine: IGraphRAGEngine,
    query: str,
    role_scope: str,
    top_k: int,
) -> HybridSearchResult:
    """Full hybrid retrieval (BM25 + dense vector + KG traversal + rerank)
    via GraphRAGEngine (M8). Used for document_search / procedural queries."""
    return await graphrag_engine.retrieve(query, role_scope, top_k)


def graph_search_tool(
    kg_traversal: IKGTraversalService,
    tags: List[str],
    max_depth: int,
    limit: int,
) -> List[KGPath]:
    """Direct KG traversal for a known set of entity tags, bypassing the
    BM25/vector/rerank stages. Used for entity_lookup queries where the
    tag is already known and a full hybrid search would be wasted work."""
    if not tags:
        return []
    return kg_traversal.traverse(tags, max_depth, limit)


def entity_lookup_tool(
    entity_extractor: IEntityExtractor,
    query: str,
) -> List[ExtractedEntity]:
    """Extract industrial entity tags mentioned in free text, reusing the
    same SpacyEntityExtractor (M7) used during document ingestion."""
    chunk = _wrap_as_chunk(query)
    return [e for e in entity_extractor.extract(chunk) if e.tag_number]


def document_lookup_tool(
    document_repo: IDocumentRepository,
    document_id: str,
) -> Optional[Document]:
    """Look up a single document by id (reuses M2's IDocumentRepository)."""
    return document_repo.get_by_id(document_id)
