"""Sentence-transformers embedding service (1024-dim).

The model is configurable via ``EMBEDDING_MODEL`` — default is the English
``BAAI/bge-large-en-v1.5``; set ``BAAI/bge-m3`` (same 1024-dim) for
cross-language dense retrieval (re-embed existing documents after switching).

TF must be disabled before this module is imported — set USE_TF=0 in the
environment. The sentence-transformers library is compatible with PyTorch only
in this configuration.
"""

from __future__ import annotations

import logging
import os
from typing import List

from app.domain.search.interfaces import IEmbeddingService
from app.infrastructure.config.settings import settings

logger = logging.getLogger(__name__)

_MODEL_NAME = settings.EMBEDDING_MODEL
_VECTOR_DIM = 1024

# Disable TF backend before importing sentence-transformers.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

try:
    import urllib3

    urllib3.disable_warnings()
    import requests as _req

    _orig = _req.Session.request

    def _no_ssl_verify(self, method, url, **kwargs):  # type: ignore[override]
        kwargs["verify"] = False
        return _orig(self, method, url, **kwargs)

    _req.Session.request = _no_ssl_verify  # type: ignore[method-assign]

    from sentence_transformers import SentenceTransformer

    _model: SentenceTransformer | None = None

    def _get_model() -> SentenceTransformer:
        global _model
        if _model is None:
            logger.info("Loading embedding model %s …", _MODEL_NAME)
            _model = SentenceTransformer(_MODEL_NAME)
            logger.info(
                "Embedding model loaded, dim=%d",
                _model.get_sentence_embedding_dimension(),
            )
        return _model

    _EMBEDDING_AVAILABLE = True
except Exception as _e:
    logger.warning("sentence-transformers unavailable: %s", _e)
    _EMBEDDING_AVAILABLE = False
    _model = None

    def _get_model():  # type: ignore[misc]
        raise RuntimeError("sentence-transformers not available")


class SentenceTransformerEmbedder(IEmbeddingService):
    """Production embedding service — model loaded once at container startup."""

    def __init__(self) -> None:
        if _EMBEDDING_AVAILABLE:
            _get_model()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        model = _get_model()
        vectors = model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return [v.tolist() for v in vectors]

    def embed_one(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]


VECTOR_DIM: int = _VECTOR_DIM
COLLECTION_NAME: str = "document_chunks"
