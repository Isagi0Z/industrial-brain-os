"""Neo4j-backed Lessons Learned repository (M13).

Writes the `LessonLearned` node and its ontology-defined edges:
    (LessonLearned)-[:RELATED_TO]->(Equipment)
    (LessonLearned)-[:REFERENCES]->(FailureMode)

Both edges are created with MATCH (not MERGE) against the target node —
Equipment/FailureMode require ontology properties (`equipment_class`,
`failure_code`/`description`) that an incident report does not supply, so
we link only to nodes that already exist rather than creating incomplete
ones (same graceful-degradation approach as M12's incident_history_repository:
a missing match is logged and skipped, not an error).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from neo4j import Driver

from app.domain.lessons_brain.interfaces import ILessonRepository
from app.domain.lessons_brain.models import LessonLearned, LessonLinkResult

logger = logging.getLogger(__name__)

_MERGE_LESSON = """
MERGE (l:LessonLearned {lesson_id: $lesson_id})
SET l.asset_tag = $asset_tag,
    l.incident_date = $incident_date,
    l.description = $description,
    l.root_cause = $root_cause,
    l.corrective_actions = $corrective_actions,
    l.severity = $severity,
    l.role_scope = $role_scope,
    l.summary = coalesce(l.summary, "")
"""

_MATCH_EQUIPMENT_RELATE = """
MATCH (l:LessonLearned {lesson_id: $lesson_id})
MATCH (e:Equipment {tag_number: $asset_tag})
MERGE (l)-[:RELATED_TO]->(e)
"""

_MATCH_FAILURE_MODE_REFERENCE = """
MATCH (l:LessonLearned {lesson_id: $lesson_id})
MATCH (f:FailureMode {failure_code: $failure_code})
MERGE (l)-[:REFERENCES]->(f)
"""

_GET_LESSON = """
MATCH (l:LessonLearned {lesson_id: $lesson_id})
RETURN l.lesson_id AS lesson_id,
       l.asset_tag AS asset_tag,
       l.incident_date AS incident_date,
       l.description AS description,
       l.root_cause AS root_cause,
       l.corrective_actions AS corrective_actions,
       l.severity AS severity,
       l.role_scope AS role_scope,
       l.summary AS summary
"""


class Neo4jLessonRepository(ILessonRepository):
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def create(
        self,
        lesson: LessonLearned,
        candidate_failure_codes: List[str],
    ) -> LessonLinkResult:
        equipment_linked = False
        failure_modes_linked: List[str] = []

        with self._driver.session() as session:
            session.run(
                _MERGE_LESSON,
                lesson_id=lesson.lesson_id,
                asset_tag=lesson.asset_tag,
                incident_date=lesson.incident_date.isoformat(),
                description=lesson.description,
                root_cause=lesson.root_cause,
                corrective_actions=lesson.corrective_actions,
                severity=lesson.severity,
                role_scope=lesson.role_scope,
            )

            try:
                summary = session.run(
                    _MATCH_EQUIPMENT_RELATE,
                    lesson_id=lesson.lesson_id,
                    asset_tag=lesson.asset_tag,
                ).consume()
                equipment_linked = summary.counters.relationships_created > 0
            except Exception as exc:
                logger.debug(
                    "LessonLearned RELATED_TO Equipment skipped (asset_tag=%s): %s",
                    lesson.asset_tag,
                    exc,
                )

            for code in candidate_failure_codes:
                try:
                    summary = session.run(
                        _MATCH_FAILURE_MODE_REFERENCE,
                        lesson_id=lesson.lesson_id,
                        failure_code=code,
                    ).consume()
                    if summary.counters.relationships_created > 0:
                        failure_modes_linked.append(code)
                except Exception as exc:
                    logger.debug(
                        "LessonLearned REFERENCES FailureMode skipped (code=%s): %s",
                        code,
                        exc,
                    )

        logger.info(
            "Lesson stored",
            extra={
                "lesson_id": lesson.lesson_id,
                "asset_tag": lesson.asset_tag,
                "equipment_linked": equipment_linked,
                "failure_modes_linked": len(failure_modes_linked),
            },
        )
        return LessonLinkResult(
            equipment_linked=equipment_linked,
            failure_modes_linked=failure_modes_linked,
        )

    def update_summary(self, lesson_id: str, summary: str) -> None:
        with self._driver.session() as session:
            session.run(
                "MATCH (l:LessonLearned {lesson_id: $lesson_id}) SET l.summary = $summary",
                lesson_id=lesson_id,
                summary=summary,
            )

    def get(self, lesson_id: str) -> Optional[LessonLearned]:
        with self._driver.session() as session:
            record = session.run(_GET_LESSON, lesson_id=lesson_id).single()
        if record is None:
            return None
        return LessonLearned(
            lesson_id=record["lesson_id"],
            asset_tag=record["asset_tag"],
            incident_date=date.fromisoformat(record["incident_date"]),
            description=record["description"],
            root_cause=record["root_cause"] or "",
            corrective_actions=list(record["corrective_actions"] or []),
            severity=record["severity"] or "MEDIUM",
            role_scope=record["role_scope"] or "public",
            summary=record["summary"] or "",
        )
