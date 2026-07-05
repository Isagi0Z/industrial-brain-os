from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, List, Optional, Tuple

from app.application.chat.citation_validation import validate_citations
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
    Citation,
    MessageRole,
    TokenUsage,
)
from app.domain.graphrag.interfaces import IGraphRAGEngine
from app.domain.graphrag.models import RankedChunk

logger = logging.getLogger(__name__)

_RETRY_DELAYS = (1.0, 2.0, 4.0)
_MAX_CONTEXT_TOKENS = 4000


class GatewayError(Exception):
    pass


def _citations_from_ranked(ranked_chunks: List[RankedChunk]) -> List[Citation]:
    """Derive ordered citations from reranked chunks so citation index N
    matches the ``[source_N]`` marker assigned during context assembly.
    Carries the absolute source coordinates (bbox_json) for Stage 8."""
    citations: List[Citation] = []
    for rc in ranked_chunks:
        r = rc.result
        citations.append(
            Citation(
                chunk_id=r.chunk_id,
                document_title=r.document_title,
                page_number=r.page_number,
                chunk_text_excerpt=r.text[:200],
                score=round(r.score, 4),
                storage_key=r.document_id,
                bbox_json=r.bbox_json,
            )
        )
    return citations


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

        if hybrid_result.compression is not None:
            # Stage 7 (M14) ran — feed the compressed, source-numbered context
            # to the LLM and derive citations in the matching [source_N] order.
            context_text = hybrid_result.compressed_context
            citations = _citations_from_ranked(hybrid_result.ranked_chunks)
        else:
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
        """Yield tokens, transparently falling back to the next configured
        gateway when one fails BEFORE emitting any token. Once streaming has
        begun we never switch gateways (that would duplicate already-shown text).
        Records the gateway/model actually used and its token counts on the
        context for finalize()."""
        usage: dict = {}
        last_exc: Optional[Exception] = None
        for gateway in self._candidate_gateways():
            yielded = False
            try:
                async for token in gateway.generate_stream(
                    context.messages, self._max_tokens, usage
                ):
                    yielded = True
                    yield token
                context.stream_model = gateway.model_name
                context.stream_prompt_tokens = int(usage.get("prompt_tokens", 0))
                context.stream_completion_tokens = int(
                    usage.get("completion_tokens", 0)
                )
                return
            except Exception as exc:  # noqa: BLE001 - try the next gateway
                last_exc = exc
                if yielded:
                    # Already streamed partial output — surface the failure rather
                    # than restart on another gateway and duplicate text.
                    context.stream_model = gateway.model_name
                    raise
                logger.warning(
                    "Streaming gateway failed before first token; trying fallback",
                    extra={"gateway": gateway.model_name, "error": str(exc)},
                )
        if last_exc is not None:
            raise last_exc

    async def chat(self, context: ChatContext) -> ChatResponse:
        """Non-streaming variant — returns full response."""
        t0 = time.monotonic()
        full_text, prompt_tokens, completion_tokens, gateway = (
            await self._generate_with_fallback(context.messages)
        )
        latency_ms = (time.monotonic() - t0) * 1000.0

        # Stage 8 (M14) — validate [source_N] citations in the answer.
        cleaned_text, validation = validate_citations(full_text, context.citations)
        self._store_exchange(context, cleaned_text)

        logger.info(
            "Chat token usage",
            extra={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "model": gateway.model_name,
                "latency_ms": round(latency_ms, 1),
                "session_id": context.request.session_id,
                "validated_citations": validation.validated_count,
                "hallucinated_citations": validation.hallucinated_count,
                "quality_flag": validation.quality_flag,
            },
        )

        return ChatResponse(
            answer=cleaned_text,
            citations=context.citations,
            token_usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=gateway.model_name,
                latency_ms=round(latency_ms, 1),
            ),
            session_id=context.request.session_id,
            citation_validation=validation,
            response_quality_flag=validation.quality_flag,
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
        # Prefer the gateway/model + token counts recorded by chat_stream (the
        # one that actually produced the answer, which may be the fallback);
        # fall back to the primary's name only if streaming never ran.
        model_name = context.stream_model or self._primary.model_name
        prompt_tokens = prompt_tokens or context.stream_prompt_tokens
        completion_tokens = completion_tokens or context.stream_completion_tokens

        # Stage 8 (M14) — validate [source_N] citations in the streamed answer.
        cleaned_text, validation = validate_citations(full_text, context.citations)
        self._store_exchange(context, cleaned_text)

        logger.info(
            "Chat stream completed",
            extra={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "model": model_name,
                "latency_ms": round(latency_ms, 1),
                "session_id": context.request.session_id,
                "validated_citations": validation.validated_count,
                "hallucinated_citations": validation.hallucinated_count,
                "quality_flag": validation.quality_flag,
            },
        )

        return ChatResponse(
            answer=cleaned_text,
            citations=context.citations,
            token_usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=model_name,
                latency_ms=round(latency_ms, 1),
            ),
            session_id=context.request.session_id,
            citation_validation=validation,
            response_quality_flag=validation.quality_flag,
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
