"""Ollama model gateway.

Reliability hardening (Performance & Ingestion Upgrade):
- ``keep_alive`` is sent on every request so the model stays resident and does
  not unload after Ollama's default idle timeout (the "disconnects after a few
  minutes" symptom). Verified via ``ollama ps``: expires_at is pushed far out.
- Requests retry with exponential backoff and reconnect when the connection
  drops, so a transient Ollama hiccup or restart recovers automatically. The
  streaming path only retries before the first token is emitted, so a recovered
  request never duplicates output.
- ``warm_up()`` preloads and pins the model at API startup; ``health()`` reports
  availability and whether the target model is present.

A fresh ``httpx.AsyncClient`` is created per call (Ollama calls are seconds
apart, so setup cost is negligible). This deliberately avoids binding a client
to a short-lived event loop: the ingestion worker runs each KG task in its own
``asyncio.run`` loop, and a persistent client bound to that loop would leak and
warn "Event loop is closed".
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union

import httpx

from app.domain.chat.interfaces import IModelGateway
from app.infrastructure.observability.metrics import record_llm_tokens
from app.infrastructure.observability.tracing import set_span_attributes, span

logger = logging.getLogger(__name__)

# Connection-level failures worth retrying (a dropped socket, Ollama still
# spinning the model back up, a brief restart). Not HTTP 4xx/5xx bodies.
_RETRYABLE: tuple = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
    httpx.ReadError,
)


def _parse_keep_alive(value: Union[str, int]) -> Union[int, str]:
    """Ollama accepts keep_alive as a number of seconds (negative = keep the
    model resident indefinitely) OR a Go duration string like "30m"/"24h".
    A bare "-1" is NOT a valid duration string, so numeric input must be sent as
    a JSON number."""
    v = str(value).strip()
    try:
        return int(v)
    except ValueError:
        return v


class OllamaGateway(IModelGateway):
    def __init__(
        self,
        host: str,
        port: int,
        model: str,
        keep_alive: Union[str, int] = "-1",
        num_ctx: int = 4096,
        timeout: float = 180.0,
        max_retries: int = 2,
    ) -> None:
        self._base_url = f"http://{host}:{port}"
        self._model = model
        self._keep_alive = _parse_keep_alive(keep_alive)
        self._num_ctx = num_ctx
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        )

    async def aclose(self) -> None:
        # No persistent client to close (kept for interface compatibility).
        return None

    def _options(self, max_tokens: int) -> Dict[str, Any]:
        return {"num_predict": max_tokens, "num_ctx": self._num_ctx}

    async def _post_with_retry(self, path: str, payload: dict) -> dict:
        """POST with retry/backoff; returns the parsed JSON body."""
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                async with self._new_client() as client:
                    response = await client.post(path, json=payload)
                    response.raise_for_status()
                    return response.json()
            except _RETRYABLE as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    backoff = 0.5 * (2**attempt)
                    logger.warning(
                        "Ollama request to %s failed (attempt %d/%d): %s; retrying in %.1fs",
                        path,
                        attempt + 1,
                        self._max_retries + 1,
                        exc,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def _record_stream_usage(
        self, done_frame: dict, usage_sink: Optional[dict]
    ) -> None:
        """Surface the token counts Ollama reports on the final stream frame so
        the streaming path feeds the same metrics/accounting as generate()."""
        prompt_tokens = int(done_frame.get("prompt_eval_count", 0) or 0)
        completion_tokens = int(done_frame.get("eval_count", 0) or 0)
        record_llm_tokens(self.model_name, prompt_tokens, completion_tokens)
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = prompt_tokens
            usage_sink["completion_tokens"] = completion_tokens

    async def generate_stream(
        self,
        messages: List[dict],
        max_tokens: int,
        usage_sink: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": self._options(max_tokens),
        }
        yielded_any = False
        for attempt in range(self._max_retries + 1):
            try:
                async with self._new_client() as client:
                    async with client.stream(
                        "POST", "/api/chat", json=payload
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
                                yielded_any = True
                                yield content
                            if data.get("done"):
                                self._record_stream_usage(data, usage_sink)
                                return
                return
            except _RETRYABLE as exc:
                # Only retry a stream that failed BEFORE emitting any token, so a
                # recovered request never re-streams already-shown text.
                if not yielded_any and attempt < self._max_retries:
                    backoff = 0.5 * (2**attempt)
                    logger.warning(
                        "Ollama stream failed before first token (attempt %d/%d): %s; retrying in %.1fs",
                        attempt + 1,
                        self._max_retries + 1,
                        exc,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise

    async def generate(
        self, messages: List[dict], max_tokens: int
    ) -> Tuple[str, int, int]:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": self._options(max_tokens),
        }
        t0 = time.monotonic()
        with span("llm.generate", **{"llm.model": self.model_name}):
            data = await self._post_with_retry("/api/chat", payload)
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
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            },
        )
        return full_text, prompt_tokens, completion_tokens

    # ------------------------------------------------------------------
    # Reliability helpers (startup warm-up + health probe)
    # ------------------------------------------------------------------
    async def warm_up(self) -> bool:
        """Preload and pin the model so the first real question is fast and the
        model stays resident. Never raises: if Ollama is down at startup the API
        still boots and recovers on the first successful request."""
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": "ok"}],
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"num_predict": 1, "num_ctx": self._num_ctx},
        }
        try:
            t0 = time.monotonic()
            await self._post_with_retry("/api/chat", payload)
            logger.info(
                "Ollama model '%s' warmed and pinned (keep_alive=%s) in %.1fs",
                self._model,
                self._keep_alive,
                time.monotonic() - t0,
            )
            return True
        except Exception as exc:  # noqa: BLE001 - startup must not fail on Ollama
            logger.warning(
                "Ollama warm-up skipped (model '%s' not reachable): %s",
                self._model,
                exc,
            )
            return False

    async def health(self) -> Dict[str, Any]:
        """Report Ollama availability and whether the target model is present."""
        try:
            async with self._new_client() as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                models = [m.get("name", "") for m in response.json().get("models", [])]
            present = any(self._model in name for name in models)
            return {
                "available": True,
                "target_model": self._model,
                "target_model_present": present,
                "models": models,
            }
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "target_model": self._model, "error": str(exc)}
