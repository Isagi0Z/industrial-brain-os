"""LLM-as-a-judge (M16, architecture §5, ADR-020).

Wraps the shared model gateway with version-controlled prompt templates to
answer the two boolean judging questions (faithfulness, relevance). Both
methods degrade to a conservative ``False`` on any error rather than raise,
so a judge outage never aborts an evaluation run.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from app.domain.chat.interfaces import IModelGateway
from app.domain.evaluation.interfaces import IEvaluationJudge

logger = logging.getLogger(__name__)


def _parse_yes(text: str) -> bool:
    """Interpret a judge response as a boolean — True only when the answer
    clearly begins with 'yes' (the prompts require a yes/no first token)."""
    if not text:
        return False
    token = text.strip().lower().lstrip("*_-# ").split()
    return bool(token) and token[0].startswith("yes")


def _load_prompt(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class LLMJudge(IEvaluationJudge):
    def __init__(
        self,
        gateway: IModelGateway,
        faithfulness_prompt_path: Path,
        relevance_prompt_path: Path,
        max_tokens: int = 64,
    ) -> None:
        self._gateway = gateway
        self._faith_prompt = _load_prompt(faithfulness_prompt_path)
        self._rel_prompt = _load_prompt(relevance_prompt_path)
        self._max_tokens = max_tokens

    async def judge_faithfulness(self, answer: str, context: str) -> bool:
        user = self._faith_prompt.get("user_template", "{answer}\n{context}").format(
            answer=answer, context=context or "(no retrieved context)"
        )
        return await self._ask(self._faith_prompt.get("system", ""), user)

    async def judge_relevance(self, chunk_text: str, expected_answer: str) -> bool:
        user = self._rel_prompt.get(
            "user_template", "{chunk_text}\n{expected_answer}"
        ).format(chunk_text=chunk_text, expected_answer=expected_answer)
        return await self._ask(self._rel_prompt.get("system", ""), user)

    async def _ask(self, system: str, user: str) -> bool:
        try:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            text, _, _ = await self._gateway.generate(messages, self._max_tokens)
            return _parse_yes(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM judge call failed — defaulting to False: %s", exc)
            return False
