"""Orchestrates NER → entity resolution → relation extraction → KG write.

Pipeline per document:
  1. Load all chunks from the chunk repository.
  2. For each chunk: entity extraction (spaCy) → entity resolution (Levenshtein).
  3. For each chunk: LLM relation extraction (against resolved entities).
  4. Validate every entity and relation against the ontology.
  5. Write results to Neo4j via IKGWriter.
  6. Advance job status: KG_EXTRACTING → KG_POPULATED → COMPLETED.
"""

from __future__ import annotations

import logging

from app.domain.document.constants import JobStatus
from app.domain.document.interfaces import IChunkRepository, IJobRepository
from app.domain.extraction.interfaces import (
    IEntityExtractor,
    IEntityResolver,
    IKGWriter,
    IRelationExtractor,
)
from app.domain.extraction.models import ExtractionResult
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
    ) -> None:
        self._chunk_repo = chunk_repo
        self._job_repo = job_repo
        self._entity_extractor = entity_extractor
        self._entity_resolver = entity_resolver
        self._relation_extractor = relation_extractor
        self._kg_writer = kg_writer
        self._validator = ontology_validator

    async def run_for_document(self, document_id: str, job_id: str) -> None:
        """Run the full KG extraction pipeline for all chunks of a document."""
        self._job_repo.update_status(job_id, JobStatus.KG_EXTRACTING)
        logger.info("KG extraction started: document=%s job=%s", document_id, job_id)

        try:
            chunks = self._chunk_repo.get_by_document_id(document_id)
            if not chunks:
                logger.info(
                    "No chunks found for document %s; skipping KG.", document_id
                )
                self._job_repo.update_status(job_id, JobStatus.KG_POPULATED)
                self._job_repo.update_status(job_id, JobStatus.COMPLETED)
                return

            for chunk in chunks:
                result = await self._process_chunk(document_id, chunk)
                if result.entities:
                    self._kg_writer.write_result(result)

            self._job_repo.update_status(job_id, JobStatus.KG_POPULATED)
            self._job_repo.update_status(job_id, JobStatus.COMPLETED)
            logger.info(
                "KG extraction complete: document=%s job=%s chunks=%d",
                document_id,
                job_id,
                len(chunks),
            )
        except Exception as exc:
            logger.error(
                "KG extraction failed: document=%s job=%s error=%s",
                document_id,
                job_id,
                exc,
                exc_info=True,
            )
            self._job_repo.update_status(job_id, JobStatus.FAILED, str(exc))
            raise

    async def _process_chunk(self, document_id: str, chunk) -> ExtractionResult:
        raw_entities = self._entity_extractor.extract(chunk)
        resolved = self._entity_resolver.resolve(raw_entities)

        valid_entities = []
        for entity in resolved:
            if not entity.tag_number:
                continue
            props = {"name": entity.text, **entity.properties}
            if entity.tag_number:
                props["tag_number"] = entity.tag_number
            try:
                self._validator.validate_node(entity.entity_type, props)
                valid_entities.append(entity)
            except OntologyViolationError as e:
                logger.debug("Entity skipped (ontology violation): %s", e)

        relations = []
        if valid_entities:
            raw_relations = await self._relation_extractor.extract(
                chunk, valid_entities
            )
            for rel in raw_relations:
                if rel.confidence < CONFIDENCE_THRESHOLD:
                    rel.properties["tentative"] = True
                try:
                    self._validator.validate_relation(
                        rel.source_type, rel.relation_type, rel.target_type
                    )
                    relations.append(rel)
                except OntologyViolationError as e:
                    logger.debug("Relation skipped (ontology violation): %s", e)

        return ExtractionResult(
            document_id=document_id,
            chunk_id=chunk.id,
            entities=valid_entities,
            relations=relations,
        )
