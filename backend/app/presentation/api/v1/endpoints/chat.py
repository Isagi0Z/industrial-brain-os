from __future__ import annotations

import json
import logging
import time
from typing import Annotated, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
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


def _verify_access_token(token: Optional[str]) -> Optional[dict]:
    """Return the decoded payload for a VALID ACCESS token, else None.

    ``verify_token`` raises ``ValueError`` on invalid/expired/revoked tokens (it
    never returns None) and does not distinguish token type, so we must both
    catch the error and reject non-access tokens (e.g. a refresh token supplied
    here must not authenticate)."""
    if not token:
        return None
    token_service = container.get_token_service()
    try:
        payload = token_service.verify_token(token)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("type") != "access":
        return None
    return payload


def _get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> str:
    payload = _verify_access_token(credentials.credentials)
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
    token: Optional[str] = Query(
        default=None, description="Deprecated fallback; prefer the ib-bearer subprotocol"
    ),
) -> None:
    # Auth: prefer the JWT carried in the WebSocket subprotocol header
    # (`new WebSocket(url, ['ib-bearer', <access_token>])`) so the token never
    # lands in the URL/query string — which is written verbatim to access logs,
    # browser history and Referer headers. A query-string token is accepted only
    # as a backward-compatible fallback. Only ACCESS tokens are honoured.
    subproto_token: Optional[str] = None
    offered = websocket.headers.get("sec-websocket-protocol", "")
    parts = [p.strip() for p in offered.split(",") if p.strip()]
    if len(parts) >= 2 and parts[0] == "ib-bearer":
        subproto_token = parts[1]

    payload = _verify_access_token(subproto_token or token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Echo the negotiated subprotocol back only when the client actually offered
    # it, otherwise the browser rejects the handshake.
    await websocket.accept(subprotocol="ib-bearer" if subproto_token else None)
    ws_connection_opened()
    use_case = _get_use_case()

    try:
        # Persistent connection: one accepted socket serves the whole
        # conversation. Loop reading queries until the client disconnects, so a
        # follow-up question does not pay a fresh connect + JWT verification and
        # the client never sees the socket drop between turns.
        while True:
            raw = await websocket.receive_text()  # WebSocketDisconnect on close
            try:
                data = json.loads(raw)
            except Exception:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Invalid request JSON"})
                )
                continue

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
                continue

            await _stream_one_answer(websocket, use_case, request)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 - never let a socket crash the worker
        logger.error("Chat stream fatal error", extra={"error": str(exc)})
    finally:
        # Close only when the conversation ends (disconnect / teardown), never
        # after an individual answer.
        try:
            await websocket.close()
        except RuntimeError:
            pass  # already closed by the peer
        ws_connection_closed()


async def _stream_one_answer(
    websocket: WebSocket, use_case: ChatUseCase, request: ChatRequest
) -> None:
    """Run a single retrieve -> stream -> finalize turn. A per-turn failure emits
    an {type:error} frame but keeps the socket open for the next question; only a
    client disconnect propagates to end the conversation."""
    t0 = time.monotonic()
    full_text = ""
    try:
        context = await use_case.prepare(request)

        async for token_chunk in use_case.chat_stream(context):
            full_text += token_chunk
            await websocket.send_text(
                json.dumps({"type": "token", "content": token_chunk})
            )

        response = await use_case.finalize(context, full_text, t0, 0, 0)

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
    except WebSocketDisconnect:
        raise
    except Exception as exc:  # noqa: BLE001 - isolate a turn failure from the loop
        logger.error(
            "Chat turn error",
            extra={"session_id": request.session_id, "error": str(exc)},
        )
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "LLM gateway unavailable"})
            )
        except Exception:
            # Cannot even send the error -> the peer is gone; end the loop.
            raise WebSocketDisconnect()
