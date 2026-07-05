from __future__ import annotations

import logging
import time
from typing import AsyncGenerator, List, Optional, Tuple

from starlette.concurrency import run_in_threadpool

from app.domain.chat.interfaces import IModelGateway
from app.infrastructure.observability.metrics import record_llm_tokens
from app.infrastructure.observability.tracing import set_span_attributes, span

logger = logging.getLogger(__name__)

_GEMINI_AVAILABLE = False
_genai: Optional[object] = None

try:
    import google.generativeai as _genai_module  # type: ignore[import-untyped]

    _genai = _genai_module
    _GEMINI_AVAILABLE = True
except ImportError:
    logger.warning("google-generativeai not installed — GeminiGateway disabled")


class GeminiGateway(IModelGateway):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._model_id = model
        if _GEMINI_AVAILABLE and _genai is not None:
            _genai.configure(api_key=api_key)  # type: ignore[attr-defined]
            self._model_obj = _genai.GenerativeModel(model)  # type: ignore[attr-defined]
        else:
            self._model_obj = None

    @property
    def model_name(self) -> str:
        return f"gemini/{self._model_id}"

    async def generate_stream(
        self,
        messages: List[dict],
        max_tokens: int,
        usage_sink: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        text, prompt_tokens, completion_tokens = await self.generate(
            messages, max_tokens
        )
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = prompt_tokens
            usage_sink["completion_tokens"] = completion_tokens
        yield text

    async def generate(
        self, messages: List[dict], max_tokens: int
    ) -> Tuple[str, int, int]:
        if not _GEMINI_AVAILABLE or self._model_obj is None:
            raise RuntimeError("google-generativeai is not installed")

        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_parts = [m["content"] for m in messages if m["role"] != "system"]
        system_text = "\n\n".join(system_parts)
        conversation = "\n\n".join(user_parts)

        import google.generativeai as genai  # type: ignore[import-untyped]
        import google.generativeai.types as genai_types  # type: ignore[import-untyped]

        model_with_system = genai.GenerativeModel(
            self._model_id,
            system_instruction=system_text or None,
        )
        gen_config = genai_types.GenerationConfig(max_output_tokens=max_tokens)

        def _call() -> Tuple[str, int, int]:
            response = model_with_system.generate_content(
                conversation, generation_config=gen_config
            )
            usage = response.usage_metadata
            pt = getattr(usage, "prompt_token_count", 0) or 0
            ct = getattr(usage, "candidates_token_count", 0) or 0
            return response.text, pt, ct

        t0 = time.monotonic()
        with span("llm.generate", **{"llm.model": self.model_name}):
            text, pt, ct = await run_in_threadpool(_call)
            set_span_attributes(
                {
                    "llm.prompt_tokens": pt,
                    "llm.completion_tokens": ct,
                    "llm.latency_ms": round((time.monotonic() - t0) * 1000, 1),
                }
            )
        record_llm_tokens(self.model_name, pt, ct)
        logger.info(
            "Gemini generate complete",
            extra={
                "model": self._model_id,
                "prompt_tokens": pt,
                "completion_tokens": ct,
            },
        )
        return text, pt, ct
