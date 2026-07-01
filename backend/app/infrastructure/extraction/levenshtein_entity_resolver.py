"""Entity resolution via Levenshtein distance on tag numbers.

Two entities with the same type and tag numbers within edit distance ≤ 2
are considered the same entity. The canonical form (shortest text) is kept.
"""

from __future__ import annotations

import logging
from typing import List

from rapidfuzz.distance import Levenshtein

from app.domain.extraction.interfaces import IEntityResolver
from app.domain.extraction.models import ExtractedEntity

logger = logging.getLogger(__name__)

_MAX_DISTANCE = 2


class LevenshteinEntityResolver(IEntityResolver):
    def resolve(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        if not entities:
            return []

        # Only resolve entities that have a tag_number
        tagged = [e for e in entities if e.tag_number]
        untagged = [e for e in entities if not e.tag_number]

        canonical: List[ExtractedEntity] = []

        for entity in tagged:
            merged = False
            for canon in canonical:
                if canon.entity_type != entity.entity_type:
                    continue
                assert canon.tag_number is not None
                assert entity.tag_number is not None
                dist = Levenshtein.distance(canon.tag_number, entity.tag_number)
                if dist <= _MAX_DISTANCE:
                    # Keep the shorter (more canonical) tag
                    if len(entity.tag_number) < len(canon.tag_number):
                        canon.tag_number = entity.tag_number
                        canon.text = entity.text
                    merged = True
                    logger.debug(
                        "Resolved '%s' → '%s' (distance=%d)",
                        entity.tag_number,
                        canon.tag_number,
                        dist,
                    )
                    break
            if not merged:
                canonical.append(entity)

        return canonical + untagged
