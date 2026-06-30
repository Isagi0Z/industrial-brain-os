from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Tuple

from app.domain.chat.models import ChatMessage, Citation
from app.domain.search.models import SearchResult


class IModelGateway(ABC):
    @abstractmethod
    async def generate_stream(
        self, messages: List[dict], max_tokens: int
    ) -> AsyncGenerator[str, None]:
        """Yield tokens one by one as they are generated."""

    @abstractmethod
    async def generate(
        self, messages: List[dict], max_tokens: int
    ) -> Tuple[str, int, int]:
        """Return (full_text, prompt_tokens, completion_tokens)."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...


class IChatHistoryRepository(ABC):
    @abstractmethod
    def get_history(self, session_id: str) -> List[ChatMessage]: ...

    @abstractmethod
    def append_messages(
        self,
        session_id: str,
        messages: List[ChatMessage],
        ttl_seconds: int,
    ) -> None: ...

    @abstractmethod
    def clear_session(self, session_id: str) -> None: ...


class IContextBuilder(ABC):
    @abstractmethod
    def build(
        self,
        results: List[SearchResult],
        max_context_tokens: int,
    ) -> Tuple[str, List[Citation]]:
        """Return (formatted_context_text, citations)."""


class IPromptLoader(ABC):
    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def wrap_context(self, context_text: str) -> str: ...
