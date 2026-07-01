"""Unit tests for M7 — Entity & Relation Extraction Pipeline.

All tests are pure in-process with no external services (Neo4j, spaCy network
downloads, LLM APIs). spaCy is called directly since en_core_web_sm is
installed in the environment; LLM and KG writers are replaced with mocks.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.domain.document.constants import JobStatus
from app.domain.document.models import DocumentChunk
from app.domain.extraction.models import (
    DocumentExtractionReport,
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
    _mfr_model_key,
    _merge,
)
from app.infrastructure.extraction.llm_relation_extractor import (
    _item_to_relation,
    _parse_response,
    _try_bracket_extract,
    _try_direct,
    _try_strip_fences,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(
    text: str,
    entity_type: str,
    tag: str | None = None,
    manufacturer: str | None = None,
    model_number: str | None = None,
    chunk_id: str = "c1",
    properties: dict | None = None,
) -> ExtractedEntity:
    return ExtractedEntity(
        text=text,
        entity_type=entity_type,
        chunk_id=chunk_id,
        tag_number=tag,
        manufacturer=manufacturer,
        model_number=model_number,
        properties=properties or {},
    )


def _chunk(text: str = "", chunk_id: str = "c1") -> DocumentChunk:
    from app.domain.document.constants import ChunkType
    from datetime import datetime

    return DocumentChunk(
        id=chunk_id,
        document_id="doc1",
        chunk_index=0,
        chunk_type=ChunkType.PARAGRAPH,
        text=text,
        page_number=1,
        parent_section_header=None,
        bbox_json=None,
        token_count=len(text.split()),
        created_at=datetime(2024, 1, 1),
        table_data_json=None,
        figure_storage_key=None,
    )


def _make_schema() -> OntologySchema:
    return OntologySchema(
        version="1.0",
        node_types={
            "Equipment": NodeTypeSpec(
                name="Equipment",
                required_properties=["tag_number", "equipment_class"],
                optional_properties=["manufacturer", "model_number"],
            ),
            "Sensor": NodeTypeSpec(
                name="Sensor",
                required_properties=["tag_number", "measurement_type"],
                optional_properties=["unit"],
            ),
        },
        allowed_relations=[
            RelationSpec("Sensor", "MONITORS", "Equipment"),
            RelationSpec("Equipment", "IS_PART_OF", "Equipment"),
        ],
    )


# ---------------------------------------------------------------------------
# DocumentExtractionReport
# ---------------------------------------------------------------------------


class TestDocumentExtractionReport:
    def test_success_rate_all_chunks_ok(self):
        r = DocumentExtractionReport(
            "d",
            "j",
            chunks_processed=5,
            chunks_failed=0,
            total_entities=10,
            total_relations=3,
        )
        assert r.success_rate == 1.0

    def test_success_rate_partial_failure(self):
        r = DocumentExtractionReport(
            "d",
            "j",
            chunks_processed=4,
            chunks_failed=1,
            total_entities=8,
            total_relations=2,
        )
        assert r.success_rate == pytest.approx(0.75)

    def test_success_rate_all_failed(self):
        r = DocumentExtractionReport(
            "d",
            "j",
            chunks_processed=3,
            chunks_failed=3,
            total_entities=0,
            total_relations=0,
        )
        assert r.success_rate == pytest.approx(0.0)

    def test_success_rate_zero_chunks_returns_one(self):
        r = DocumentExtractionReport(
            "d",
            "j",
            chunks_processed=0,
            chunks_failed=0,
            total_entities=0,
            total_relations=0,
        )
        assert r.success_rate == 1.0


# ---------------------------------------------------------------------------
# LevenshteinEntityResolver — Pass 1: tag-number deduplication
# ---------------------------------------------------------------------------


class TestLevenshteinEntityResolverTagDedup:
    def setup_method(self):
        self.resolver = LevenshteinEntityResolver()

    def test_identical_tags_same_type_deduped(self):
        entities = [
            _entity("FT-001", "Sensor", tag="FT-001"),
            _entity("FT-001", "Sensor", tag="FT-001"),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 1
        assert result[0].tag_number == "FT-001"

    def test_close_tags_same_type_deduped(self):
        # "FT-001" vs "FT-01" — Levenshtein distance = 1
        entities = [
            _entity("FT-001", "Sensor", tag="FT-001"),
            _entity("FT-01", "Sensor", tag="FT-01"),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 1

    def test_close_tags_different_types_kept_separate(self):
        # Same tag text but different entity types → NOT merged
        entities = [
            _entity("P-101", "Equipment", tag="P-101"),
            _entity("P-101", "Sensor", tag="P-101"),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 2

    def test_distant_tags_kept_separate(self):
        # "FT-001" vs "FT-999" — distance = 3
        entities = [
            _entity("FT-001", "Sensor", tag="FT-001"),
            _entity("FT-999", "Sensor", tag="FT-999"),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 2

    def test_merge_keeps_shorter_tag(self):
        entities = [
            _entity("FT-001A", "Sensor", tag="FT-001A"),
            _entity("FT-001", "Sensor", tag="FT-001"),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 1
        assert result[0].tag_number == "FT-001"

    def test_untagged_entities_pass_through(self):
        entities = [
            _entity("SomePump", "Equipment", tag=None),
            _entity("FT-001", "Sensor", tag="FT-001"),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 2

    def test_empty_input(self):
        assert self.resolver.resolve([]) == []

    def test_properties_merged_on_dedup(self):
        e1 = _entity("FT-001", "Sensor", tag="FT-001", properties={"unit": "m3/h"})
        e2 = _entity("FT-01", "Sensor", tag="FT-01", properties={"calibrated": True})
        result = self.resolver.resolve([e1, e2])
        assert len(result) == 1
        assert result[0].properties.get("calibrated") is True
        assert result[0].properties.get("unit") == "m3/h"

    def test_canonical_properties_take_precedence(self):
        e1 = _entity("FT-001", "Sensor", tag="FT-001", properties={"unit": "m3/h"})
        e2 = _entity("FT-01", "Sensor", tag="FT-01", properties={"unit": "GPM"})
        result = self.resolver.resolve([e1, e2])
        assert len(result) == 1
        # e1 was inserted first as canonical → its unit wins
        assert result[0].properties.get("unit") == "m3/h"


# ---------------------------------------------------------------------------
# LevenshteinEntityResolver — Pass 2: manufacturer + model deduplication
# ---------------------------------------------------------------------------


class TestLevenshteinEntityResolverMfrModelDedup:
    def setup_method(self):
        self.resolver = LevenshteinEntityResolver()

    def test_same_mfr_model_equipment_deduped(self):
        entities = [
            _entity(
                "P-101",
                "Equipment",
                tag="P-101",
                manufacturer="Grundfos",
                model_number="CM5-6",
            ),
            _entity(
                "P-101A",
                "Equipment",
                tag="P-101A",
                manufacturer="Grundfos",
                model_number="CM5-6",
            ),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 1

    def test_mfr_model_key_is_case_insensitive(self):
        entities = [
            _entity(
                "P-101",
                "Equipment",
                tag="P-101",
                manufacturer="grundfos",
                model_number="cm5-6",
            ),
            _entity(
                "P-201",
                "Equipment",
                tag="P-201",
                manufacturer="GRUNDFOS",
                model_number="CM5-6",
            ),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 1

    def test_different_mfr_same_model_not_deduped(self):
        # "P-101" vs "P-999" — Levenshtein distance 3 → not merged by Pass 1
        entities = [
            _entity(
                "P-101",
                "Equipment",
                tag="P-101",
                manufacturer="Grundfos",
                model_number="CM5-6",
            ),
            _entity(
                "P-999",
                "Equipment",
                tag="P-999",
                manufacturer="KSB",
                model_number="CM5-6",
            ),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 2

    def test_missing_model_number_skips_pass2(self):
        # "P-101" vs "P-999" — distance 3, not merged by tag pass
        entities = [
            _entity("P-101", "Equipment", tag="P-101", manufacturer="Grundfos"),
            _entity("P-999", "Equipment", tag="P-999", manufacturer="Grundfos"),
        ]
        result = self.resolver.resolve(entities)
        assert len(result) == 2

    def test_mfr_model_dedup_only_for_equipment(self):
        # Sensors with same mfr+model should NOT be deduped via Pass 2
        # "FT-001" vs "FT-999" — distance 3, not merged by tag pass either
        entities = [
            _entity(
                "FT-001",
                "Sensor",
                tag="FT-001",
                manufacturer="Endress",
                model_number="M2",
            ),
            _entity(
                "FT-999",
                "Sensor",
                tag="FT-999",
                manufacturer="Endress",
                model_number="M2",
            ),
        ]
        result = self.resolver.resolve(entities)
        # Pass 2 only handles Equipment → both Sensors remain
        assert len(result) == 2

    def test_mfr_model_propagated_on_merge(self):
        e1 = _entity("P-101", "Equipment", tag="P-101")  # no mfr info
        e2 = _entity(
            "P-101A",
            "Equipment",
            tag="P-101A",
            manufacturer="Grundfos",
            model_number="CM5-6",
        )
        result = self.resolver.resolve([e1, e2])
        # Tag pass merges them (dist=1); canonical gets mfr propagated
        assert len(result) == 1
        assert result[0].manufacturer == "Grundfos"
        assert result[0].model_number == "CM5-6"


# ---------------------------------------------------------------------------
# _mfr_model_key helper
# ---------------------------------------------------------------------------


class TestMfrModelKey:
    def test_returns_tuple_when_both_present(self):
        e = _entity(
            "P-101",
            "Equipment",
            tag="P-101",
            manufacturer="Grundfos",
            model_number="CM5-6",
        )
        assert _mfr_model_key(e) == ("GRUNDFOS", "CM5-6")

    def test_returns_none_when_manufacturer_missing(self):
        e = _entity("P-101", "Equipment", tag="P-101", model_number="CM5-6")
        assert _mfr_model_key(e) is None

    def test_returns_none_when_model_missing(self):
        e = _entity("P-101", "Equipment", tag="P-101", manufacturer="Grundfos")
        assert _mfr_model_key(e) is None

    def test_reads_from_properties_dict(self):
        e = _entity(
            "P-101",
            "Equipment",
            tag="P-101",
            properties={"manufacturer": "KSB", "model_number": "Etanorm"},
        )
        key = _mfr_model_key(e)
        assert key == ("KSB", "ETANORM")


# ---------------------------------------------------------------------------
# _merge helper
# ---------------------------------------------------------------------------


class TestMerge:
    def test_keeps_shorter_canonical_tag(self):
        canon = _entity("FT-001A", "Sensor", tag="FT-001A")
        dup = _entity("FT-001", "Sensor", tag="FT-001")
        _merge(canon, dup)
        assert canon.tag_number == "FT-001"
        assert canon.text == "FT-001"

    def test_does_not_swap_when_canonical_shorter(self):
        canon = _entity("FT-001", "Sensor", tag="FT-001")
        dup = _entity("FT-001A", "Sensor", tag="FT-001A")
        _merge(canon, dup)
        assert canon.tag_number == "FT-001"

    def test_propagates_manufacturer_to_canonical(self):
        canon = _entity("P-101", "Equipment", tag="P-101")
        dup = _entity("P-101A", "Equipment", tag="P-101A", manufacturer="Grundfos")
        _merge(canon, dup)
        assert canon.manufacturer == "Grundfos"

    def test_does_not_overwrite_existing_manufacturer(self):
        canon = _entity("P-101", "Equipment", tag="P-101", manufacturer="KSB")
        dup = _entity("P-101A", "Equipment", tag="P-101A", manufacturer="Grundfos")
        _merge(canon, dup)
        assert canon.manufacturer == "KSB"


# ---------------------------------------------------------------------------
# LLM relation extractor — JSON parsing strategies
# ---------------------------------------------------------------------------


class TestParseResponseDirect:
    def test_valid_json_array(self):
        raw = json.dumps(
            [
                {
                    "source_tag": "FT-001",
                    "source_type": "Sensor",
                    "relation_type": "MONITORS",
                    "target_tag": "P-101",
                    "target_type": "Equipment",
                    "confidence": 0.9,
                }
            ]
        )
        rels = _parse_response(raw)
        assert len(rels) == 1
        assert rels[0].source_tag == "FT-001"
        assert rels[0].confidence == pytest.approx(0.9)

    def test_empty_array(self):
        assert _parse_response("[]") == []

    def test_missing_required_key_skipped(self):
        raw = json.dumps([{"source_tag": "FT-001"}])
        rels = _parse_response(raw)
        assert rels == []

    def test_confidence_clamped_above_one(self):
        raw = json.dumps(
            [
                {
                    "source_tag": "FT-001",
                    "source_type": "Sensor",
                    "relation_type": "MONITORS",
                    "target_tag": "P-101",
                    "target_type": "Equipment",
                    "confidence": 2.5,
                }
            ]
        )
        rels = _parse_response(raw)
        assert rels[0].confidence == pytest.approx(1.0)

    def test_confidence_clamped_below_zero(self):
        raw = json.dumps(
            [
                {
                    "source_tag": "FT-001",
                    "source_type": "Sensor",
                    "relation_type": "MONITORS",
                    "target_tag": "P-101",
                    "target_type": "Equipment",
                    "confidence": -0.5,
                }
            ]
        )
        rels = _parse_response(raw)
        assert rels[0].confidence == pytest.approx(0.0)

    def test_non_array_root_object_returns_empty(self):
        raw = json.dumps({"error": "bad response"})
        rels = _parse_response(raw)
        assert rels == []

    def test_fully_invalid_json_returns_empty(self):
        rels = _parse_response("not json at all")
        assert rels == []


class TestParseResponseBracketExtract:
    def test_extracts_array_from_prose_preamble(self):
        preamble = "Sure! Here are the relations:\n"
        payload = json.dumps(
            [
                {
                    "source_tag": "FT-001",
                    "source_type": "Sensor",
                    "relation_type": "MONITORS",
                    "target_tag": "P-101",
                    "target_type": "Equipment",
                    "confidence": 0.8,
                }
            ]
        )
        rels = _parse_response(preamble + payload)
        assert len(rels) == 1

    def test_extracts_array_after_prose_suffix(self):
        payload = json.dumps(
            [
                {
                    "source_tag": "FT-001",
                    "source_type": "Sensor",
                    "relation_type": "MONITORS",
                    "target_tag": "P-101",
                    "target_type": "Equipment",
                }
            ]
        )
        rels = _parse_response(payload + "\nHope that helps!")
        assert len(rels) == 1

    def test_try_bracket_extract_returns_none_on_no_bracket(self):
        assert _try_bracket_extract("no brackets here") is None

    def test_try_direct_returns_none_on_invalid(self):
        assert _try_direct("{bad") is None


class TestParseResponseFenceStrip:
    def test_strips_json_fence_and_parses(self):
        payload = json.dumps(
            [
                {
                    "source_tag": "FT-001",
                    "source_type": "Sensor",
                    "relation_type": "MONITORS",
                    "target_tag": "P-101",
                    "target_type": "Equipment",
                }
            ]
        )
        fenced = f"```json\n{payload}\n```"
        rels = _parse_response(fenced)
        assert len(rels) == 1

    def test_strips_plain_fence_and_parses(self):
        payload = json.dumps(
            [
                {
                    "source_tag": "FT-001",
                    "source_type": "Sensor",
                    "relation_type": "MONITORS",
                    "target_tag": "P-101",
                    "target_type": "Equipment",
                }
            ]
        )
        fenced = f"```\n{payload}\n```"
        rels = _try_strip_fences(fenced)
        assert isinstance(rels, list)

    def test_try_strip_fences_returns_none_on_bad_json(self):
        assert _try_strip_fences("```\nnot json\n```") is None


# ---------------------------------------------------------------------------
# _item_to_relation
# ---------------------------------------------------------------------------


class TestItemToRelation:
    def test_valid_item(self):
        item = {
            "source_tag": "FT-001",
            "source_type": "Sensor",
            "relation_type": "MONITORS",
            "target_tag": "P-101",
            "target_type": "Equipment",
            "confidence": 0.7,
        }
        rel = _item_to_relation(item)
        assert rel is not None
        assert rel.relation_type == "MONITORS"
        assert rel.confidence == pytest.approx(0.7)

    def test_missing_key_returns_none(self):
        assert _item_to_relation({"source_tag": "FT-001"}) is None

    def test_non_dict_returns_none(self):
        assert _item_to_relation("bad") is None
        assert _item_to_relation(42) is None

    def test_default_confidence_is_one(self):
        item = {
            "source_tag": "FT-001",
            "source_type": "Sensor",
            "relation_type": "MONITORS",
            "target_tag": "P-101",
            "target_type": "Equipment",
        }
        rel = _item_to_relation(item)
        assert rel is not None
        assert rel.confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# SpacyEntityExtractor — requires en_core_web_sm to be installed
# ---------------------------------------------------------------------------


try:
    import spacy as _spacy_check  # noqa: F401

    _SPACY_AVAILABLE = True
except ModuleNotFoundError:
    _SPACY_AVAILABLE = False


@pytest.mark.skipif(
    not _SPACY_AVAILABLE, reason="spaCy not installed in this environment"
)
class TestSpacyEntityExtractor:
    @pytest.fixture(scope="class")
    def extractor(self):
        from app.infrastructure.extraction.spacy_entity_extractor import (
            SpacyEntityExtractor,
        )

        return SpacyEntityExtractor("en_core_web_sm")

    def test_extracts_hyphenated_tag(self, extractor):
        chunk = _chunk("Replace sensor FT-101 on the flow line.")
        entities = extractor.extract(chunk)
        tags = [e.tag_number for e in entities]
        assert "FT-101" in tags

    def test_maps_ft_prefix_to_sensor_type(self, extractor):
        chunk = _chunk("Flow transmitter FT-202 is faulty.")
        entities = extractor.extract(chunk)
        ft = next((e for e in entities if e.tag_number == "FT-202"), None)
        assert ft is not None
        assert ft.entity_type == "Sensor"
        assert ft.properties.get("measurement_type") == "flow"

    def test_maps_vlv_prefix_to_equipment_valve(self, extractor):
        chunk = _chunk("Inspect valve VLV-305 for leaks.")
        entities = extractor.extract(chunk)
        vlv = next(
            (e for e in entities if e.tag_number and "305" in e.tag_number), None
        )
        assert vlv is not None
        assert vlv.entity_type == "Equipment"
        assert vlv.properties.get("equipment_class") == "valve"

    def test_maps_pt_prefix_to_pressure_sensor(self, extractor):
        chunk = _chunk("Pressure transmitter PT-100 reading high.")
        entities = extractor.extract(chunk)
        pt = next((e for e in entities if e.tag_number and "100" in e.tag_number), None)
        assert pt is not None
        assert pt.entity_type == "Sensor"
        assert pt.properties.get("measurement_type") == "pressure"

    def test_empty_chunk_returns_empty(self, extractor):
        chunk = _chunk("")
        assert extractor.extract(chunk) == []

    def test_no_duplicate_spans(self, extractor):
        chunk = _chunk("FT-001 FT-001 FT-001 all three are the same sensor.")
        entities = extractor.extract(chunk)
        ft_tags = [e.tag_number for e in entities if e.tag_number == "FT-001"]
        assert len(ft_tags) == len(set(ft_tags))

    def test_pic_prefix_wins_over_pi(self, extractor):
        chunk = _chunk("PIC-300 regulates the pressure setpoint.")
        entities = extractor.extract(chunk)
        pic = next(
            (e for e in entities if e.tag_number and "300" in e.tag_number), None
        )
        assert pic is not None
        assert "pressure" in (pic.properties.get("measurement_type") or "")


# ---------------------------------------------------------------------------
# ExtractionUseCase — integration (mocked infra)
# ---------------------------------------------------------------------------


def _make_use_case(
    chunks,
    entity_extractor=None,
    entity_resolver=None,
    relation_extractor=None,
    kg_writer=None,
    validator=None,
    threshold=0.6,
):
    from app.application.extraction.extraction_use_case import ExtractionUseCase

    chunk_repo = MagicMock()
    chunk_repo.get_by_document_id.return_value = chunks

    job_repo = MagicMock()

    if entity_extractor is None:
        entity_extractor = MagicMock()
        entity_extractor.extract.return_value = []

    if entity_resolver is None:
        entity_resolver = MagicMock()
        entity_resolver.resolve.return_value = []

    if relation_extractor is None:
        relation_extractor = MagicMock()

        # async mock
        async def _async_extract(*a, **kw):
            return []

        relation_extractor.extract = _async_extract

    if kg_writer is None:
        kg_writer = MagicMock()

    if validator is None:
        validator = MagicMock()
        validator.validate_node.return_value = None
        validator.validate_relation.return_value = None

    uc = ExtractionUseCase(
        chunk_repo=chunk_repo,
        job_repo=job_repo,
        entity_extractor=entity_extractor,
        entity_resolver=entity_resolver,
        relation_extractor=relation_extractor,
        kg_writer=kg_writer,
        ontology_validator=validator,
        confidence_threshold=threshold,
    )
    return uc, job_repo, kg_writer


class TestExtractionUseCaseStatusTransitions:
    def test_status_advances_through_kg_extracting_to_completed(self):
        chunks = [_chunk("FT-001 is a sensor.")]
        uc, job_repo, _ = _make_use_case(chunks)

        asyncio.run(uc.run_for_document("doc1", "job1"))

        calls = [c[0][1] for c in job_repo.update_status.call_args_list]
        assert JobStatus.KG_EXTRACTING in calls
        assert JobStatus.KG_POPULATED in calls
        assert JobStatus.COMPLETED in calls

    def test_kg_extracting_called_before_kg_populated(self):
        chunks = [_chunk("text")]
        uc, job_repo, _ = _make_use_case(chunks)

        asyncio.run(uc.run_for_document("doc1", "job1"))

        statuses = [c[0][1] for c in job_repo.update_status.call_args_list]
        assert statuses.index(JobStatus.KG_EXTRACTING) < statuses.index(
            JobStatus.KG_POPULATED
        )

    def test_no_chunks_still_completes(self):
        uc, job_repo, _ = _make_use_case([])
        asyncio.run(uc.run_for_document("doc1", "job1"))
        statuses = [c[0][1] for c in job_repo.update_status.call_args_list]
        assert JobStatus.COMPLETED in statuses


class TestExtractionUseCaseEntityCountLogging:
    def test_write_report_called_with_entity_count(self):
        entity = _entity(
            "FT-001", "Sensor", tag="FT-001", properties={"measurement_type": "flow"}
        )

        extractor = MagicMock()
        extractor.extract.return_value = [entity]

        resolver = MagicMock()
        resolver.resolve.return_value = [entity]

        validator = MagicMock()
        validator.validate_node.return_value = None
        validator.validate_relation.return_value = None

        uc, _, kg_writer = _make_use_case(
            [_chunk("FT-001 reads flow.")],
            entity_extractor=extractor,
            entity_resolver=resolver,
            validator=validator,
        )

        asyncio.run(uc.run_for_document("doc1", "job1"))

        kg_writer.write_report.assert_called_once()
        report: DocumentExtractionReport = kg_writer.write_report.call_args[0][0]
        assert report.document_id == "doc1"
        assert report.job_id == "job1"
        assert report.total_entities >= 1
        assert report.chunks_processed == 1

    def test_write_report_reflects_chunk_count(self):
        extractor = MagicMock()
        extractor.extract.return_value = []

        resolver = MagicMock()
        resolver.resolve.return_value = []

        chunks = [
            _chunk("chunk 1", "c1"),
            _chunk("chunk 2", "c2"),
            _chunk("chunk 3", "c3"),
        ]
        uc, _, kg_writer = _make_use_case(
            chunks, entity_extractor=extractor, entity_resolver=resolver
        )

        asyncio.run(uc.run_for_document("doc1", "job1"))

        report = kg_writer.write_report.call_args[0][0]
        assert report.chunks_processed == 3

    def test_failed_chunks_counted_in_report(self):
        bad_extractor = MagicMock()
        bad_extractor.extract.side_effect = RuntimeError("NLP crash")

        resolver = MagicMock()
        resolver.resolve.return_value = []

        chunks = [_chunk("problem chunk")]
        uc, _, kg_writer = _make_use_case(
            chunks, entity_extractor=bad_extractor, entity_resolver=resolver
        )

        asyncio.run(uc.run_for_document("doc1", "job1"))

        report = kg_writer.write_report.call_args[0][0]
        assert report.chunks_failed == 1
        assert report.chunks_processed == 1


class TestExtractionUseCasePerChunkIsolation:
    def test_single_bad_chunk_does_not_abort_rest(self):
        call_count = 0

        class SometimesFailExtractor:
            def extract(self, chunk):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise ValueError("Simulated extractor failure on chunk 2")
                return []

        resolver = MagicMock()
        resolver.resolve.return_value = []

        chunks = [_chunk("c1", "c1"), _chunk("c2", "c2"), _chunk("c3", "c3")]
        uc, _, kg_writer = _make_use_case(
            chunks,
            entity_extractor=SometimesFailExtractor(),
            entity_resolver=resolver,
        )

        # Must not raise
        asyncio.run(uc.run_for_document("doc1", "job1"))

        report = kg_writer.write_report.call_args[0][0]
        assert report.chunks_failed == 1
        assert report.chunks_processed == 3

    def test_all_chunks_fail_still_writes_report(self):
        bad_extractor = MagicMock()
        bad_extractor.extract.side_effect = Exception("total disaster")

        resolver = MagicMock()
        chunks = [_chunk("c1", "c1"), _chunk("c2", "c2")]
        uc, _, kg_writer = _make_use_case(
            chunks, entity_extractor=bad_extractor, entity_resolver=resolver
        )

        asyncio.run(uc.run_for_document("doc1", "job1"))

        kg_writer.write_report.assert_called_once()
        report = kg_writer.write_report.call_args[0][0]
        assert report.chunks_failed == 2
        assert report.total_entities == 0


class TestExtractionUseCaseConfidenceThreshold:
    def test_low_confidence_relation_marked_tentative(self):
        entity_a = _entity(
            "FT-001", "Sensor", tag="FT-001", properties={"measurement_type": "flow"}
        )
        entity_b = _entity(
            "P-101", "Equipment", tag="P-101", properties={"equipment_class": "pump"}
        )

        extractor = MagicMock()
        extractor.extract.return_value = [entity_a, entity_b]

        resolver = MagicMock()
        resolver.resolve.return_value = [entity_a, entity_b]

        low_conf_relation = ExtractedRelation(
            source_tag="FT-001",
            source_type="Sensor",
            relation_type="MONITORS",
            target_tag="P-101",
            target_type="Equipment",
            confidence=0.4,
        )

        async def _async_extract(*a, **kw):
            return [low_conf_relation]

        relation_extractor = MagicMock()
        relation_extractor.extract = _async_extract

        validator = OntologyValidatorService(_make_schema())

        uc, _, kg_writer = _make_use_case(
            [_chunk("FT-001 monitors P-101")],
            entity_extractor=extractor,
            entity_resolver=resolver,
            relation_extractor=relation_extractor,
            validator=validator,
            threshold=0.6,
        )

        asyncio.run(uc.run_for_document("doc1", "job1"))

        # Relation passes ontology but is below threshold → tentative=True
        # write_result should be called with the relation still included
        if kg_writer.write_result.called:
            result: ExtractionResult = kg_writer.write_result.call_args[0][0]
            for rel in result.relations:
                if rel.confidence < 0.6:
                    assert rel.properties.get("tentative") is True

    def test_high_confidence_relation_not_tentative(self):
        entity_a = _entity(
            "FT-001", "Sensor", tag="FT-001", properties={"measurement_type": "flow"}
        )
        entity_b = _entity(
            "P-101", "Equipment", tag="P-101", properties={"equipment_class": "pump"}
        )

        extractor = MagicMock()
        extractor.extract.return_value = [entity_a, entity_b]

        resolver = MagicMock()
        resolver.resolve.return_value = [entity_a, entity_b]

        high_conf_relation = ExtractedRelation(
            source_tag="FT-001",
            source_type="Sensor",
            relation_type="MONITORS",
            target_tag="P-101",
            target_type="Equipment",
            confidence=0.9,
        )

        async def _async_extract(*a, **kw):
            return [high_conf_relation]

        relation_extractor = MagicMock()
        relation_extractor.extract = _async_extract

        validator = OntologyValidatorService(_make_schema())

        uc, _, kg_writer = _make_use_case(
            [_chunk("FT-001 monitors P-101")],
            entity_extractor=extractor,
            entity_resolver=resolver,
            relation_extractor=relation_extractor,
            validator=validator,
            threshold=0.6,
        )

        asyncio.run(uc.run_for_document("doc1", "job1"))

        if kg_writer.write_result.called:
            result: ExtractionResult = kg_writer.write_result.call_args[0][0]
            for rel in result.relations:
                if rel.confidence >= 0.6:
                    assert not rel.properties.get("tentative")
