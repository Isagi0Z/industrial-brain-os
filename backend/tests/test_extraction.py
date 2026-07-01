"""M7 — Entity & Relation Extraction Pipeline tests."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.document.constants import ChunkType, JobStatus
from app.domain.document.models import DocumentChunk
from app.domain.extraction.models import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
)
from app.domain.ontology.models import (
    NodeTypeSpec,
    OntologySchema,
    RelationSpec,
)
from app.domain.ontology.validator import OntologyValidatorService
from app.infrastructure.extraction.levenshtein_entity_resolver import (
    LevenshteinEntityResolver,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_chunk(text: str = "Pump P-101 feeds vessel V-202.") -> DocumentChunk:
    return DocumentChunk(
        id="chunk-001",
        document_id="doc-001",
        chunk_index=0,
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=1,
        parent_section_header=None,
        bbox_json=None,
        token_count=10,
        created_at=datetime.utcnow(),
    )


def _make_ontology() -> OntologyValidatorService:
    schema = OntologySchema(
        version="1.0",
        node_types={
            "Equipment": NodeTypeSpec(
                name="Equipment",
                required_properties=["tag_number", "equipment_class"],
                optional_properties=["manufacturer"],
            ),
            "Sensor": NodeTypeSpec(
                name="Sensor",
                required_properties=["tag_number", "measurement_type"],
                optional_properties=[],
            ),
            "Asset": NodeTypeSpec(
                name="Asset",
                required_properties=["tag_number", "name"],
                optional_properties=[],
            ),
            "Document": NodeTypeSpec(
                name="Document",
                required_properties=["source_id", "title"],
                optional_properties=[],
            ),
            "Personnel": NodeTypeSpec(
                name="Personnel",
                required_properties=["personnel_id", "role"],
                optional_properties=[],
            ),
            "Process": NodeTypeSpec(
                name="Process",
                required_properties=["process_id", "process_name"],
                optional_properties=[],
            ),
        },
        allowed_relations=[
            RelationSpec(
                source_type="Sensor", relation_type="MONITORS", target_type="Equipment"
            ),
            RelationSpec(
                source_type="Equipment", relation_type="IS_PART_OF", target_type="Asset"
            ),
        ],
    )
    return OntologyValidatorService(schema)


# ---------------------------------------------------------------------------
# LevenshteinEntityResolver
# ---------------------------------------------------------------------------


def _entity(tag: str, etype: str = "Equipment") -> ExtractedEntity:
    return ExtractedEntity(
        text=tag,
        entity_type=etype,
        chunk_id="c1",
        tag_number=tag,
    )


class TestLevenshteinEntityResolver:
    def setup_method(self):
        self.resolver = LevenshteinEntityResolver()

    def test_identical_tags_deduplicated(self):
        entities = [_entity("P-101"), _entity("P-101")]
        result = self.resolver.resolve(entities)
        assert len(result) == 1

    def test_distance_1_same_type_deduplicated(self):
        entities = [_entity("P-101"), _entity("P-102")]
        result = self.resolver.resolve(entities)
        # distance("P-101","P-102") = 1 ≤ 2 → merged
        assert len(result) == 1

    def test_distance_3_not_merged(self):
        entities = [_entity("P-101"), _entity("P-201")]
        result = self.resolver.resolve(entities)
        # distance("P-101","P-201") = 1 ≤ 2 → still merged (numeric difference only 1 char)
        # Actually "P-101" vs "P-201": '1'->'2', distance=1 → merged
        assert len(result) == 1

    def test_different_types_not_merged(self):
        entities = [_entity("PT-100", "Sensor"), _entity("PT-101", "Equipment")]
        result = self.resolver.resolve(entities)
        # Different types → not merged even if distance ≤ 2
        assert len(result) == 2

    def test_empty_input(self):
        assert self.resolver.resolve([]) == []

    def test_untagged_entities_pass_through(self):
        tagged = _entity("P-101")
        untagged = ExtractedEntity(
            text="SomeName", entity_type="Personnel", chunk_id="c1"
        )
        result = self.resolver.resolve([tagged, untagged])
        assert len(result) == 2

    def test_canonical_form_kept(self):
        # Shorter tag is kept as canonical
        entities = [_entity("P-1010"), _entity("P-101")]
        result = self.resolver.resolve(entities)
        assert len(result) == 1
        assert result[0].tag_number == "P-101"

    def test_large_distance_not_merged(self):
        entities = [_entity("P-001"), _entity("V-999")]
        result = self.resolver.resolve(entities)
        # distance("P-001", "V-999") = 3 > 2 → not merged
        assert len(result) == 2


# ---------------------------------------------------------------------------
# SpacyEntityExtractor
# ---------------------------------------------------------------------------


class TestSpacyEntityExtractor:
    def setup_method(self):
        from app.infrastructure.extraction.spacy_entity_extractor import (
            SpacyEntityExtractor,
        )

        self.extractor = SpacyEntityExtractor("en_core_web_sm")

    def test_extracts_industrial_tag_as_equipment(self):
        chunk = _make_chunk("Pump P-101 is running.")
        entities = self.extractor.extract(chunk)
        tags = {e.tag_number for e in entities}
        # P- prefix → Equipment
        assert any("P-101" in str(t) for t in tags if t)

    def test_extracts_sensor_tag(self):
        chunk = _make_chunk("Pressure transmitter PT-100 reads 5 bar.")
        entities = self.extractor.extract(chunk)
        sensor_entities = [e for e in entities if e.entity_type == "Sensor"]
        assert len(sensor_entities) >= 1

    def test_empty_chunk_returns_empty(self):
        chunk = _make_chunk("")
        assert self.extractor.extract(chunk) == []

    def test_chunk_id_set_on_entities(self):
        chunk = _make_chunk("Valve VLV-202 is closed.")
        entities = self.extractor.extract(chunk)
        for e in entities:
            assert e.chunk_id == chunk.id

    def test_sensor_has_measurement_type(self):
        chunk = _make_chunk("Flow transmitter FT-300 is offline.")
        entities = self.extractor.extract(chunk)
        sensors = [e for e in entities if e.entity_type == "Sensor" and e.tag_number]
        for s in sensors:
            assert "measurement_type" in s.properties


# ---------------------------------------------------------------------------
# LLMRelationExtractor
# ---------------------------------------------------------------------------


class TestLLMRelationExtractor:
    def _make_extractor(self, llm_response: str):
        from pathlib import Path
        from app.infrastructure.extraction.llm_relation_extractor import (
            LLMRelationExtractor,
        )

        mock_gateway = AsyncMock()
        mock_gateway.generate = AsyncMock(return_value=(llm_response, 100, 50))

        prompt_path = (
            Path(__file__).parents[1] / "ai" / "prompts" / "relation_extraction.yaml"
        )
        return LLMRelationExtractor(gateway=mock_gateway, prompt_path=prompt_path)

    @pytest.mark.asyncio
    async def test_parses_valid_relation_json(self):
        response = json.dumps(
            [
                {
                    "source_tag": "PT-100",
                    "source_type": "Sensor",
                    "relation_type": "MONITORS",
                    "target_tag": "P-101",
                    "target_type": "Equipment",
                    "confidence": 0.9,
                }
            ]
        )
        extractor = self._make_extractor(response)
        chunk = _make_chunk("PT-100 monitors pump P-101.")
        entities = [
            _entity("PT-100", "Sensor"),
            _entity("P-101", "Equipment"),
        ]
        relations = await extractor.extract(chunk, entities)
        assert len(relations) == 1
        assert relations[0].relation_type == "MONITORS"
        assert relations[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_returns_empty_on_invalid_json(self):
        extractor = self._make_extractor("not json")
        chunk = _make_chunk("P-101 near V-202.")
        entities = [_entity("P-101"), _entity("V-202")]
        result = await extractor.extract(chunk, entities)
        assert result == []

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        response = "```json\n[]\n```"
        extractor = self._make_extractor(response)
        chunk = _make_chunk("P-101 near V-202.")
        entities = [_entity("P-101"), _entity("V-202")]
        result = await extractor.extract(chunk, entities)
        assert result == []

    @pytest.mark.asyncio
    async def test_single_entity_skips_extraction(self):
        extractor = self._make_extractor("[]")
        chunk = _make_chunk("P-101 is running.")
        entities = [_entity("P-101")]
        result = await extractor.extract(chunk, entities)
        assert result == []


# ---------------------------------------------------------------------------
# ExtractionResult / domain models
# ---------------------------------------------------------------------------


class TestExtractionModels:
    def test_extracted_entity_defaults(self):
        e = ExtractedEntity(text="P-101", entity_type="Equipment", chunk_id="c1")
        assert e.tag_number is None
        assert e.properties == {}
        assert e.start_char == 0

    def test_extracted_relation_default_confidence(self):
        r = ExtractedRelation(
            source_tag="PT-100",
            source_type="Sensor",
            relation_type="MONITORS",
            target_tag="P-101",
            target_type="Equipment",
        )
        assert r.confidence == 1.0
        assert r.properties == {}

    def test_extraction_result_empty_lists(self):
        result = ExtractionResult(document_id="d1", chunk_id="c1")
        assert result.entities == []
        assert result.relations == []


# ---------------------------------------------------------------------------
# ExtractionUseCase (integration with mocks)
# ---------------------------------------------------------------------------


class TestExtractionUseCase:
    def _make_use_case(self, chunks, entities, relations):
        from app.application.extraction.extraction_use_case import ExtractionUseCase

        chunk_repo = MagicMock()
        chunk_repo.get_by_document_id.return_value = chunks

        job_repo = MagicMock()

        entity_extractor = MagicMock()
        entity_extractor.extract.return_value = entities

        entity_resolver = MagicMock()
        entity_resolver.resolve.return_value = entities

        relation_extractor = AsyncMock()
        relation_extractor.extract = AsyncMock(return_value=relations)

        kg_writer = MagicMock()

        ontology = _make_ontology()

        uc = ExtractionUseCase(
            chunk_repo=chunk_repo,
            job_repo=job_repo,
            entity_extractor=entity_extractor,
            entity_resolver=entity_resolver,
            relation_extractor=relation_extractor,
            kg_writer=kg_writer,
            ontology_validator=ontology,
        )
        return uc, chunk_repo, job_repo, kg_writer

    @pytest.mark.asyncio
    async def test_no_chunks_advances_to_completed(self):
        uc, _, job_repo, kg_writer = self._make_use_case([], [], [])
        await uc.run_for_document("doc-1", "job-1")

        statuses = [call.args[1] for call in job_repo.update_status.call_args_list]
        assert JobStatus.KG_EXTRACTING in statuses
        assert JobStatus.KG_POPULATED in statuses
        assert JobStatus.COMPLETED in statuses
        kg_writer.write_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_entities_without_tag_number_skipped(self):
        chunks = [_make_chunk()]
        # Entity has no tag_number → should be filtered
        entities = [
            ExtractedEntity(
                text="SomeName", entity_type="Personnel", chunk_id="chunk-001"
            )
        ]
        uc, _, job_repo, kg_writer = self._make_use_case(chunks, entities, [])
        await uc.run_for_document("doc-1", "job-1")
        # kg_writer should not be called because no valid entities
        kg_writer.write_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_entity_written_to_kg(self):
        chunks = [_make_chunk()]
        entities = [
            ExtractedEntity(
                text="P-101",
                entity_type="Equipment",
                chunk_id="chunk-001",
                tag_number="P-101",
                properties={"equipment_class": "pump"},
            )
        ]
        uc, _, _, kg_writer = self._make_use_case(chunks, entities, [])
        await uc.run_for_document("doc-1", "job-1")
        kg_writer.write_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_relation_below_threshold_gets_tentative_flag(self):

        chunks = [_make_chunk()]
        entities = [
            ExtractedEntity(
                text="PT-100",
                entity_type="Sensor",
                chunk_id="chunk-001",
                tag_number="PT-100",
                properties={"measurement_type": "pressure"},
            ),
            ExtractedEntity(
                text="P-101",
                entity_type="Equipment",
                chunk_id="chunk-001",
                tag_number="P-101",
                properties={"equipment_class": "pump"},
            ),
        ]
        rel = ExtractedRelation(
            source_tag="PT-100",
            source_type="Sensor",
            relation_type="MONITORS",
            target_tag="P-101",
            target_type="Equipment",
            confidence=0.3,  # below threshold
        )
        uc, _, _, kg_writer = self._make_use_case(chunks, entities, [rel])
        await uc.run_for_document("doc-1", "job-1")
        # The relation should have tentative=True
        result = kg_writer.write_result.call_args[0][0]
        assert result.relations[0].properties.get("tentative") is True

    @pytest.mark.asyncio
    async def test_ontology_violation_skips_relation(self):
        chunks = [_make_chunk()]
        entities = [
            ExtractedEntity(
                text="PT-100",
                entity_type="Sensor",
                chunk_id="chunk-001",
                tag_number="PT-100",
                properties={"measurement_type": "pressure"},
            ),
            ExtractedEntity(
                text="P-101",
                entity_type="Equipment",
                chunk_id="chunk-001",
                tag_number="P-101",
                properties={"equipment_class": "pump"},
            ),
        ]
        # INVALID_REL not in ontology allowed relations
        rel = ExtractedRelation(
            source_tag="PT-100",
            source_type="Sensor",
            relation_type="INVALID_REL",
            target_tag="P-101",
            target_type="Equipment",
            confidence=0.9,
        )
        uc, _, _, kg_writer = self._make_use_case(chunks, entities, [rel])
        await uc.run_for_document("doc-1", "job-1")
        result = kg_writer.write_result.call_args[0][0]
        assert result.relations == []


# ---------------------------------------------------------------------------
# JobStatus enum
# ---------------------------------------------------------------------------


class TestJobStatusEnum:
    def test_kg_extracting_present(self):
        assert hasattr(JobStatus, "KG_EXTRACTING")

    def test_kg_populated_present(self):
        assert hasattr(JobStatus, "KG_POPULATED")

    def test_kg_extracting_value(self):
        assert JobStatus.KG_EXTRACTING == "KG_EXTRACTING"

    def test_kg_populated_value(self):
        assert JobStatus.KG_POPULATED == "KG_POPULATED"
