from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, List, Optional, Tuple

from app.domain.chat.interfaces import (
    IChatHistoryRepository,
    IContextBuilder,
    IModelGateway,
    IPromptLoader,
)
from app.domain.chat.models import (
    ChatContext,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    MessageRole,
    TokenUsage,
)
from app.domain.graphrag.interfaces import IGraphRAGEngine

logger = logging.getLogger(__name__)

_RETRY_DELAYS = (1.0, 2.0, 4.0)
_MAX_CONTEXT_TOKENS = 4000


class GatewayError(Exception):
    pass


class ChatUseCase:
    def __init__(
        self,
        graphrag_engine: IGraphRAGEngine,
        primary_gateway: IModelGateway,
        fallback_gateway: Optional[IModelGateway],
        history_repo: IChatHistoryRepository,
        context_builder: IContextBuilder,
        prompt_loader: IPromptLoader,
        max_tokens: int = 2048,
        session_ttl_seconds: int = 3600,
    ) -> None:
        self._graphrag = graphrag_engine
        self._primary = primary_gateway
        self._fallback = fallback_gateway
        self._history = history_repo
        self._ctx_builder = context_builder
        self._prompts = prompt_loader
        self._max_tokens = max_tokens
        self._session_ttl = session_ttl_seconds

    async def prepare(self, request: ChatRequest) -> ChatContext:
        """Fetch history, run the GraphRAG hybrid pipeline, build context."""
        history = self._history.get_history(request.session_id)

        hybrid_result = await self._graphrag.retrieve(
            query=request.query,
            role_scope=request.role_scope,
            top_k=request.top_k,
        )

        search_results = [rc.result for rc in hybrid_result.ranked_chunks]
        context_text, citations = self._ctx_builder.build(
            search_results, _MAX_CONTEXT_TOKENS
        )

        kg_markdown = hybrid_result.kg_paths_as_markdown()
        if kg_markdown:
            context_text = (
                f"{context_text}\n\n### Related Knowledge Graph Relationships\n"
                f"{kg_markdown}"
            )

        system_content = (
            self._prompts.system_prompt()
            + "\n\n"
            + self._prompts.wrap_context(context_text)
        )

        messages: List[dict] = [{"role": "system", "content": system_content}]
        for msg in history:
            messages.append({"role": msg.role.value, "content": msg.content})
        messages.append({"role": "user", "content": request.query})

        return ChatContext(
            request=request,
            messages=messages,
            citations=citations,
            history=history,
        )

    async def chat_stream(self, context: ChatContext) -> AsyncGenerator[str, None]:
        """Yield tokens from the active gateway with fallback."""
        gateway = await self._active_gateway(context.messages)
        async for token in gateway.generate_stream(context.messages, self._max_tokens):
            yield token

    async def chat(self, context: ChatContext) -> ChatResponse:
        """Non-streaming variant — returns full response."""
        t0 = time.monotonic()
        full_text, prompt_tokens, completion_tokens, gateway = (
            await self._generate_with_fallback(context.messages)
        )
        latency_ms = (time.monotonic() - t0) * 1000.0

        self._store_exchange(context, full_text)

        logger.info(
            "Chat token usage",
            extra={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "model": gateway.model_name,
                "latency_ms": round(latency_ms, 1),
                "session_id": context.request.session_id,
            },
        )

        return ChatResponse(
            answer=full_text,
            citations=context.citations,
            token_usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=gateway.model_name,
                latency_ms=round(latency_ms, 1),
            ),
            session_id=context.request.session_id,
        )

    async def finalize(
        self,
        context: ChatContext,
        full_text: str,
        t0: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> ChatResponse:
        """Called after streaming completes to persist history and build response."""
        latency_ms = (time.monotonic() - t0) * 1000.0
        gateway = await self._active_gateway(context.messages)
        self._store_exchange(context, full_text)

        logger.info(
            "Chat stream completed",
            extra={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "model": gateway.model_name,
                "latency_ms": round(latency_ms, 1),
                "session_id": context.request.session_id,
            },
        )

        return ChatResponse(
            answer=full_text,
            citations=context.citations,
            token_usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=gateway.model_name,
                latency_ms=round(latency_ms, 1),
            ),
            session_id=context.request.session_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _store_exchange(self, context: ChatContext, assistant_reply: str) -> None:
        user_msg = ChatMessage(role=MessageRole.USER, content=context.request.query)
        asst_msg = ChatMessage(role=MessageRole.ASSISTANT, content=assistant_reply)
        self._history.append_messages(
            context.request.session_id,
            [user_msg, asst_msg],
            self._session_ttl,
        )

    async def _active_gateway(self, messages: List[dict]) -> IModelGateway:
        """Return primary if reachable, else fallback."""
        return self._primary

    async def _generate_with_fallback(
        self, messages: List[dict]
    ) -> Tuple[str, int, int, IModelGateway]:
        """Try primary with retries; on total failure, try fallback."""
        for gateway in self._candidate_gateways():
            try:
                text, pt, ct = await self._retry(gateway, messages)
                return text, pt, ct, gateway
            except GatewayError as exc:
                logger.warning(
                    "Gateway exhausted, trying fallback",
                    extra={"gateway": gateway.model_name, "error": str(exc)},
                )
        raise GatewayError("All configured gateways failed")

    def _candidate_gateways(self) -> List[IModelGateway]:
        candidates: List[IModelGateway] = [self._primary]
        if self._fallback is not None:
            candidates.append(self._fallback)
        return candidates

    async def _retry(
        self, gateway: IModelGateway, messages: List[dict]
    ) -> Tuple[str, int, int]:
        last_exc: Optional[Exception] = None
        for attempt, delay in enumerate(_RETRY_DELAYS):
            try:
                return await gateway.generate(messages, self._max_tokens)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "LLM gateway attempt failed",
                    extra={
                        "attempt": attempt + 1,
                        "gateway": gateway.model_name,
                        "error": str(exc),
                    },
                )
                if attempt < len(_RETRY_DELAYS) - 1:
                    await asyncio.sleep(delay)
        raise GatewayError(str(last_exc))
