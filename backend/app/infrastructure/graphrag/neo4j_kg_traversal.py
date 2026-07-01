"""Neo4j KG traversal service (Stage 4 of the 8-stage hybrid retrieval pipeline).

Uses APOC's apoc.path.subgraphAll for bounded-depth traversal from each
extracted entity tag. Depth is hardcoded by the caller (ADR-004 mitigation —
Neo4j Community is single-node, so unbounded traversals on a large graph are
a performance risk).
"""

from __future__ import annotations

import logging
from typing import List, Set, Tuple

from neo4j import Driver

from app.domain.graphrag.interfaces import IKGTraversalService
from app.domain.graphrag.models import KGPath

logger = logging.getLogger(__name__)

_TRAVERSAL_QUERY = """
MATCH (n {tag_number: $tag})
CALL apoc.path.subgraphAll(n, {maxLevel: $max_level, limit: $limit})
YIELD relationships
UNWIND relationships AS rel
RETURN
    startNode(rel).tag_number AS source_tag,
    labels(startNode(rel))[0] AS source_type,
    type(rel) AS relation_type,
    endNode(rel).tag_number AS target_tag,
    labels(endNode(rel))[0] AS target_type
"""


class Neo4jKGTraversalService(IKGTraversalService):
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def traverse(self, tags: List[str], max_depth: int, limit: int) -> List[KGPath]:
        paths: List[KGPath] = []
        seen: Set[Tuple[str, str, str]] = set()

        with self._driver.session() as session:
            for tag in tags:
                try:
                    records = session.run(
                        _TRAVERSAL_QUERY, tag=tag, max_level=max_depth, limit=limit
                    )
                    for record in records:
                        source_tag = record["source_tag"]
                        target_tag = record["target_tag"]
                        if not source_tag or not target_tag:
                            continue
                        relation_type = record["relation_type"]
                        key = (source_tag, relation_type, target_tag)
                        if key in seen:
                            continue
                        seen.add(key)
                        paths.append(
                            KGPath(
                                source_tag=source_tag,
                                source_type=record["source_type"] or "Unknown",
                                relation_type=relation_type,
                                target_tag=target_tag,
                                target_type=record["target_type"] or "Unknown",
                            )
                        )
                except Exception as exc:
                    logger.warning(
                        "KG traversal failed for tag=%s: %s — skipping.", tag, exc
                    )
        return paths
