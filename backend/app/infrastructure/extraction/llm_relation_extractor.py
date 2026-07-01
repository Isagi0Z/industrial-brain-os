"""LLM-backed relation extractor (ADR-020: version-controlled PromptOps).

Loads relation_extraction.yaml, calls IModelGateway.generate(), and parses the
JSON array response.  Multiple JSON-extraction strategies are tried in order:
  1. Direct json.loads of the trimmed response.
  2. Extract first [...] block by bracket matching (handles spurious text).
  3. Discard markdown fences and retry json.loads.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml  # type: ignore[import-untyped]

from app.domain.chat.interfaces import IModelGateway
from app.domain.document.models import DocumentChunk
from app.domain.extraction.interfaces import IRelationExtractor
from app.domain.extraction.models import ExtractedEntity, ExtractedRelation

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 1024
_MIN_ENTITIES_FOR_LLM = 2  # never call LLM for a single entity


class LLMRelationExtractor(IRelationExtractor):
    def __init__(
        self,
        gateway: IModelGateway,
        prompt_path: Path,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._gateway = gateway
        self._max_tokens = max_tokens
        self._prompt = _load_prompt(prompt_path)

    async def extract(
        self,
        chunk: DocumentChunk,
        entities: List[ExtractedEntity],
    ) -> List[ExtractedRelation]:
        tagged = [e for e in entities if e.tag_number]
        if len(tagged) < _MIN_ENTITIES_FOR_LLM:
            return []

        messages = self._build_messages(chunk, tagged)
        try:
            text, _, _ = await self._gateway.generate(messages, self._max_tokens)
        except Exception as exc:
            logger.warning(
                "LLM call failed for chunk %s: %s — skipping relation extraction.",
                chunk.id,
                exc,
            )
            return []

        return _parse_response(text)

    def _build_messages(
        self, chunk: DocumentChunk, entities: List[ExtractedEntity]
    ) -> List[dict]:
        entity_payload = [
            {"tag_number": e.tag_number, "entity_type": e.entity_type} for e in entities
        ]
        user_content = self._prompt["extraction_template"].format(
            chunk_text=chunk.text[:4000],
            entities_json=json.dumps(entity_payload, indent=2),
        )
        return [
            {"role": "system", "content": self._prompt["system"]},
            {"role": "user", "content": user_content},
        ]


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _load_prompt(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _parse_response(text: str) -> List[ExtractedRelation]:
    """Try three strategies to extract a JSON array from the LLM response."""
    text = text.strip()

    raw = _try_direct(text) or _try_bracket_extract(text) or _try_strip_fences(text)
    if raw is None:
        logger.warning(
            "LLM relation extraction: no JSON array found in response (%.200s)", text
        )
        return []

    if not isinstance(raw, list):
        logger.warning(
            "LLM relation extraction: expected JSON array, got %s", type(raw)
        )
        return []

    relations: List[ExtractedRelation] = []
    for item in raw:
        rel = _item_to_relation(item)
        if rel is not None:
            relations.append(rel)
    return relations


def _try_direct(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _try_bracket_extract(text: str) -> Optional[Any]:
    """Find the first '[' … ']' balanced block and parse it."""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _try_strip_fences(text: str) -> Optional[Any]:
    """Remove ``` fences and retry."""
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _item_to_relation(item: Any) -> Optional[ExtractedRelation]:
    if not isinstance(item, dict):
        return None
    try:
        confidence = float(item.get("confidence", 1.0))
        if confidence < 0.0:
            confidence = 0.0
        elif confidence > 1.0:
            confidence = 1.0
        return ExtractedRelation(
            source_tag=str(item["source_tag"]),
            source_type=str(item["source_type"]),
            relation_type=str(item["relation_type"]),
            target_tag=str(item["target_tag"]),
            target_type=str(item["target_type"]),
            confidence=confidence,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("Skipping malformed relation item %s: %s", item, exc)
        return None
