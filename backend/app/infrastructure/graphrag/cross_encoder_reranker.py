"""Cross-encoder reranker (Stage 6) using BAAI/bge-reranker-large.

Mirrors the lazy-load + availability-guard pattern used by
SentenceTransformerEmbedder (M4): the model loads once at first use. If
sentence-transformers or the model weights are unavailable (offline dev
environment, no GPU/network), rerank() degrades to passing candidates
through in their original vector/BM25 score order rather than failing the
whole retrieval pipeline.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Tuple

from app.domain.graphrag.interfaces import ICrossEncoderReranker
from app.domain.search.models import SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_NAME = "BAAI/bge-reranker-large"

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

try:
    import urllib3

    urllib3.disable_warnings()
    import requests as _req  # type: ignore[import-untyped]

    _orig = _req.Session.request

    def _no_ssl_verify(self, method, url, **kwargs):  # type: ignore[override]
        kwargs["verify"] = False
        return _orig(self, method, url, **kwargs)

    _req.Session.request = _no_ssl_verify  # type: ignore[method-assign]

    from sentence_transformers import CrossEncoder

    _model_cache: Dict[str, "CrossEncoder"] = {}

    def _get_model(model_name: str) -> "CrossEncoder":
        if model_name not in _model_cache:
            logger.info("Loading cross-encoder model %s …", model_name)
            _model_cache[model_name] = CrossEncoder(model_name)
            logger.info("Cross-encoder model loaded: %s", model_name)
        return _model_cache[model_name]

    _RERANKER_AVAILABLE = True
except Exception as _e:
    logger.warning("sentence-transformers CrossEncoder unavailable: %s", _e)
    _RERANKER_AVAILABLE = False

    def _get_model(model_name: str):  # type: ignore[misc]
        raise RuntimeError("CrossEncoder not available")


class CrossEncoderReranker(ICrossEncoderReranker):
    """Production reranker — model loaded once at first rerank() call."""

    def __init__(self, model_name: str = _DEFAULT_MODEL_NAME) -> None:
        self._model_name = model_name
        self._available = _RERANKER_AVAILABLE

    def warm_up(self) -> bool:
        """Eagerly load (and cache) the cross-encoder so the first real rerank()
        does not pay the one-time model-load cost (~8s on CPU). Never raises: if
        the model is unavailable the pipeline still degrades gracefully to
        original-score order at query time."""
        if not self._available:
            return False
        try:
            _get_model(self._model_name)
            return True
        except Exception as exc:  # noqa: BLE001 - startup must not fail on this
            logger.warning(
                "Cross-encoder warm-up skipped (model '%s' unavailable): %s",
                self._model_name,
                exc,
            )
            return False

    def rerank(
        self, query: str, candidates: List[SearchResult]
    ) -> List[Tuple[SearchResult, float]]:
        if not candidates:
            return []
        # Bound rerank cost so it does not scale with corpus size. Candidates
        # are already in fused retrieval-score order, so the top N are the ones
        # worth the cross-encoder pass.
        from app.infrastructure.config.settings import settings

        max_n = getattr(settings, "GRAPHRAG_RERANK_MAX_CANDIDATES", 0) or 0
        if max_n and len(candidates) > max_n:
            logger.info(
                "Reranking top %d of %d candidates (bounded).", max_n, len(candidates)
            )
            candidates = candidates[:max_n]
        if not self._available:
            logger.warning(
                "Cross-encoder unavailable — passing %d candidates through "
                "unranked (original retrieval scores retained).",
                len(candidates),
            )
            return [(c, c.score) for c in candidates]

        try:
            model = _get_model(self._model_name)
            pairs = [(query, c.text) for c in candidates]
            scores = model.predict(pairs)
        except Exception as exc:  # noqa: BLE001 - honour the graceful-degradation contract
            # A runtime failure (OOM on a large batch, tokenizer error on
            # pathological text, an evicted model) must degrade to fused order,
            # never fail the whole retrieval / chat turn.
            logger.warning(
                "Cross-encoder rerank failed on %d candidates — falling back to "
                "fused retrieval order: %s",
                len(candidates),
                exc,
            )
            return [(c, c.score) for c in candidates]
        return list(zip(candidates, [float(s) for s in scores]))
