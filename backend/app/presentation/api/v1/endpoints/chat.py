from __future__ import annotations

import json
import logging
import time
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.application.chat.chat_use_case import ChatUseCase
from app.domain.chat.models import ChatRequest
from app.infrastructure.di.container import container
from app.infrastructure.observability.metrics import (
    ws_connection_closed,
    ws_connection_opened,
)

router = APIRouter(prefix="/chat", tags=["Chat Copilot"])
logger = logging.getLogger(__name__)
_bearer = HTTPBearer()


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class ChatRequestBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1, max_length=128)
    top_k: int = Field(default=5, ge=1, le=20)
    role_scope: str = Field(default="public")


class CitationOut(BaseModel):
    chunk_id: str
    document_title: str
    page_number: Optional[int]
    chunk_text_excerpt: str
    score: float
    storage_key: Optional[str]


class TokenUsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    model: str
    latency_ms: float


class ValidatedSourceOut(BaseModel):
    source_index: int
    chunk_id: str
    document_id: str
    document_title: str
    page_number: Optional[int]
    bbox_json: Optional[dict]


class CitationValidationOut(BaseModel):
    validated_count: int
    hallucinated_count: int
    quality_flag: str
    validated_sources: List[ValidatedSourceOut]


class ChatResponseBody(BaseModel):
    answer: str
    citations: List[CitationOut]
    token_usage: TokenUsageOut
    session_id: str
    citation_validation: Optional[CitationValidationOut] = None
    response_quality_flag: str = "OK"


# ------------------------------------------------------------------
# Auth helper
# ------------------------------------------------------------------


def _get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> str:
    token_service = container.get_token_service()
    payload = token_service.verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return str(payload.get("sub", ""))


def _get_use_case() -> ChatUseCase:
    return container.get_chat_use_case()


def _validation_out(report) -> Optional[CitationValidationOut]:
    if report is None:
        return None
    return CitationValidationOut(
        validated_count=report.validated_count,
        hallucinated_count=report.hallucinated_count,
        quality_flag=report.quality_flag,
        validated_sources=[
            ValidatedSourceOut(
                source_index=s.source_index,
                chunk_id=s.chunk_id,
                document_id=s.document_id,
                document_title=s.document_title,
                page_number=s.page_number,
                bbox_json=s.bbox_json,
            )
            for s in report.validated_sources
        ],
    )


def _validation_dict(report) -> Optional[dict]:
    out = _validation_out(report)
    return out.model_dump() if out is not None else None


# ------------------------------------------------------------------
# POST /api/v1/chat  (non-streaming)
# ------------------------------------------------------------------


@router.post("", response_model=ChatResponseBody)
async def chat(
    body: ChatRequestBody,
    current_user: Annotated[str, Depends(_get_current_user)],
) -> ChatResponseBody:
    use_case = _get_use_case()
    request = ChatRequest(
        query=body.query,
        session_id=body.session_id,
        top_k=body.top_k,
        role_scope=body.role_scope,
    )
    context = await use_case.prepare(request)
    response = await use_case.chat(context)

    return ChatResponseBody(
        answer=response.answer,
        citations=[
            CitationOut(
                chunk_id=c.chunk_id,
                document_title=c.document_title,
                page_number=c.page_number,
                chunk_text_excerpt=c.chunk_text_excerpt,
                score=c.score,
                storage_key=c.storage_key,
            )
            for c in response.citations
        ],
        token_usage=TokenUsageOut(
            prompt_tokens=response.token_usage.prompt_tokens,
            completion_tokens=response.token_usage.completion_tokens,
            model=response.token_usage.model,
            latency_ms=response.token_usage.latency_ms,
        ),
        session_id=response.session_id,
        citation_validation=_validation_out(response.citation_validation),
        response_quality_flag=response.response_quality_flag,
    )


# ------------------------------------------------------------------
# WS /api/v1/chat/stream  (streaming)
# ------------------------------------------------------------------


@router.websocket("/stream")
async def chat_stream(
    websocket: WebSocket,
    token: str = Query(..., description="JWT bearer token"),
) -> None:
    token_service = container.get_token_service()
    payload = token_service.verify_token(token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    ws_connection_opened()
    use_case = _get_use_case()

    try:
        raw = await websocket.receive_text()
        data = json.loads(raw)
    except Exception:
        await websocket.send_text(
            json.dumps({"type": "error", "message": "Invalid request JSON"})
        )
        await websocket.close()
        ws_connection_closed()
        return

    request = ChatRequest(
        query=data.get("query", ""),
        session_id=data.get("session_id", "default"),
        top_k=int(data.get("top_k", 5)),
        role_scope=data.get("role_scope", "public"),
    )

    if not request.query.strip():
        await websocket.send_text(
            json.dumps({"type": "error", "message": "query must not be empty"})
        )
        await websocket.close()
        ws_connection_closed()
        return

    t0 = time.monotonic()
    full_text = ""
    prompt_tokens = 0
    completion_tokens = 0

    try:
        context = await use_case.prepare(request)

        async for token_chunk in use_case.chat_stream(context):
            full_text += token_chunk
            await websocket.send_text(
                json.dumps({"type": "token", "content": token_chunk})
            )

        response = await use_case.finalize(
            context, full_text, t0, prompt_tokens, completion_tokens
        )

        await websocket.send_text(
            json.dumps(
                {
                    "type": "done",
                    "answer": response.answer,
                    "citations": [
                        {
                            "chunk_id": c.chunk_id,
                            "document_title": c.document_title,
                            "page_number": c.page_number,
                            "chunk_text_excerpt": c.chunk_text_excerpt,
                            "score": c.score,
                            "storage_key": c.storage_key,
                        }
                        for c in response.citations
                    ],
                    "token_usage": {
                        "prompt_tokens": response.token_usage.prompt_tokens,
                        "completion_tokens": response.token_usage.completion_tokens,
                        "model": response.token_usage.model,
                        "latency_ms": response.token_usage.latency_ms,
                    },
                    "session_id": response.session_id,
                    "citation_validation": _validation_dict(
                        response.citation_validation
                    ),
                    "response_quality_flag": response.response_quality_flag,
                }
            )
        )

    except Exception as exc:
        logger.error(
            "Chat stream error",
            extra={"session_id": request.session_id, "error": str(exc)},
        )
        await websocket.send_text(
            json.dumps({"type": "error", "message": "LLM gateway unavailable"})
        )
    finally:
        await websocket.close()
        ws_connection_closed()
