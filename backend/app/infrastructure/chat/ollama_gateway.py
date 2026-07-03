from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator, List, Tuple

import httpx

from app.domain.chat.interfaces import IModelGateway
from app.infrastructure.observability.metrics import record_llm_tokens
from app.infrastructure.observability.tracing import set_span_attributes, span

logger = logging.getLogger(__name__)


class OllamaGateway(IModelGateway):
    def __init__(self, host: str, port: int, model: str) -> None:
        self._base_url = f"http://{host}:{port}"
        self._model = model

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    async def generate_stream(
        self, messages: List[dict], max_tokens: int
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content: str = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break

    async def generate(
        self, messages: List[dict], max_tokens: int
    ) -> Tuple[str, int, int]:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        t0 = time.monotonic()
        with span("llm.generate", **{"llm.model": self.model_name}):
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat", json=payload
                )
                response.raise_for_status()
                data = response.json()
            full_text: str = data.get("message", {}).get("content", "")
            prompt_tokens: int = data.get("prompt_eval_count", 0)
            completion_tokens: int = data.get("eval_count", 0)
            set_span_attributes(
                {
                    "llm.prompt_tokens": prompt_tokens,
                    "llm.completion_tokens": completion_tokens,
                    "llm.latency_ms": round((time.monotonic() - t0) * 1000, 1),
                }
            )
        record_llm_tokens(self.model_name, prompt_tokens, completion_tokens)
        logger.info(
            "Ollama generate complete",
            extra={
                "model": self._model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )
        return full_text, prompt_tokens, completion_tokens
