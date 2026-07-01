"""spaCy-based entity extractor with industrial EntityRuler patterns.

Uses en_core_web_sm with a custom EntityRuler prepended before the NER component.
Industrial tag patterns (FT-001, VLV-202, PT-100, etc.) map to ontology node types.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional

import spacy
from spacy.language import Language
from spacy.pipeline import EntityRuler

from app.domain.document.models import DocumentChunk
from app.domain.extraction.interfaces import IEntityExtractor
from app.domain.extraction.models import ExtractedEntity

logger = logging.getLogger(__name__)

# Maps tag-number prefix → ontology node type + measurement_type (for Sensors)
_TAG_PREFIX_MAP: Dict[str, tuple[str, Optional[str]]] = {
    # Sensors / transmitters / indicators
    "PT": ("Sensor", "pressure"),
    "PI": ("Sensor", "pressure"),
    "PIC": ("Sensor", "pressure"),
    "TE": ("Sensor", "temperature"),
    "TI": ("Sensor", "temperature"),
    "TIC": ("Sensor", "temperature"),
    "FT": ("Sensor", "flow"),
    "FI": ("Sensor", "flow"),
    "FIC": ("Sensor", "flow"),
    "FE": ("Sensor", "flow"),
    "LT": ("Sensor", "level"),
    "LI": ("Sensor", "level"),
    "LIC": ("Sensor", "level"),
    "AT": ("Sensor", "analytical"),
    "AIC": ("Sensor", "analytical"),
    # Equipment
    "P": ("Equipment", None),
    "PMP": ("Equipment", None),
    "V": ("Equipment", None),
    "VLV": ("Equipment", None),
    "XV": ("Equipment", None),
    "CV": ("Equipment", None),
    "E": ("Equipment", None),
    "EX": ("Equipment", None),
    "HX": ("Equipment", None),
    "TK": ("Equipment", None),
    "T": ("Equipment", None),
    "C": ("Equipment", None),
    "K": ("Equipment", None),
    "M": ("Equipment", None),
    "R": ("Equipment", None),
    "AG": ("Equipment", None),
    # Assets (units / trains)
    "UNIT": ("Asset", None),
    "TRAIN": ("Asset", None),
}

# Longest-prefix match: sort by length desc so PIC matches before PI
_SORTED_PREFIXES = sorted(_TAG_PREFIX_MAP.keys(), key=len, reverse=True)

# spaCy label → ontology node type (for default NER results)
_SPACY_LABEL_MAP: Dict[str, str] = {
    "PERSON": "Personnel",
    "ORG": "Asset",
    "PRODUCT": "Equipment",
    "FAC": "Asset",
    "LOC": "Process",
    "GPE": "Process",
    "WORK_OF_ART": "Document",
}

# EntityRuler patterns — each has an `id` that encodes prefix for type lookup
_RULER_PATTERNS = [
    {"label": "INDUSTRIAL_TAG", "pattern": [{"TEXT": {"REGEX": r"[A-Z]{1,4}-\d+"}}]},
    {"label": "INDUSTRIAL_TAG", "pattern": [{"TEXT": {"REGEX": r"[A-Z]{1,4}\d{3,}"}}]},
]


def _make_nlp(model_name: str) -> Language:
    nlp = spacy.load(model_name, exclude=["parser", "lemmatizer"])
    if "entity_ruler" not in nlp.pipe_names:
        ruler: EntityRuler = nlp.add_pipe("entity_ruler", before="ner")  # type: ignore[assignment]
        ruler.add_patterns(_RULER_PATTERNS)  # type: ignore[arg-type]
    return nlp


def _classify_tag(text: str) -> tuple[str, Optional[str], Optional[str]]:
    """Return (entity_type, tag_number, measurement_type) for a tag string."""
    upper = text.upper().strip()
    for prefix in _SORTED_PREFIXES:
        pattern = re.compile(rf"^{re.escape(prefix)}[-\s]?\d+", re.IGNORECASE)
        if pattern.match(upper):
            etype, mtype = _TAG_PREFIX_MAP[prefix]
            return etype, upper, mtype
    return "Equipment", upper, None


class SpacyEntityExtractor(IEntityExtractor):
    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        try:
            self._nlp = _make_nlp(model_name)
            logger.info("SpacyEntityExtractor loaded model: %s", model_name)
        except OSError:
            logger.warning(
                "spaCy model '%s' not found; falling back to en_core_web_sm.",
                model_name,
            )
            self._nlp = _make_nlp("en_core_web_sm")

    def extract(self, chunk: DocumentChunk) -> List[ExtractedEntity]:
        if not chunk.text or not chunk.text.strip():
            return []

        doc = self._nlp(chunk.text)
        entities: List[ExtractedEntity] = []

        for ent in doc.ents:
            entity = self._ent_to_extracted(ent, chunk.id)
            if entity:
                entities.append(entity)

        return entities

    def _ent_to_extracted(self, ent, chunk_id: str) -> Optional[ExtractedEntity]:
        text = ent.text.strip()
        if not text:
            return None

        if ent.label_ == "INDUSTRIAL_TAG":
            etype, tag_number, mtype = _classify_tag(text)
            props: Dict = (
                {"equipment_class": etype.lower()} if etype == "Equipment" else {}
            )
            if mtype:
                props["measurement_type"] = mtype
            return ExtractedEntity(
                text=text,
                entity_type=etype,
                chunk_id=chunk_id,
                tag_number=tag_number,
                properties=props,
                start_char=ent.start_char,
                end_char=ent.end_char,
            )

        mapped_type = _SPACY_LABEL_MAP.get(ent.label_)
        if mapped_type:
            return ExtractedEntity(
                text=text,
                entity_type=mapped_type,
                chunk_id=chunk_id,
                tag_number=None,
                start_char=ent.start_char,
                end_char=ent.end_char,
            )

        return None
