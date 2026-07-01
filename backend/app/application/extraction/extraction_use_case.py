"""Orchestrates NER → entity resolution → relation extraction → KG write.

Pipeline per document:
  1. Load all chunks from the chunk repository.
  2. For each chunk (in isolation):
       a. Entity extraction (spaCy + EntityRuler).
       b. Entity resolution (Levenshtein on tag numbers + manufacturer/model).
       c. Ontology validation for each candidate entity.
       d. LLM relation extraction against the validated entity set.
       e. Ontology validation for each candidate relation.
       f. Flag relations below the confidence threshold as tentative.
       g. Write the chunk result to Neo4j.
  3. Any per-chunk error is logged and skipped; the document is never failed by
     a single bad chunk.
  4. Log a DocumentExtractionReport for operational visibility.
  5. Advance job status: KG_EXTRACTING → KG_POPULATED → COMPLETED.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.domain.document.constants import JobStatus
from app.domain.document.interfaces import IChunkRepository, IJobRepository
from app.domain.document.models import DocumentChunk
from app.domain.extraction.interfaces import (
    IEntityExtractor,
    IEntityResolver,
    IKGWriter,
    IRelationExtractor,
)
from app.domain.extraction.models import (
    DocumentExtractionReport,
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)
from app.domain.ontology.interfaces import IOntologyValidator
from app.domain.ontology.models import OntologyViolationError

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6


class ExtractionUseCase:
    def __init__(
        self,
        chunk_repo: IChunkRepository,
        job_repo: IJobRepository,
        entity_extractor: IEntityExtractor,
        entity_resolver: IEntityResolver,
        relation_extractor: IRelationExtractor,
        kg_writer: IKGWriter,
        ontology_validator: IOntologyValidator,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self._chunk_repo = chunk_repo
        self._job_repo = job_repo
        self._entity_extractor = entity_extractor
        self._entity_resolver = entity_resolver
        self._relation_extractor = relation_extractor
        self._kg_writer = kg_writer
        self._validator = ontology_validator
        self._confidence_threshold = confidence_threshold

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run_for_document(self, document_id: str, job_id: str) -> None:
        """Run the full KG extraction pipeline for all chunks of a document."""
        self._job_repo.update_status(job_id, JobStatus.KG_EXTRACTING)
        logger.info("KG extraction started: document=%s job=%s", document_id, job_id)

        chunks = self._chunk_repo.get_by_document_id(document_id)
        if not chunks:
            logger.info("KG extraction skipped (no chunks): document=%s", document_id)
            self._job_repo.update_status(job_id, JobStatus.KG_POPULATED)
            self._job_repo.update_status(job_id, JobStatus.COMPLETED)
            return

        total_entities = 0
        total_relations = 0
        failed_chunks = 0

        for chunk in chunks:
            try:
                result = await self._process_chunk(document_id, chunk)
                if result.entities:
                    self._kg_writer.write_result(result)
                    total_entities += len(result.entities)
                    total_relations += len(result.relations)
            except Exception as exc:
                failed_chunks += 1
                logger.error(
                    "Chunk extraction failed — skipping: document=%s chunk=%s error=%s",
                    document_id,
                    chunk.id,
                    exc,
                    exc_info=True,
                )

        report = DocumentExtractionReport(
            document_id=document_id,
            job_id=job_id,
            chunks_processed=len(chunks),
            chunks_failed=failed_chunks,
            total_entities=total_entities,
            total_relations=total_relations,
        )
        self._kg_writer.write_report(report)
        logger.info(
            "KG extraction complete: document=%s job=%s "
            "chunks=%d failed=%d entities=%d relations=%d success_rate=%.1f%%",
            document_id,
            job_id,
            report.chunks_processed,
            report.chunks_failed,
            report.total_entities,
            report.total_relations,
            report.success_rate * 100,
        )

        self._job_repo.update_status(job_id, JobStatus.KG_POPULATED)
        self._job_repo.update_status(job_id, JobStatus.COMPLETED)

    # ------------------------------------------------------------------
    # Per-chunk processing
    # ------------------------------------------------------------------

    async def _process_chunk(
        self, document_id: str, chunk: DocumentChunk
    ) -> ExtractionResult:
        raw_entities = self._entity_extractor.extract(chunk)
        resolved = self._entity_resolver.resolve(raw_entities)

        valid_entities = self._validate_entities(resolved)

        relations: List[ExtractedRelation] = []
        if len(valid_entities) >= 2:
            raw_relations = await self._relation_extractor.extract(
                chunk, valid_entities
            )
            relations = self._validate_relations(raw_relations)

        return ExtractionResult(
            document_id=document_id,
            chunk_id=chunk.id,
            entities=valid_entities,
            relations=relations,
        )

    def _validate_entities(
        self, entities: List[ExtractedEntity]
    ) -> List[ExtractedEntity]:
        valid: List[ExtractedEntity] = []
        for entity in entities:
            if not entity.tag_number:
                continue
            props: Dict[str, Any] = {
                "name": entity.text,
                "tag_number": entity.tag_number,
            }
            props.update(entity.properties)
            try:
                self._validator.validate_node(entity.entity_type, props)
                valid.append(entity)
            except OntologyViolationError as exc:
                logger.debug("Entity rejected by ontology: %s — %s", entity.text, exc)
        return valid

    def _validate_relations(
        self, relations: List[ExtractedRelation]
    ) -> List[ExtractedRelation]:
        valid: List[ExtractedRelation] = []
        for rel in relations:
            if rel.confidence < self._confidence_threshold:
                rel.properties["tentative"] = True
            try:
                self._validator.validate_relation(
                    rel.source_type, rel.relation_type, rel.target_type
                )
                valid.append(rel)
            except OntologyViolationError as exc:
                logger.debug(
                    "Relation rejected by ontology: %s-[%s]->%s — %s",
                    rel.source_type,
                    rel.relation_type,
                    rel.target_type,
                    exc,
                )
        return valid
