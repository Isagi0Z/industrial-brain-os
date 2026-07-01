"""Redis-backed live RCA session-state store (M12).

Holds the transient in-progress 5-Whys working state keyed by session_id so
a subsequent HTTP request can resume the analysis without the service
holding it in process memory (Engineering Bible §28 — stateless services).

This is the "Redis-backed store enabling resume after human input" the M12
checklist calls for. LangGraph's own checkpointer is not used for cross-
request durability: the official `langgraph-checkpoint-redis` requires the
RedisJSON module, which the plain `redis:7.2-alpine` deployment does not
provide — see docs/verification/m12_verification.md. The LangGraph graph
itself still configures `interrupt_before` at the human-confirm node
(compiled with an in-process MemorySaver) to model the pause point.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

import redis

from app.domain.rca_brain.interfaces import IRCASessionStateStore
from app.domain.rca_brain.models import RCASession
from app.infrastructure.rca.serialization import session_from_dict, session_to_dict

logger = logging.getLogger(__name__)

_KEY_PREFIX = "rca:session:"


class RedisRCAStateStore(IRCASessionStateStore):
    def __init__(self, get_redis_fn: Callable[[], redis.Redis]) -> None:
        self._get_redis = get_redis_fn

    def save(self, session: RCASession, ttl_seconds: int) -> None:
        try:
            payload = json.dumps(session_to_dict(session))
            self._get_redis().set(
                f"{_KEY_PREFIX}{session.session_id}", payload, ex=ttl_seconds
            )
        except Exception as exc:
            logger.warning(
                "RCA state save failed",
                extra={"session_id": session.session_id, "error": str(exc)},
            )

    def load(self, session_id: str) -> Optional[RCASession]:
        try:
            raw = self._get_redis().get(f"{_KEY_PREFIX}{session_id}")
            if raw is None:
                return None
            return session_from_dict(json.loads(raw))  # type: ignore[arg-type]
        except Exception as exc:
            logger.warning(
                "RCA state load failed",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return None

    def delete(self, session_id: str) -> None:
        try:
            self._get_redis().delete(f"{_KEY_PREFIX}{session_id}")
        except Exception as exc:
            logger.warning(
                "RCA state delete failed",
                extra={"session_id": session_id, "error": str(exc)},
            )
