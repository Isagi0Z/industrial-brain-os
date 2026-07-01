"""Neo4j-backed failure history repository (M10).

Queries the (Equipment)-[:EXHIBITS]->(FailureMode) edge defined in the
industrial ontology (M6/M7, ADR-010).
"""

from __future__ import annotations

import logging
from typing import List

from neo4j import Driver

from app.domain.maintenance_brain.interfaces import IFailureHistoryRepository
from app.domain.maintenance_brain.models import FailureRecord

logger = logging.getLogger(__name__)

_EXHIBITS_QUERY = """
MATCH (e:Equipment {tag_number: $tag})-[:EXHIBITS]->(f:FailureMode)
RETURN f.failure_code AS failure_code,
       f.description AS description,
       f.severity AS severity,
       f.typical_cause AS typical_cause
"""


class Neo4jFailureHistoryRepository(IFailureHistoryRepository):
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def search_by_asset_tag(self, asset_tag: str) -> List[FailureRecord]:
        try:
            with self._driver.session() as session:
                records = session.run(_EXHIBITS_QUERY, tag=asset_tag)
                return [
                    FailureRecord(
                        failure_code=r["failure_code"],
                        description=r["description"],
                        severity=r["severity"],
                        typical_cause=r["typical_cause"],
                    )
                    for r in records
                    if r["failure_code"]
                ]
        except Exception as exc:
            logger.warning(
                "Failure history search failed for asset_tag=%s: %s", asset_tag, exc
            )
            return []
