from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from app.domain.chat.interfaces import IPromptLoader

logger = logging.getLogger(__name__)


class YamlPromptLoader(IPromptLoader):
    def __init__(self, prompt_file: Path) -> None:
        self._data: Optional[dict] = None
        self._path = prompt_file
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as fh:
                self._data = yaml.safe_load(fh)
            logger.info("Prompt file loaded", extra={"path": str(self._path)})
        except FileNotFoundError:
            logger.error(
                "Prompt file not found — using defaults",
                extra={"path": str(self._path)},
            )
            self._data = {}

    def system_prompt(self) -> str:
        if self._data:
            return str(self._data.get("system", _DEFAULT_SYSTEM))
        return _DEFAULT_SYSTEM

    def wrap_context(self, context_text: str) -> str:
        template: str = ""
        if self._data:
            template = str(self._data.get("context_template", ""))
        if template:
            return template.replace("{context_blocks}", context_text)
        return f"=== DOCUMENT CONTEXT ===\n{context_text}\n=== END CONTEXT ==="


_DEFAULT_SYSTEM = (
    "You are an Industrial Knowledge Copilot for an engineering facility. "
    "Answer questions using ONLY the provided document context. "
    "Always cite your sources using [Document Title, p.N] notation. "
    "If the context does not contain the answer, say so clearly."
)
