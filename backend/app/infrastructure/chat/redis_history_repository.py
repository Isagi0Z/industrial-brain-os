from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Callable, List

import redis

from app.domain.chat.interfaces import IChatHistoryRepository
from app.domain.chat.models import ChatMessage, MessageRole

logger = logging.getLogger(__name__)

_KEY_PREFIX = "chat:session:"
_MAX_HISTORY_MESSAGES = 20


class RedisChatHistoryRepository(IChatHistoryRepository):
    def __init__(self, get_redis_fn: Callable[[], redis.Redis]) -> None:
        self._get_redis = get_redis_fn

    def get_history(self, session_id: str) -> List[ChatMessage]:
        try:
            raw = self._get_redis().get(f"{_KEY_PREFIX}{session_id}")
            if raw is None:
                return []
            records: List[dict] = json.loads(raw)
            return [
                ChatMessage(
                    role=MessageRole(r["role"]),
                    content=r["content"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                )
                for r in records
            ]
        except Exception as exc:
            logger.warning(
                "Failed to load chat history",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return []

    def append_messages(
        self,
        session_id: str,
        messages: List[ChatMessage],
        ttl_seconds: int,
    ) -> None:
        try:
            client = self._get_redis()
            key = f"{_KEY_PREFIX}{session_id}"
            existing = self.get_history(session_id)
            combined = existing + messages
            if len(combined) > _MAX_HISTORY_MESSAGES:
                combined = combined[-_MAX_HISTORY_MESSAGES:]
            payload = json.dumps(
                [
                    {
                        "role": m.role.value,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat(),
                    }
                    for m in combined
                ]
            )
            client.set(key, payload, ex=ttl_seconds)
        except Exception as exc:
            logger.warning(
                "Failed to persist chat history",
                extra={"session_id": session_id, "error": str(exc)},
            )

    def clear_session(self, session_id: str) -> None:
        try:
            self._get_redis().delete(f"{_KEY_PREFIX}{session_id}")
        except Exception as exc:
            logger.warning(
                "Failed to clear chat session",
                extra={"session_id": session_id, "error": str(exc)},
            )
