"""Proactive warning detector (M13).

Embeds the incoming query, searches the `lessons_learned` Qdrant collection
(role-scoped per ADR-005), and — above the configured similarity threshold —
resolves the matching Qdrant point id (the lesson_id) back to its canonical
Neo4j record so the warning carries the real incident_date/summary rather
than a denormalized copy.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.domain.chat.models import ProactiveWarning
from app.domain.lessons_brain.interfaces import (
    ILessonRepository,
    IProactiveWarningDetector,
)
from app.domain.search.interfaces import IEmbeddingService, IVectorRepository

logger = logging.getLogger(__name__)

LESSONS_LEARNED_COLLECTION = "lessons_learned"
DEFAULT_SIMILARITY_THRESHOLD = 0.85


class ProactiveWarningDetector(IProactiveWarningDetector):
    def __init__(
        self,
        embedding_service: IEmbeddingService,
        vector_repo: IVectorRepository,
        lesson_repo: ILessonRepository,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        self._embedding_service = embedding_service
        self._vector_repo = vector_repo
        self._lesson_repo = lesson_repo
        self._threshold = similarity_threshold

    def detect(self, query: str, role_scope: str) -> Optional[ProactiveWarning]:
        if not query or not query.strip():
            return None
        try:
            vector = self._embedding_service.embed_one(query)
            hits = self._vector_repo.search(
                LESSONS_LEARNED_COLLECTION, vector, role_scope, limit=1
            )
        except Exception as exc:
            logger.warning("Proactive warning detection failed: %s", exc)
            return None

        if not hits or hits[0].score <= self._threshold:
            return None

        top = hits[0]
        lesson = self._lesson_repo.get(top.chunk_id)  # chunk_id == lesson_id
        if lesson is None:
            return None

        return ProactiveWarning(
            warning_type="LESSONS_LEARNED",
            lesson_summary=lesson.summary or lesson.description,
            similarity_score=round(top.score, 4),
            incident_date=lesson.incident_date.isoformat(),
            asset_tag=lesson.asset_tag,
            lesson_id=lesson.lesson_id,
        )
