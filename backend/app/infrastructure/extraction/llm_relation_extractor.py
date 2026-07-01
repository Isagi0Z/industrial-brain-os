"""LLM-backed relation extractor.

Loads the relation_extraction.yaml prompt (ADR-020), sends a structured
request to the configured IModelGateway, and parses the JSON response.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml  # type: ignore[import-untyped]

from app.domain.chat.interfaces import IModelGateway
from app.domain.document.models import DocumentChunk
from app.domain.extraction.interfaces import IRelationExtractor
from app.domain.extraction.models import ExtractedEntity, ExtractedRelation

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 1024


class LLMRelationExtractor(IRelationExtractor):
    def __init__(
        self,
        gateway: IModelGateway,
        prompt_path: Path,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._gateway = gateway
        self._max_tokens = max_tokens
        self._prompt = self._load_prompt(prompt_path)

    @staticmethod
    def _load_prompt(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data

    def _build_messages(
        self, chunk: DocumentChunk, entities: List[ExtractedEntity]
    ) -> List[dict]:
        entities_payload = [
            {
                "tag_number": e.tag_number,
                "entity_type": e.entity_type,
                "text": e.text,
            }
            for e in entities
            if e.tag_number
        ]
        user_content = self._prompt["extraction_template"].format(
            chunk_text=chunk.text[:4000],
            entities_json=json.dumps(entities_payload, indent=2),
        )
        return [
            {"role": "system", "content": self._prompt["system"]},
            {"role": "user", "content": user_content},
        ]

    async def extract(
        self,
        chunk: DocumentChunk,
        entities: List[ExtractedEntity],
    ) -> List[ExtractedRelation]:
        tagged = [e for e in entities if e.tag_number]
        if len(tagged) < 2:
            return []

        messages = self._build_messages(chunk, tagged)
        try:
            text, _, _ = await self._gateway.generate(messages, self._max_tokens)
            return self._parse_response(text)
        except Exception as exc:
            logger.warning(
                "LLM relation extraction failed for chunk %s: %s", chunk.id, exc
            )
            return []

    @staticmethod
    def _parse_response(text: str) -> List[ExtractedRelation]:
        text = text.strip()
        # Strip markdown fences if the model added them
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(
                "LLM returned non-JSON for relation extraction: %.200s", text
            )
            return []

        if not isinstance(data, list):
            return []

        relations = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                rel = ExtractedRelation(
                    source_tag=str(item["source_tag"]),
                    source_type=str(item["source_type"]),
                    relation_type=str(item["relation_type"]),
                    target_tag=str(item["target_tag"]),
                    target_type=str(item["target_type"]),
                    confidence=float(item.get("confidence", 1.0)),
                )
                relations.append(rel)
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("Skipping malformed relation item: %s", exc)

        return relations
