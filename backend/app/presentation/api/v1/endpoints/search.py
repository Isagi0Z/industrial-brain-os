"""Search API endpoints — semantic (vector) and keyword (BM25)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.application.search.embedding_use_case import EmbeddingUseCase
from app.domain.auth.models import User
from app.domain.search.models import SearchResult
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/search", tags=["search"])

_DEFAULT_ROLE_SCOPE = "public"


def get_embedding_use_case() -> EmbeddingUseCase:
    return container.get_embedding_use_case()


class SearchResultResponse:
    chunk_id: str
    document_id: str
    document_title: str
    chunk_type: str
    chunk_text: str
    page_number: Optional[int]
    parent_section_header: Optional[str]
    bbox_json: Optional[dict]
    score: float


def _to_response(r: SearchResult) -> dict:
    return {
        "chunk_id": r.chunk_id,
        "document_id": r.document_id,
        "document_title": r.document_title,
        "chunk_type": r.chunk_type.value,
        "chunk_text": r.text,
        "page_number": r.page_number,
        "parent_section_header": r.parent_section_header,
        "bbox_json": r.bbox_json,
        "score": round(r.score, 4),
    }


@router.get("/semantic")
async def search_semantic(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    role_scope: str = Query(_DEFAULT_ROLE_SCOPE, description="Role scope filter"),
    use_case: EmbeddingUseCase = Depends(get_embedding_use_case),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Semantic vector search over indexed document chunks."""
    results: List[SearchResult] = await use_case.search_semantic(
        query=q,
        role_scope=role_scope,
        limit=limit,
    )
    return {
        "query": q,
        "total": len(results),
        "results": [_to_response(r) for r in results],
    }


@router.get("/keyword")
async def search_keyword(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    role_scope: str = Query(_DEFAULT_ROLE_SCOPE, description="Role scope filter"),
    use_case: EmbeddingUseCase = Depends(get_embedding_use_case),
    current_user: User = Depends(get_current_user),
) -> dict:
    """BM25 keyword search over indexed document chunks."""
    results: List[SearchResult] = await use_case.search_keyword(
        query=q,
        role_scope=role_scope,
        limit=limit,
    )
    return {
        "query": q,
        "total": len(results),
        "results": [_to_response(r) for r in results],
    }
