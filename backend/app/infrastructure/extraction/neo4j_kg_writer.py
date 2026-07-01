"""Neo4j Knowledge Graph writer.

Writes ExtractionResult and DocumentExtractionReport to Neo4j using idempotent
MERGE statements.

Entity MERGE key: tag_number (unique constraint enforced by infra_init.py).
Relation MERGE key: (source tag, relation type, target tag) triple.

HAS_CHUNK relationship:
  (Document {source_id}) -[:HAS_CHUNK]-> (DocumentChunk {chunk_id})
MENTIONS relationship:
  (DocumentChunk {chunk_id}) -[:MENTIONS]-> (entity {tag_number})

Neo4j constraint violations on entity MERGE are caught and logged — they signal
a pre-existing node with conflicting properties, which is treated as a
successful deduplication rather than an error.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from neo4j import Driver

from app.domain.extraction.interfaces import IKGWriter
from app.domain.extraction.models import (
    DocumentExtractionReport,
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)

logger = logging.getLogger(__name__)


class Neo4jKGWriter(IKGWriter):
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    # ------------------------------------------------------------------
    # IKGWriter
    # ------------------------------------------------------------------

    def write_result(self, result: ExtractionResult) -> None:
        if not result.entities:
            return

        with self._driver.session() as session:
            entity_tags: List[str] = []
            for entity in result.entities:
                if not entity.tag_number:
                    continue
                try:
                    session.execute_write(_merge_entity, entity)
                    entity_tags.append(entity.tag_number)
                except Exception as exc:
                    logger.warning(
                        "Entity MERGE failed (tag=%s type=%s): %s",
                        entity.tag_number,
                        entity.entity_type,
                        exc,
                    )

            if entity_tags:
                try:
                    session.execute_write(
                        _merge_has_chunk,
                        result.document_id,
                        result.chunk_id,
                        entity_tags,
                    )
                except Exception as exc:
                    logger.warning(
                        "HAS_CHUNK MERGE failed (doc=%s chunk=%s): %s",
                        result.document_id,
                        result.chunk_id,
                        exc,
                    )

            for relation in result.relations:
                try:
                    session.execute_write(_merge_relation, relation)
                except Exception as exc:
                    logger.warning(
                        "Relation MERGE failed (%s-[%s]->%s): %s",
                        relation.source_tag,
                        relation.relation_type,
                        relation.target_tag,
                        exc,
                    )

        logger.debug(
            "KG write: chunk=%s entities=%d relations=%d",
            result.chunk_id,
            len(result.entities),
            len(result.relations),
        )

    def write_report(self, report: DocumentExtractionReport) -> None:
        """Log the extraction report — no Neo4j write needed at this milestone."""
        logger.info(
            "Extraction report: document=%s job=%s "
            "chunks_processed=%d chunks_failed=%d "
            "entities=%d relations=%d success_rate=%.1f%%",
            report.document_id,
            report.job_id,
            report.chunks_processed,
            report.chunks_failed,
            report.total_entities,
            report.total_relations,
            report.success_rate * 100,
        )


# ---------------------------------------------------------------------------
# Transaction functions
# ---------------------------------------------------------------------------


def _merge_entity(tx, entity: ExtractedEntity) -> None:
    label = entity.entity_type
    props: Dict[str, Any] = {"tag_number": entity.tag_number, "name": entity.text}
    if entity.manufacturer:
        props["manufacturer"] = entity.manufacturer
    if entity.model_number:
        props["model_number"] = entity.model_number
    props.update(entity.properties)

    tx.run(
        f"MERGE (n:{label} {{tag_number: $tag}}) SET n += $props",
        tag=entity.tag_number,
        props=props,
    )


def _merge_has_chunk(
    tx, document_id: str, chunk_id: str, entity_tags: List[str]
) -> None:
    tx.run(
        "MERGE (d:Document {source_id: $doc_id})"
        " MERGE (c:DocumentChunk {chunk_id: $chunk_id})"
        " ON CREATE SET c.document_id = $doc_id"
        " MERGE (d)-[:HAS_CHUNK]->(c)",
        doc_id=document_id,
        chunk_id=chunk_id,
    )
    for tag in entity_tags:
        tx.run(
            "MATCH (c:DocumentChunk {chunk_id: $chunk_id})"
            " MATCH (e {tag_number: $tag})"
            " MERGE (c)-[:MENTIONS]->(e)",
            chunk_id=chunk_id,
            tag=tag,
        )


def _merge_relation(tx, relation: ExtractedRelation) -> None:
    rel_props: Dict[str, Any] = {"confidence": relation.confidence}
    rel_props.update(relation.properties)

    tx.run(
        f"MATCH (s:{relation.source_type} {{tag_number: $src}})"
        f" MATCH (t:{relation.target_type} {{tag_number: $tgt}})"
        f" MERGE (s)-[r:{relation.relation_type}]->(t)"
        " SET r += $props",
        src=relation.source_tag,
        tgt=relation.target_tag,
        props=rel_props,
    )
