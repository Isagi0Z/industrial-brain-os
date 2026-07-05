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
    # M14 Stage 8 — absolute source coordinates for citation validation.
    bbox_json: Optional[dict] = None


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
    # Populated by chat_stream() so finalize() reports the gateway/model that
    # actually produced the streamed answer (may be the fallback) and the real
    # token counts from the streaming provider rather than zeros.
    stream_model: Optional[str] = None
    stream_prompt_tokens: int = 0
    stream_completion_tokens: int = 0


@dataclass
class ValidatedSource:
    """A single validated citation with its absolute source coordinates
    (M14 Stage 8). ``source_index`` is the 1-based ``[source_N]`` marker the
    LLM emitted; the rest maps back to the retrieved chunk record."""

    source_index: int
    chunk_id: str
    document_id: str
    document_title: str
    page_number: Optional[int]
    bbox_json: Optional[dict] = None


@dataclass
class CitationValidationReport:
    """Stage 8 output (M14) — appended to every /chat response.

    quality_flag is ``"CITATION_WARNING"`` when the LLM cited one or more
    ``[source_N]`` markers that do not resolve to a retrieved chunk
    (hallucinated), else ``"OK"``.
    """

    validated_count: int
    hallucinated_count: int
    quality_flag: str
    validated_sources: List[ValidatedSource] = field(default_factory=list)


@dataclass
class ChatResponse:
    answer: str
    citations: List[Citation]
    token_usage: TokenUsage
    session_id: str
    # M14 Stage 8 — citation validation report + overall quality flag.
    citation_validation: Optional[CitationValidationReport] = None
    response_quality_flag: str = "OK"


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
