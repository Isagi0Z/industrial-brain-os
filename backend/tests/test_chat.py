"""Unit tests for M5 — Chat API & Copilot.

All LLM gateways and external services are mocked.
No live Ollama or Gemini calls are made.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Tuple
from unittest.mock import MagicMock

import pytest

from app.domain.chat.models import (
    ChatMessage,
    ChatRequest,
    Citation,
    MessageRole,
)
from app.domain.search.models import SearchResult
from app.domain.document.constants import ChunkType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_result(
    doc_title: str = "Pump Manual",
    text: str = "Impeller inspection procedure",
    score: float = 0.9,
    page: int = 3,
) -> SearchResult:
    return SearchResult(
        chunk_id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        document_title=doc_title,
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=page,
        parent_section_header=None,
        bbox_json=None,
        score=score,
        role_scope="public",
    )


class FakeGateway:
    def __init__(self, name: str, response: str = "Answer text.") -> None:
        self._name = name
        self._response = response
        self.calls: int = 0

    @property
    def model_name(self) -> str:
        return self._name

    async def generate(
        self, messages: List[dict], max_tokens: int
    ) -> Tuple[str, int, int]:
        self.calls += 1
        return self._response, 50, 20

    async def generate_stream(
        self, messages: List[dict], max_tokens: int
    ) -> AsyncGenerator[str, None]:
        for word in self._response.split():
            yield word + " "


class FailingGateway:
    @property
    def model_name(self) -> str:
        return "fail"

    async def generate(
        self, messages: List[dict], max_tokens: int
    ) -> Tuple[str, int, int]:
        raise RuntimeError("connection refused")

    async def generate_stream(
        self, messages: List[dict], max_tokens: int
    ) -> AsyncGenerator[str, None]:
        raise RuntimeError("connection refused")
        yield ""


# ---------------------------------------------------------------------------
# ContextBuilder unit tests
# ---------------------------------------------------------------------------


def test_context_builder_deduplicates_chunks():
    from app.infrastructure.chat.context_builder import ContextBuilder

    r1 = _make_result()
    r2 = _make_result()
    r2.chunk_id = r1.chunk_id  # duplicate

    builder = ContextBuilder()
    ctx, citations = builder.build([r1, r2], max_context_tokens=8000)

    assert len(citations) == 1
    assert r1.chunk_id == citations[0].chunk_id


def test_context_builder_ranks_by_score():
    from app.infrastructure.chat.context_builder import ContextBuilder

    low = _make_result(text="low score chunk", score=0.3)
    high = _make_result(text="high score chunk", score=0.95)

    builder = ContextBuilder()
    ctx, citations = builder.build([low, high], max_context_tokens=8000)

    assert citations[0].chunk_text_excerpt.startswith("high score chunk")


def test_context_builder_respects_token_budget():
    from app.infrastructure.chat.context_builder import ContextBuilder

    long_text = "x " * 5000  # ~10_000 approx tokens
    result = _make_result(text=long_text, score=0.9)

    builder = ContextBuilder()
    ctx, citations = builder.build([result], max_context_tokens=100)

    assert len(citations) == 0
    assert ctx == ""


def test_context_builder_populates_storage_key():
    from app.infrastructure.chat.context_builder import ContextBuilder

    result = _make_result()
    builder = ContextBuilder()
    _, citations = builder.build([result], max_context_tokens=8000)

    assert citations[0].storage_key == result.document_id


def test_context_builder_includes_source_header():
    from app.infrastructure.chat.context_builder import ContextBuilder

    result = _make_result(doc_title="Valve Manual", page=5)
    builder = ContextBuilder()
    ctx, _ = builder.build([result], max_context_tokens=8000)

    assert "Valve Manual" in ctx
    assert "p.5" in ctx


# ---------------------------------------------------------------------------
# CitationCard (resolve helper) unit test
# ---------------------------------------------------------------------------


def test_citation_fields():
    c = Citation(
        chunk_id="c1",
        document_title="SOP-101",
        page_number=2,
        chunk_text_excerpt="Do not exceed pressure limit",
        score=0.88,
        storage_key="doc-abc",
    )
    assert c.document_title == "SOP-101"
    assert c.page_number == 2
    assert c.score == pytest.approx(0.88)


# ---------------------------------------------------------------------------
# Gateway fallback logic unit tests
# ---------------------------------------------------------------------------


def test_chat_use_case_calls_primary_gateway():
    from app.application.chat.chat_use_case import ChatUseCase

    primary = FakeGateway("ollama/llama3.2")
    fallback = FakeGateway("gemini/gemini-2.0-flash")

    embedding_uc = MagicMock()
    embedding_uc.search_semantic = MagicMock(
        return_value=asyncio.coroutine(lambda *a, **kw: [])()
    )

    async def _search(*a, **kw):
        return []

    embedding_uc.search_semantic = _search

    history_repo = MagicMock()
    history_repo.get_history.return_value = []
    history_repo.append_messages.return_value = None

    ctx_builder = MagicMock()
    ctx_builder.build.return_value = ("context text", [])

    prompt_loader = MagicMock()
    prompt_loader.system_prompt.return_value = "You are a copilot."
    prompt_loader.wrap_context.return_value = "=== context ==="

    uc = ChatUseCase(
        embedding_use_case=embedding_uc,
        primary_gateway=primary,
        fallback_gateway=fallback,
        history_repo=history_repo,
        context_builder=ctx_builder,
        prompt_loader=prompt_loader,
    )

    request = ChatRequest(query="What is the pump pressure?", session_id="s1")

    async def _run():
        context = await uc.prepare(request)
        response = await uc.chat(context)
        return response

    response = asyncio.get_event_loop().run_until_complete(_run())

    assert primary.calls == 1
    assert fallback.calls == 0
    assert response.answer == "Answer text."


def test_chat_use_case_falls_back_on_primary_failure():
    from app.application.chat.chat_use_case import ChatUseCase

    primary = FailingGateway()
    fallback = FakeGateway("gemini/gemini-2.0-flash", response="Fallback answer.")

    async def _search(*a, **kw):
        return []

    history_repo = MagicMock()
    history_repo.get_history.return_value = []
    history_repo.append_messages.return_value = None

    ctx_builder = MagicMock()
    ctx_builder.build.return_value = ("ctx", [])

    prompt_loader = MagicMock()
    prompt_loader.system_prompt.return_value = "You are a copilot."
    prompt_loader.wrap_context.return_value = "=== ctx ==="

    embedding_uc = MagicMock()
    embedding_uc.search_semantic = _search

    uc = ChatUseCase(
        embedding_use_case=embedding_uc,
        primary_gateway=primary,
        fallback_gateway=fallback,
        history_repo=history_repo,
        context_builder=ctx_builder,
        prompt_loader=prompt_loader,
    )

    request = ChatRequest(query="Bearing clearance?", session_id="s2")

    async def _run():
        context = await uc.prepare(request)
        # _active_gateway returns primary; but _generate_with_fallback tries both
        return await uc.chat(context)

    response = asyncio.get_event_loop().run_until_complete(_run())

    assert response.answer == "Fallback answer."
    assert fallback.calls == 1


def test_chat_use_case_both_gateways_fail():
    from app.application.chat.chat_use_case import ChatUseCase, GatewayError

    primary = FailingGateway()
    fallback = FailingGateway()

    async def _search(*a, **kw):
        return []

    history_repo = MagicMock()
    history_repo.get_history.return_value = []

    ctx_builder = MagicMock()
    ctx_builder.build.return_value = ("ctx", [])

    prompt_loader = MagicMock()
    prompt_loader.system_prompt.return_value = ""
    prompt_loader.wrap_context.return_value = ""

    embedding_uc = MagicMock()
    embedding_uc.search_semantic = _search

    uc = ChatUseCase(
        embedding_use_case=embedding_uc,
        primary_gateway=primary,
        fallback_gateway=fallback,
        history_repo=history_repo,
        context_builder=ctx_builder,
        prompt_loader=prompt_loader,
    )

    request = ChatRequest(query="What?", session_id="s3")

    async def _run():
        context = await uc.prepare(request)
        return await uc.chat(context)

    with pytest.raises(GatewayError):
        asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Redis history repository unit tests
# ---------------------------------------------------------------------------


def test_redis_history_round_trip():
    from app.infrastructure.chat.redis_history_repository import (
        RedisChatHistoryRepository,
    )

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True

    repo = RedisChatHistoryRepository(lambda: mock_redis)

    messages = [
        ChatMessage(role=MessageRole.USER, content="Hello"),
        ChatMessage(role=MessageRole.ASSISTANT, content="Hi"),
    ]
    repo.append_messages("session-1", messages, 3600)

    call_args = mock_redis.set.call_args
    key_used = call_args.args[0]
    assert key_used == "chat:session:session-1"

    stored_json = call_args.args[1]
    stored = json.loads(stored_json)
    assert len(stored) == 2
    assert stored[0]["role"] == "user"
    assert stored[1]["content"] == "Hi"


def test_redis_history_returns_empty_on_missing():
    from app.infrastructure.chat.redis_history_repository import (
        RedisChatHistoryRepository,
    )

    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    repo = RedisChatHistoryRepository(lambda: mock_redis)
    result = repo.get_history("no-such-session")
    assert result == []


# ---------------------------------------------------------------------------
# Prompt loader unit tests
# ---------------------------------------------------------------------------


def test_prompt_loader_uses_defaults_on_missing_file(tmp_path):
    from app.infrastructure.chat.prompt_loader import YamlPromptLoader, _DEFAULT_SYSTEM

    loader = YamlPromptLoader(tmp_path / "nonexistent.yaml")
    assert loader.system_prompt() == _DEFAULT_SYSTEM
    wrapped = loader.wrap_context("test context")
    assert "test context" in wrapped


def test_prompt_loader_reads_yaml(tmp_path):
    from app.infrastructure.chat.prompt_loader import YamlPromptLoader

    prompt_file = tmp_path / "prompt.yaml"
    prompt_file.write_text(
        "system: 'You are a test copilot.'\n"
        "context_template: '=== {context_blocks} ==='\n",
        encoding="utf-8",
    )
    loader = YamlPromptLoader(prompt_file)
    assert loader.system_prompt() == "You are a test copilot."
    assert loader.wrap_context("my context") == "=== my context ==="
