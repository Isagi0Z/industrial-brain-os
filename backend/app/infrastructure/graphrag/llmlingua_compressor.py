"""LLMLingua context compressor — Stage 7 of the 8-stage hybrid retrieval
pipeline (M14, architecture §4).

Compresses the assembled, source-numbered context before the LLM call,
stripping low-information tokens to save context window (target: keep ~70%
of tokens). Degrades gracefully on every axis so the pipeline always ships:

- If ``llmlingua`` is not installed, or the compression model cannot be
  loaded (e.g. offline / no model cache), compression becomes a labelled
  no-op passthrough (``was_compressed=False``, ``ratio=1.0``). This mirrors
  the guarded-import pattern used by the embedding service and PaddleOCR.
- If the context is below ``min_tokens``, compression is skipped to avoid
  over-compressing small results (checklist requirement).
- Any runtime error during compression falls back to passthrough.

Token counting uses ``tiktoken`` (already a project dependency) when
available, else a ~4-chars-per-token approximation.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.domain.graphrag.interfaces import IContextCompressor
from app.domain.graphrag.models import CompressionResult

logger = logging.getLogger(__name__)

_APPROX_CHARS_PER_TOKEN = 4

# tiktoken for accurate token counts (optional).
try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_ENCODING.encode(text))

except Exception:  # pragma: no cover - tiktoken always present in this project

    def _count_tokens(text: str) -> int:
        return len(text) // _APPROX_CHARS_PER_TOKEN


class LLMLinguaCompressor(IContextCompressor):
    """LLMLingua-2 backed compressor with lazy model loading and graceful
    degradation. The model is loaded on first ``compress`` call, not at
    construction, so a missing model never blocks application startup."""

    def __init__(
        self,
        model_name: str,
        use_llmlingua2: bool = True,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._use_llmlingua2 = use_llmlingua2
        # LLMLingua's PromptCompressor defaults to CUDA; pin the device so the
        # model loads on CPU-only deployments (device_map is required — without
        # it the load raises "Torch not compiled with CUDA enabled").
        self._device = device
        self._compressor: Optional[object] = None
        self._load_attempted = False
        self._available = False

    def _ensure_loaded(self) -> bool:
        """Lazily load the PromptCompressor. Returns True if usable."""
        if self._load_attempted:
            return self._available
        self._load_attempted = True
        try:
            from llmlingua import PromptCompressor

            logger.info("Loading LLMLingua compressor model %s …", self._model_name)
            self._compressor = PromptCompressor(
                model_name=self._model_name,
                use_llmlingua2=self._use_llmlingua2,
                device_map=self._device,
            )
            self._available = True
            logger.info("LLMLingua compressor ready.")
        except Exception as exc:
            logger.warning(
                "LLMLingua unavailable — Stage 7 compression will pass through: %s",
                exc,
            )
            self._available = False
        return self._available

    def compress(
        self, context: str, target_ratio: float, min_tokens: int
    ) -> CompressionResult:
        original_tokens = _count_tokens(context)

        # Skip small contexts (avoid over-compression on sparse results).
        if not context.strip() or original_tokens < min_tokens:
            return CompressionResult(
                compressed_text=context,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                ratio=1.0,
                was_compressed=False,
            )

        if not self._ensure_loaded() or self._compressor is None:
            return CompressionResult(
                compressed_text=context,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                ratio=1.0,
                was_compressed=False,
            )

        try:
            result = self._compressor.compress_prompt(  # type: ignore[attr-defined]
                context,
                rate=target_ratio,
                force_tokens=["\n", ".", "[", "]", "source"],
                drop_consecutive=True,
            )
            compressed_text = result.get("compressed_prompt", context)
            compressed_tokens = int(
                result.get("compressed_tokens", _count_tokens(compressed_text))
            )
            origin_tokens = int(result.get("origin_tokens", original_tokens))
            ratio = (
                round(compressed_tokens / origin_tokens, 4) if origin_tokens else 1.0
            )
            logger.info(
                "Stage 7 compression applied",
                extra={
                    "original_tokens": origin_tokens,
                    "compressed_tokens": compressed_tokens,
                    "ratio": ratio,
                },
            )
            return CompressionResult(
                compressed_text=compressed_text,
                original_tokens=origin_tokens,
                compressed_tokens=compressed_tokens,
                ratio=ratio,
                was_compressed=True,
            )
        except Exception as exc:
            logger.warning("Stage 7 compression failed — passing through: %s", exc)
            return CompressionResult(
                compressed_text=context,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                ratio=1.0,
                was_compressed=False,
            )
