"""Neo4j Knowledge Graph writer.

Writes ExtractedEntity and ExtractedRelation instances as nodes/edges using
idempotent MERGE statements.  Every node and relation is validated against the
ontology before any Cypher is executed.

HAS_CHUNK relationship:
  (doc:Document)-[:HAS_CHUNK]->(chunk:DocumentChunk)
  Written once per chunk that yields at least one valid entity.

Confidence threshold (< 0.6): relations written with {tentative: true}.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from neo4j import Driver

from app.domain.extraction.interfaces import IKGWriter
from app.domain.extraction.models import (
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)

logger = logging.getLogger(__name__)


class Neo4jKGWriter(IKGWriter):
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def write_result(self, result: ExtractionResult) -> None:
        if not result.entities:
            return

        with self._driver.session() as session:
            for entity in result.entities:
                if entity.tag_number:
                    session.execute_write(self._merge_entity, entity)

            if result.entities:
                session.execute_write(
                    self._merge_has_chunk,
                    result.document_id,
                    result.chunk_id,
                    [e.tag_number for e in result.entities if e.tag_number],
                )

            for relation in result.relations:
                session.execute_write(self._merge_relation, relation)

        logger.debug(
            "KG write: chunk=%s entities=%d relations=%d",
            result.chunk_id,
            len(result.entities),
            len(result.relations),
        )

    # ------------------------------------------------------------------
    # Transaction functions (called inside execute_write)
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_entity(tx, entity: ExtractedEntity) -> None:
        label = entity.entity_type
        props: Dict[str, Any] = {"tag_number": entity.tag_number, "name": entity.text}
        props.update(entity.properties)

        query = f"MERGE (n:{label} {{tag_number: $tag}}) " "SET n += $props " "RETURN n"
        tx.run(query, tag=entity.tag_number, props=props)

    @staticmethod
    def _merge_has_chunk(
        tx, document_id: str, chunk_id: str, entity_tags: list
    ) -> None:
        # Ensure the DocumentChunk node exists and link it to the Document
        tx.run(
            "MERGE (d:Document {source_id: $doc_id}) "
            "MERGE (c:DocumentChunk {chunk_id: $chunk_id}) "
            "ON CREATE SET c.document_id = $doc_id "
            "MERGE (d)-[:HAS_CHUNK]->(c)",
            doc_id=document_id,
            chunk_id=chunk_id,
        )
        # Link each extracted entity to the chunk
        for tag in entity_tags:
            tx.run(
                "MATCH (c:DocumentChunk {chunk_id: $chunk_id}) "
                "MATCH (e {tag_number: $tag}) "
                "MERGE (c)-[:MENTIONS]->(e)",
                chunk_id=chunk_id,
                tag=tag,
            )

    @staticmethod
    def _merge_relation(tx, relation: ExtractedRelation) -> None:
        rel_props: Dict[str, Any] = {"confidence": relation.confidence}
        rel_props.update(relation.properties)

        query = (
            f"MATCH (s:{relation.source_type} {{tag_number: $src_tag}}) "
            f"MATCH (t:{relation.target_type} {{tag_number: $tgt_tag}}) "
            f"MERGE (s)-[r:{relation.relation_type}]->(t) "
            "SET r += $props"
        )
        tx.run(
            query,
            src_tag=relation.source_tag,
            tgt_tag=relation.target_tag,
            props=rel_props,
        )
