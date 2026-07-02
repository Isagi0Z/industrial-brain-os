"""Golden dataset loader (M16). Reads ``datasets/golden_qa.json`` into
domain ``GoldenQAItem`` objects; shared by the `/eval/run` endpoint and the
`make eval` script.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from app.domain.evaluation.models import GoldenQAItem


def load_golden_dataset(path: Path) -> List[GoldenQAItem]:
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return [
        GoldenQAItem(
            question=item["question"],
            expected_answer=item["expected_answer"],
            source_document_id=item["source_document_id"],
            source_page=item.get("source_page"),
            expected_entity_mentions=list(item.get("expected_entity_mentions") or []),
            category=item.get("category", "general"),
        )
        for item in raw
    ]
