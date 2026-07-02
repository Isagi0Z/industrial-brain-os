from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Citation:
    chunk_id: str
    document_title: str
    page_number: Optional[int]
    chunk_text_excerpt: str
    score: float
    storage_key: Optional[str] = None


@dataclass
class ChatMessage:
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    model: str
    latency_ms: float


@dataclass
class ChatRequest:
    query: str
    session_id: str
    top_k: int = 5
    role_scope: str = "public"


@dataclass
class ChatContext:
    """Prepared context passed from prepare() to chat_stream() to finalize()."""

    request: ChatRequest
    messages: List[dict]
    citations: List[Citation]
    history: List[ChatMessage]
    prepared_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ChatResponse:
    answer: str
    citations: List[Citation]
    token_usage: TokenUsage
    session_id: str


@dataclass
class ProactiveWarning:
    """Lessons Learned Brain (M13) knowledge-cliff warning, injected into
    another sub-brain's response when the query resembles a past incident
    above the similarity threshold (ADR-007 cross-agent tool reuse)."""

    warning_type: str
    lesson_summary: str
    similarity_score: float
    incident_date: str
    asset_tag: str
    lesson_id: str
