"""Entity resolution with two deduplication passes.

Pass 1 — Tag-number resolution (all entity types):
  Two entities of the same type whose tag numbers are within Levenshtein
  distance ≤ 2 are merged. The shorter (more canonical) tag is kept.

Pass 2 — Manufacturer + model_number resolution (Equipment only):
  Two Equipment entities with both manufacturer AND model_number set,
  whose combined key matches exactly, are merged even if their tag numbers
  differ. The entity with the shorter tag number is kept as canonical.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from rapidfuzz.distance import Levenshtein

from app.domain.extraction.interfaces import IEntityResolver
from app.domain.extraction.models import ExtractedEntity

logger = logging.getLogger(__name__)

_MAX_TAG_DISTANCE = 2


def _tag_key(entity: ExtractedEntity) -> Optional[str]:
    return entity.tag_number


def _mfr_model_key(entity: ExtractedEntity) -> Optional[Tuple[str, str]]:
    """Return (manufacturer, model_number) if both are present, else None."""
    mfr = entity.manufacturer or entity.properties.get("manufacturer")
    model = entity.model_number or entity.properties.get("model_number")
    if mfr and model:
        return (str(mfr).strip().upper(), str(model).strip().upper())
    return None


def _merge(canonical: ExtractedEntity, duplicate: ExtractedEntity) -> None:
    """Merge duplicate's properties into canonical in-place."""
    # Keep the shorter tag as canonical
    if (
        canonical.tag_number
        and duplicate.tag_number
        and len(duplicate.tag_number) < len(canonical.tag_number)
    ):
        canonical.tag_number = duplicate.tag_number
        canonical.text = duplicate.text
    # Merge properties (canonical takes precedence on collision)
    for k, v in duplicate.properties.items():
        if k not in canonical.properties:
            canonical.properties[k] = v
    # Propagate manufacturer/model if canonical lacks them
    if not canonical.manufacturer and duplicate.manufacturer:
        canonical.manufacturer = duplicate.manufacturer
    if not canonical.model_number and duplicate.model_number:
        canonical.model_number = duplicate.model_number


class LevenshteinEntityResolver(IEntityResolver):
    def resolve(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        if not entities:
            return []

        tagged = [e for e in entities if e.tag_number]
        untagged = [e for e in entities if not e.tag_number]

        resolved = self._resolve_by_tag(tagged)
        resolved = self._resolve_by_manufacturer_model(resolved)

        return resolved + untagged

    # ------------------------------------------------------------------
    # Pass 1 — tag number Levenshtein
    # ------------------------------------------------------------------

    def _resolve_by_tag(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        canonical: List[ExtractedEntity] = []
        for entity in entities:
            merged = False
            for canon in canonical:
                if canon.entity_type != entity.entity_type:
                    continue
                assert canon.tag_number and entity.tag_number
                dist = Levenshtein.distance(canon.tag_number, entity.tag_number)
                if dist <= _MAX_TAG_DISTANCE:
                    _merge(canon, entity)
                    logger.debug(
                        "Tag resolution: merged '%s' → '%s' (dist=%d)",
                        entity.tag_number,
                        canon.tag_number,
                        dist,
                    )
                    merged = True
                    break
            if not merged:
                canonical.append(entity)
        return canonical

    # ------------------------------------------------------------------
    # Pass 2 — manufacturer + model_number exact match (Equipment only)
    # ------------------------------------------------------------------

    def _resolve_by_manufacturer_model(
        self, entities: List[ExtractedEntity]
    ) -> List[ExtractedEntity]:
        equipment = [e for e in entities if e.entity_type == "Equipment"]
        other = [e for e in entities if e.entity_type != "Equipment"]

        canonical: List[ExtractedEntity] = []
        for entity in equipment:
            key = _mfr_model_key(entity)
            if key is None:
                canonical.append(entity)
                continue
            merged = False
            for canon in canonical:
                if _mfr_model_key(canon) == key:
                    _merge(canon, entity)
                    logger.debug(
                        "Mfr+model resolution: merged tag '%s' → '%s' (key=%s)",
                        entity.tag_number,
                        canon.tag_number,
                        key,
                    )
                    merged = True
                    break
            if not merged:
                canonical.append(entity)

        return canonical + other
