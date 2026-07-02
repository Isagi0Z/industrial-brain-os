"""Unit tests for M14 — 8-Stage Pipeline completion (Stage 7 LLMLingua
context compression + Stage 8 citation validation).

The LLMLingua model is never loaded here: the compressor's small-context
skip path and a monkeypatched internal compressor cover Stage 7 without a
real model download. Stage 8 is pure logic.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator, List, Tuple
from unittest.mock import MagicMock

from app.domain.document.constants import ChunkType
from app.domain.graphrag.models import (
    CompressionResult,
    HybridSearchResult,
    RankedChunk,
)
from app.domain.search.models import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(text: str = "chunk text", title: str = "Pump Manual", page: int = 3):
    return SearchResult(
        chunk_id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        document_title=title,
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=page,
        parent_section_header=None,
        bbox_json={"x": 1, "y": 2, "w": 3, "h": 4},
        score=0.9,
        role_scope="public",
    )


def _ranked(*results) -> List[RankedChunk]:
    return [RankedChunk(result=r, rerank_score=r.score) for r in results]


# ---------------------------------------------------------------------------
# Stage 7 — LLMLinguaCompressor (graceful degradation, no model load)
# ---------------------------------------------------------------------------


class TestLLMLinguaCompressor:
    def test_skips_small_context_without_loading(self):
        from app.infrastructure.graphrag.llmlingua_compressor import LLMLinguaCompressor

        comp = LLMLinguaCompressor("some/model")
        out = comp.compress("short context", target_ratio=0.7, min_tokens=2000)

        assert out.was_compressed is False
        assert out.ratio == 1.0
        assert out.compressed_text == "short context"
        # never attempted to load the model
        assert comp._load_attempted is False

    def test_passthrough_when_backend_unavailable(self):
        from app.infrastructure.graphrag.llmlingua_compressor import LLMLinguaCompressor

        comp = LLMLinguaCompressor("some/model")
        comp._load_attempted = True
        comp._available = False
        comp._compressor = None

        text = "word " * 50  # > min_tokens below
        out = comp.compress(text, target_ratio=0.7, min_tokens=5)

        assert out.was_compressed is False
        assert out.ratio == 1.0
        assert out.compressed_text == text

    def test_parses_llmlingua_output(self):
        from app.infrastructure.graphrag.llmlingua_compressor import LLMLinguaCompressor

        fake = MagicMock()
        fake.compress_prompt.return_value = {
            "compressed_prompt": "compressed version",
            "compressed_tokens": 70,
            "origin_tokens": 100,
        }

        comp = LLMLinguaCompressor("some/model")
        comp._load_attempted = True
        comp._available = True
        comp._compressor = fake

        text = "word " * 50
        out = comp.compress(text, target_ratio=0.7, min_tokens=5)

        assert out.was_compressed is True
        assert out.compressed_text == "compressed version"
        assert out.original_tokens == 100
        assert out.compressed_tokens == 70
        assert out.ratio == 0.7

    def test_compression_failure_degrades_to_passthrough(self):
        from app.infrastructure.graphrag.llmlingua_compressor import LLMLinguaCompressor

        fake = MagicMock()
        fake.compress_prompt.side_effect = RuntimeError("model boom")

        comp = LLMLinguaCompressor("some/model")
        comp._load_attempted = True
        comp._available = True
        comp._compressor = fake

        text = "word " * 50
        out = comp.compress(text, target_ratio=0.7, min_tokens=5)

        assert out.was_compressed is False
        assert out.compressed_text == text


# ---------------------------------------------------------------------------
# Stage 8 — citation validation (pure logic)
# ---------------------------------------------------------------------------


class TestCitationValidation:
    def _citations(self, n: int):
        from app.domain.chat.models import Citation

        return [
            Citation(
                chunk_id=f"c{i}",
                document_title=f"Doc {i}",
                page_number=i,
                chunk_text_excerpt="excerpt",
                score=0.9,
                storage_key=f"doc-{i}",
                bbox_json={"page": i},
            )
            for i in range(1, n + 1)
        ]

    def test_all_valid_citations(self):
        from app.application.chat.citation_validation import validate_citations

        answer = "The valve is rated 10 bar [source_1] and inspected yearly [source_2]."
        cleaned, report = validate_citations(answer, self._citations(2))

        assert report.validated_count == 2
        assert report.hallucinated_count == 0
        assert report.quality_flag == "OK"
        assert cleaned == answer  # valid markers kept
        assert report.validated_sources[0].source_index == 1
        assert report.validated_sources[0].document_id == "doc-1"
        assert report.validated_sources[0].bbox_json == {"page": 1}

    def test_hallucinated_citation_stripped_and_flagged(self):
        from app.application.chat.citation_validation import validate_citations

        answer = "Per the manual [source_1], torque is 40 Nm [source_9]."
        cleaned, report = validate_citations(answer, self._citations(2))

        assert report.validated_count == 1
        assert report.hallucinated_count == 1
        assert report.quality_flag == "CITATION_WARNING"
        assert "[source_9]" not in cleaned
        assert "[source_1]" in cleaned

    def test_no_markers_yields_empty_report(self):
        from app.application.chat.citation_validation import validate_citations

        cleaned, report = validate_citations("Plain answer.", self._citations(3))

        assert report.validated_count == 0
        assert report.hallucinated_count == 0
        assert report.quality_flag == "OK"
        assert cleaned == "Plain answer."

    def test_duplicate_citation_counts_once(self):
        from app.application.chat.citation_validation import validate_citations

        answer = "See [source_1]. Also [source_1] again."
        _, report = validate_citations(answer, self._citations(2))

        assert report.validated_count == 1


# ---------------------------------------------------------------------------
# Stage 7 wiring — GraphRAGEngine assembly + compression
# ---------------------------------------------------------------------------


def _make_engine(compressor=None):
    from app.application.graphrag.graphrag_engine import GraphRAGEngine

    embedding_uc = MagicMock()

    async def _bm25(*a, **kw):
        return [_result(text="bm25 hit")]

    async def _vector(*a, **kw):
        return [_result(text="vector hit")]

    embedding_uc.search_keyword = _bm25
    embedding_uc.search_semantic = _vector

    entity_extractor = MagicMock()
    entity_extractor.extract.return_value = []

    kg_traversal = MagicMock()
    kg_traversal.traverse.return_value = []

    reranker = MagicMock()
    reranker.rerank = lambda q, c: [(x, x.score) for x in c]

    cache = MagicMock()
    cache.get.return_value = None
    cache.set.return_value = None

    return GraphRAGEngine(
        embedding_use_case=embedding_uc,
        entity_extractor=entity_extractor,
        kg_traversal=kg_traversal,
        reranker=reranker,
        cache=cache,
        compressor=compressor,
        compression_min_tokens=1,  # force compression path in tests
    )


class TestGraphRAGStage7:
    def test_no_compressor_leaves_result_uncompressed(self):
        engine = _make_engine(compressor=None)
        result = asyncio.run(engine.retrieve("pump pressure", "public", 5))

        assert result.compression is None
        assert result.compressed_context == ""

    def test_compressor_produces_numbered_context(self):
        captured = {}

        class FakeCompressor:
            def compress(self, context, target_ratio, min_tokens):
                captured["context"] = context
                return CompressionResult(
                    compressed_text="COMPRESSED",
                    original_tokens=100,
                    compressed_tokens=70,
                    ratio=0.7,
                    was_compressed=True,
                )

        engine = _make_engine(compressor=FakeCompressor())
        result = asyncio.run(engine.retrieve("pump pressure", "public", 5))

        assert result.compression is not None
        assert result.compression.ratio == 0.7
        assert result.compressed_context == "COMPRESSED"
        # the assembled context the compressor saw is source-numbered
        assert "[source_1]" in captured["context"]
        assert "[source_2]" in captured["context"]

    def test_assemble_numbered_context_helper(self):
        from app.application.graphrag.graphrag_engine import _assemble_numbered_context

        ranked = _ranked(
            _result(text="alpha", title="A", page=1),
            _result(text="beta", title="B", page=2),
        )
        ctx = _assemble_numbered_context(ranked)
        assert ctx.startswith("[source_1] (A, p.1)")
        assert "[source_2] (B, p.2)" in ctx
        assert "alpha" in ctx and "beta" in ctx


# ---------------------------------------------------------------------------
# Stages 7+8 integration through ChatUseCase (mocked gateway)
# ---------------------------------------------------------------------------


class _FakeGateway:
    def __init__(self, response: str) -> None:
        self._response = response

    @property
    def model_name(self) -> str:
        return "fake"

    async def generate(
        self, messages: List[dict], max_tokens: int
    ) -> Tuple[str, int, int]:
        return self._response, 50, 20

    async def generate_stream(
        self, messages: List[dict], max_tokens: int
    ) -> AsyncGenerator[str, None]:
        yield self._response


class TestChatStage8Integration:
    def _use_case(self, gateway):
        from app.application.chat.chat_use_case import ChatUseCase

        r1, r2 = _result(text="first"), _result(text="second")

        engine = MagicMock()

        async def _retrieve(*a, **kw):
            return HybridSearchResult(
                ranked_chunks=_ranked(r1, r2),
                compressed_context="[source_1] first\n\n[source_2] second",
                compression=CompressionResult(
                    compressed_text="[source_1] first\n\n[source_2] second",
                    original_tokens=100,
                    compressed_tokens=70,
                    ratio=0.7,
                    was_compressed=True,
                ),
            )

        engine.retrieve = _retrieve

        history = MagicMock()
        history.get_history.return_value = []
        history.append_messages.return_value = None

        prompts = MagicMock()
        prompts.system_prompt.return_value = "sys"
        prompts.wrap_context.side_effect = lambda c: c

        return ChatUseCase(
            graphrag_engine=engine,
            primary_gateway=gateway,
            fallback_gateway=None,
            history_repo=history,
            context_builder=MagicMock(),
            prompt_loader=prompts,
        )

    def test_uses_compressed_context_and_validates_citations(self):
        from app.domain.chat.models import ChatRequest

        gateway = _FakeGateway("Answer grounded in [source_1] and [source_9].")
        uc = self._use_case(gateway)
        request = ChatRequest(query="pressure?", session_id="s1")

        async def _run():
            context = await uc.prepare(request)
            return context, await uc.chat(context)

        context, response = asyncio.run(_run())

        # compression path was used → context fed to LLM is the compressed one
        assert any("[source_1] first" in m["content"] for m in context.messages)
        # Stage 8: [source_1] valid, [source_9] hallucinated
        assert response.citation_validation is not None
        assert response.citation_validation.validated_count == 1
        assert response.citation_validation.hallucinated_count == 1
        assert response.response_quality_flag == "CITATION_WARNING"
        assert "[source_9]" not in response.answer
        assert "[source_1]" in response.answer

    def test_clean_answer_yields_ok_flag(self):
        from app.domain.chat.models import ChatRequest

        gateway = _FakeGateway("Fully grounded [source_1] [source_2].")
        uc = self._use_case(gateway)
        request = ChatRequest(query="pressure?", session_id="s2")

        async def _run():
            context = await uc.prepare(request)
            return await uc.chat(context)

        response = asyncio.run(_run())
        assert response.response_quality_flag == "OK"
        assert response.citation_validation.validated_count == 2
        assert response.citation_validation.hallucinated_count == 0
