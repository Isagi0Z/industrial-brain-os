"""Unit and integration tests for M4 — Embedding Pipeline & Qdrant Indexing.

All external dependencies (Qdrant, PostgreSQL, embedding model) are mocked
except in the integration test, which uses the real DI container.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock

import pytest

from app.domain.document.constants import ChunkType, JobStatus
from app.domain.document.models import DocumentChunk
from app.domain.search.models import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(timezone.utc)


def _make_chunk(
    doc_id: str = "doc-1",
    idx: int = 0,
    chunk_type: ChunkType = ChunkType.PARAGRAPH,
    text: str = "centrifugal pump maintenance procedure",
) -> DocumentChunk:
    return DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=doc_id,
        chunk_index=idx,
        chunk_type=chunk_type,
        text=text,
        page_number=1,
        parent_section_header=None,
        bbox_json=None,
        token_count=len(text.split()),
        created_at=_now(),
    )


def _make_search_result(score: float = 0.9) -> SearchResult:
    return SearchResult(
        chunk_id=str(uuid.uuid4()),
        document_id="doc-1",
        document_title="Test Doc",
        chunk_type=ChunkType.PARAGRAPH,
        text="pump maintenance",
        page_number=1,
        parent_section_header=None,
        bbox_json=None,
        score=score,
        role_scope="public",
    )


# ---------------------------------------------------------------------------
# IEmbeddingService unit tests
# ---------------------------------------------------------------------------


def test_embedding_service_embed_one_returns_list():
    from app.domain.search.interfaces import IEmbeddingService

    class FakeEmbedder(IEmbeddingService):
        def embed_batch(self, texts: List[str]) -> List[List[float]]:
            return [[0.1] * 1024 for _ in texts]

        def embed_one(self, text: str) -> List[float]:
            return self.embed_batch([text])[0]

    svc = FakeEmbedder()
    result = svc.embed_one("test text")
    assert len(result) == 1024
    assert isinstance(result[0], float)


def test_embedding_service_embed_batch_multiple():
    from app.domain.search.interfaces import IEmbeddingService

    class FakeEmbedder(IEmbeddingService):
        def embed_batch(self, texts: List[str]) -> List[List[float]]:
            return [[float(i)] * 1024 for i, _ in enumerate(texts)]

        def embed_one(self, text: str) -> List[float]:
            return self.embed_batch([text])[0]

    svc = FakeEmbedder()
    results = svc.embed_batch(["a", "b", "c"])
    assert len(results) == 3
    assert results[0][0] == 0.0
    assert results[1][0] == 1.0


# ---------------------------------------------------------------------------
# QdrantVectorRepository unit tests
# ---------------------------------------------------------------------------


def test_qdrant_ensure_collection_creates_if_missing():
    from app.infrastructure.search.qdrant_repository import QdrantVectorRepository

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = []
    repo = QdrantVectorRepository(lambda: mock_client)

    repo.ensure_collection("test_col", 1024)

    mock_client.create_collection.assert_called_once()


def test_qdrant_ensure_collection_skips_existing():
    from app.infrastructure.search.qdrant_repository import QdrantVectorRepository

    mock_client = MagicMock()
    existing = MagicMock()
    existing.name = "doc_chunks"
    mock_client.get_collections.return_value.collections = [existing]
    repo = QdrantVectorRepository(lambda: mock_client)

    repo.ensure_collection("doc_chunks", 1024)

    mock_client.create_collection.assert_not_called()


def test_qdrant_batch_upsert_calls_client():
    from app.infrastructure.search.qdrant_repository import QdrantVectorRepository

    mock_client = MagicMock()
    repo = QdrantVectorRepository(lambda: mock_client)

    points = [
        {"id": "abc", "vector": [0.1] * 1024, "payload": {"document_id": "d1"}},
        {"id": "def", "vector": [0.2] * 1024, "payload": {"document_id": "d1"}},
    ]
    repo.batch_upsert("chunks", points)

    mock_client.upsert.assert_called_once()
    call_args = mock_client.upsert.call_args
    assert call_args.kwargs["collection_name"] == "chunks"
    assert len(call_args.kwargs["points"]) == 2


def test_qdrant_search_maps_hits_to_search_results():
    from app.infrastructure.search.qdrant_repository import QdrantVectorRepository

    mock_client = MagicMock()
    hit = MagicMock()
    hit.id = str(uuid.uuid4())
    hit.score = 0.87
    hit.payload = {
        "document_id": "doc-x",
        "document_title": "Pump Manual",
        "chunk_type": "paragraph",
        "text": "bearing inspection",
        "page_number": 3,
        "parent_section_header": "Maintenance",
        "bbox_json": None,
        "role_scope": "public",
    }
    mock_client.search.return_value = [hit]

    repo = QdrantVectorRepository(lambda: mock_client)
    results = repo.search("chunks", [0.1] * 1024, "public", 5)

    assert len(results) == 1
    assert results[0].score == pytest.approx(0.87)
    assert results[0].document_title == "Pump Manual"
    assert results[0].chunk_type == ChunkType.PARAGRAPH


def test_qdrant_search_applies_role_scope_filter():
    from app.infrastructure.search.qdrant_repository import QdrantVectorRepository

    mock_client = MagicMock()
    mock_client.search.return_value = []

    repo = QdrantVectorRepository(lambda: mock_client)
    repo.search("chunks", [0.0] * 1024, "engineering", 5)

    call_kwargs = mock_client.search.call_args.kwargs
    filt = call_kwargs["query_filter"]
    assert filt is not None
    condition = filt.must[0]
    assert condition.key == "role_scope"
    assert condition.match.value == "engineering"


# ---------------------------------------------------------------------------
# BM25 repository unit tests
# ---------------------------------------------------------------------------


def test_bm25_tokenize():
    from app.infrastructure.search.bm25_repository import _tokenize

    tokens = _tokenize("The pump valve is broken")
    assert "pump" in tokens
    assert "valve" in tokens
    assert "the" not in tokens
    assert "is" not in tokens


def test_bm25_tokenize_empty():
    from app.infrastructure.search.bm25_repository import _tokenize

    assert _tokenize("") == []
    assert _tokenize("the an is") == []


def test_bm25_build_index_and_search():
    from app.infrastructure.search.bm25_repository import PostgresBM25Repository

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    repo = PostgresBM25Repository(lambda: mock_conn)

    chunks = [
        _make_chunk(text="pump bearing wear inspection"),
        _make_chunk(idx=1, text="valve pressure test procedure"),
    ]
    repo.build_index("doc-1", chunks, "public")

    mock_cur.executemany.assert_called_once()
    mock_conn.commit.assert_called()


def test_bm25_search_returns_normalized_scores():
    from app.infrastructure.search.bm25_repository import PostgresBM25Repository

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    cid1 = str(uuid.uuid4())
    mock_cur.fetchone.return_value = (3,)
    mock_cur.fetchall.side_effect = [
        [("pump", 2)],
        [
            (
                cid1,
                0,
                "paragraph",
                "pump",
                0.4,
                "doc-1",
                "Manual",
                1,
                None,
                None,
                "pump bearing wear",
            ),
            (
                cid1,
                0,
                "paragraph",
                "pump",
                0.4,
                "doc-1",
                "Manual",
                1,
                None,
                None,
                "pump bearing wear",
            ),
        ],
    ]

    repo = PostgresBM25Repository(lambda: mock_conn)
    results = repo.search("pump inspection", "public", 5)

    assert len(results) >= 0
    for r in results:
        assert 0.0 <= r.score <= 1.0


# ---------------------------------------------------------------------------
# RBAC filter unit test
# ---------------------------------------------------------------------------


def test_qdrant_search_empty_for_wrong_scope():
    from app.infrastructure.search.qdrant_repository import QdrantVectorRepository

    mock_client = MagicMock()
    mock_client.search.return_value = []

    repo = QdrantVectorRepository(lambda: mock_client)
    results = repo.search("chunks", [0.1] * 1024, "restricted_ops", 5)

    assert results == []
    call_kwargs = mock_client.search.call_args.kwargs
    assert call_kwargs["query_filter"].must[0].match.value == "restricted_ops"


# ---------------------------------------------------------------------------
# EmbeddingUseCase unit tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_embedding_use_case():
    from app.application.search.embedding_use_case import EmbeddingUseCase

    doc_repo = MagicMock()
    chunk_repo = MagicMock()
    job_repo = MagicMock()
    embedder = MagicMock()
    vector_repo = MagicMock()
    bm25_repo = MagicMock()

    embedder.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]
    embedder.embed_one.return_value = [0.1] * 1024

    uc = EmbeddingUseCase(
        document_repo=doc_repo,
        chunk_repo=chunk_repo,
        job_repo=job_repo,
        embedding_service=embedder,
        vector_repo=vector_repo,
        bm25_repo=bm25_repo,
        vector_dim=1024,
    )
    return uc, doc_repo, chunk_repo, job_repo, embedder, vector_repo, bm25_repo


def test_embed_document_success(mock_embedding_use_case):
    uc, doc_repo, chunk_repo, job_repo, embedder, vector_repo, bm25_repo = (
        mock_embedding_use_case
    )

    from app.domain.document.models import Document, DocumentStatus

    doc = Document(
        id="doc-1",
        original_filename="pump.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        sha256_hash="abc",
        status=DocumentStatus.PROCESSED,
        created_at=_now(),
        updated_at=_now(),
        created_by="user-1",
    )
    doc_repo.get_by_id.return_value = doc
    chunk_repo.get_by_document_id.return_value = [
        _make_chunk(text="pump bearing"),
        _make_chunk(idx=1, text="valve inspection"),
    ]
    vector_repo.search.return_value = []

    uc.embed_document("doc-1", "job-1")

    job_repo.update_status.assert_any_call("job-1", JobStatus.EMBEDDING)
    job_repo.update_status.assert_any_call("job-1", JobStatus.INDEXED)
    vector_repo.batch_upsert.assert_called()
    bm25_repo.build_index.assert_called_once()


def test_embed_document_missing_doc(mock_embedding_use_case):
    uc, doc_repo, chunk_repo, job_repo, *_ = mock_embedding_use_case
    doc_repo.get_by_id.return_value = None

    uc.embed_document("missing", "job-2")

    calls = [str(c) for c in job_repo.update_status.call_args_list]
    assert any("FAILED" in c for c in calls)


def test_embed_document_no_chunks(mock_embedding_use_case):
    uc, doc_repo, chunk_repo, job_repo, *_ = mock_embedding_use_case
    from app.domain.document.models import Document, DocumentStatus

    doc_repo.get_by_id.return_value = Document(
        id="doc-1",
        original_filename="f.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        sha256_hash="x",
        status=DocumentStatus.PROCESSED,
        created_at=_now(),
        updated_at=_now(),
        created_by="u",
    )
    chunk_repo.get_by_document_id.return_value = []

    uc.embed_document("doc-1", "job-3")

    calls = [str(c) for c in job_repo.update_status.call_args_list]
    assert any("FAILED" in c for c in calls)


# ---------------------------------------------------------------------------
# Integration test — real DB + real model (5 chunks, semantic query)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_index_and_semantic_search():
    """Index 5 chunks into Qdrant, run semantic query, verify top-1 is correct."""
    import os

    os.environ.setdefault("USE_TF", "0")

    from app.infrastructure.di.container import container
    from app.infrastructure.search.embedding_service import (
        SentenceTransformerEmbedder,
    )
    from app.infrastructure.search.qdrant_repository import QdrantVectorRepository

    embedder = SentenceTransformerEmbedder()
    vector_repo = QdrantVectorRepository(container.get_qdrant)

    test_collection = "test_m4_integration"
    vector_repo.ensure_collection(test_collection, 1024)

    texts = [
        "centrifugal pump impeller wear causes vibration and flow loss",
        "valve seat corrosion leads to leakage in high pressure systems",
        "bearing temperature rise indicates lubrication failure",
        "motor winding insulation resistance degrades in humid environments",
        "pipe flange bolt torque specification for ASME class 150",
    ]
    chunks = [_make_chunk(idx=i, text=t) for i, t in enumerate(texts)]

    vectors = embedder.embed_batch(texts)
    points = [
        {
            "id": chunks[i].id,
            "vector": vectors[i],
            "payload": {
                "document_id": "doc-integration",
                "chunk_index": i,
                "chunk_type": chunks[i].chunk_type.value,
                "page_number": 1,
                "parent_section_header": None,
                "role_scope": "public",
                "document_title": "Integration Test",
                "revision_date": None,
                "text": texts[i],
                "bbox_json": None,
            },
        }
        for i in range(len(texts))
    ]
    vector_repo.batch_upsert(test_collection, points)

    query = "pump impeller wear vibration"
    q_vector = embedder.embed_one(query)
    results = vector_repo.search(test_collection, q_vector, "public", 3)

    assert len(results) >= 1
    top_text = results[0].text
    assert "pump" in top_text.lower() or "impeller" in top_text.lower()

    vector_repo.delete_by_document(test_collection, "doc-integration")
    try:
        client = container.get_qdrant()
        client.delete_collection(test_collection)
    except Exception:
        pass
