"""spaCy-based entity extractor with industrial EntityRuler patterns.

Uses en_core_web_sm with a custom EntityRuler prepended before the NER component.
Industrial tag patterns (FT-001, VLV-202, PT-100, etc.) map to ontology node types.
Longest-prefix matching ensures PIC beats PI, PMP beats P.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional, Tuple

import spacy
from spacy.language import Language
from spacy.pipeline import EntityRuler

from app.domain.document.models import DocumentChunk
from app.domain.extraction.interfaces import IEntityExtractor
from app.domain.extraction.models import ExtractedEntity

logger = logging.getLogger(__name__)

# (entity_type, measurement_type or None, equipment_class or None)
_TagInfo = Tuple[str, Optional[str], Optional[str]]

# Maps tag-number prefix → (entity_type, measurement_type, equipment_class)
_TAG_PREFIX_MAP: Dict[str, _TagInfo] = {
    # Analytical
    "AIC": ("Sensor", "analytical", None),
    "AT": ("Sensor", "analytical", None),
    # Flow
    "FIC": ("Sensor", "flow", None),
    "FT": ("Sensor", "flow", None),
    "FE": ("Sensor", "flow", None),
    "FI": ("Sensor", "flow", None),
    # Level
    "LIC": ("Sensor", "level", None),
    "LT": ("Sensor", "level", None),
    "LI": ("Sensor", "level", None),
    # Pressure
    "PIC": ("Sensor", "pressure", None),
    "PT": ("Sensor", "pressure", None),
    "PI": ("Sensor", "pressure", None),
    # Temperature
    "TIC": ("Sensor", "temperature", None),
    "TE": ("Sensor", "temperature", None),
    "TI": ("Sensor", "temperature", None),
    # Valve / control
    "XV": ("Equipment", None, "valve"),
    "CV": ("Equipment", None, "valve"),
    "VLV": ("Equipment", None, "valve"),
    # Compressor
    "CMP": ("Equipment", None, "compressor"),
    # Pump
    "PMP": ("Equipment", None, "pump"),
    # Agitator
    "AG": ("Equipment", None, "agitator"),
    # Exchanger
    "HX": ("Equipment", None, "heat_exchanger"),
    "EX": ("Equipment", None, "exchanger"),
    # Motor
    "MCC": ("Equipment", None, "motor_control_center"),
    # Reactor / vessel
    "R": ("Equipment", None, "reactor"),
    # Tank
    "TK": ("Equipment", None, "tank"),
    # Single-letter catches (last resort — only match if nothing else does)
    "K": ("Equipment", None, "compressor"),
    "M": ("Equipment", None, "motor"),
    "C": ("Equipment", None, "compressor"),
    "E": ("Equipment", None, "exchanger"),
    "T": ("Equipment", None, "tank"),
    "V": ("Equipment", None, "vessel"),
    "P": ("Equipment", None, "pump"),
    # Asset / process unit
    "TRAIN": ("Asset", None, None),
    "UNIT": ("Asset", None, None),
}

# Sort longest first so PIC is tried before PI, PMP before P, VLV before V
_SORTED_PREFIXES = sorted(_TAG_PREFIX_MAP.keys(), key=len, reverse=True)

# spaCy label → ontology node type (for default NER results, no tag number)
_SPACY_LABEL_MAP: Dict[str, str] = {
    "PERSON": "Personnel",
    "ORG": "Asset",
    "FAC": "Asset",
    "PRODUCT": "Equipment",
    "LOC": "Process",
    "GPE": "Process",
    "WORK_OF_ART": "Document",
}

# EntityRuler patterns covering the most common industrial tag formats
_RULER_PATTERNS = [
    # Standard hyphenated: FT-001, VLV-202, PT-100A
    {
        "label": "INDUSTRIAL_TAG",
        "pattern": [{"TEXT": {"REGEX": r"^[A-Z]{1,4}-\d+[A-Z]?$"}}],
    },
    # Compact (no hyphen, ≥3 digits): TE001, LT100
    {
        "label": "INDUSTRIAL_TAG",
        "pattern": [{"TEXT": {"REGEX": r"^[A-Z]{1,4}\d{3,}[A-Z]?$"}}],
    },
]


def _build_nlp(model_name: str) -> Language:
    nlp = spacy.load(model_name, exclude=["parser", "lemmatizer"])
    if "entity_ruler" not in nlp.pipe_names:
        ruler: EntityRuler = nlp.add_pipe(  # type: ignore[assignment]
            "entity_ruler", before="ner"
        )
        ruler.add_patterns(_RULER_PATTERNS)  # type: ignore[arg-type]
    return nlp


def _classify_tag(text: str) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Return (entity_type, canonical_tag, measurement_type, equipment_class)."""
    upper = text.upper().strip()
    for prefix in _SORTED_PREFIXES:
        pat = re.compile(rf"^{re.escape(prefix)}[-\s]?\d", re.IGNORECASE)
        if pat.match(upper):
            etype, mtype, eclass = _TAG_PREFIX_MAP[prefix]
            return etype, upper, mtype, eclass
    return "Equipment", upper, None, "general"


class SpacyEntityExtractor(IEntityExtractor):
    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        try:
            self._nlp = _build_nlp(model_name)
            logger.info("SpacyEntityExtractor: loaded model '%s'.", model_name)
        except OSError:
            logger.warning(
                "spaCy model '%s' not found; falling back to en_core_web_sm.",
                model_name,
            )
            self._nlp = _build_nlp("en_core_web_sm")

    def extract(self, chunk: DocumentChunk) -> List[ExtractedEntity]:
        if not chunk.text or not chunk.text.strip():
            return []
        doc = self._nlp(chunk.text)
        entities: List[ExtractedEntity] = []
        seen_spans: set = set()
        for ent in doc.ents:
            span_key = (ent.start_char, ent.end_char)
            if span_key in seen_spans:
                continue
            seen_spans.add(span_key)
            entity = self._convert(ent, chunk.id)
            if entity is not None:
                entities.append(entity)
        return entities

    def _convert(self, ent, chunk_id: str) -> Optional[ExtractedEntity]:
        text = ent.text.strip()
        if not text:
            return None

        if ent.label_ == "INDUSTRIAL_TAG":
            etype, tag_number, mtype, eclass = _classify_tag(text)
            props: Dict = {}
            if eclass:
                props["equipment_class"] = eclass
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
                start_char=ent.start_char,
                end_char=ent.end_char,
            )

        return None
