"""Shared OCR engine for the parsing layer.

Single seam every parser OCRs through, with graceful engine selection:

1. **PaddleOCR** when installed (the original integration).
2. **EasyOCR** as the portable fallback — pure-Python install on top of the
   torch runtime the platform already ships for embeddings, with multilingual
   model packs (``OCR_LANGUAGES``, default ``en,hi`` — English + Hindi;
   EasyOCR restricts non-Latin scripts to *one per reader*, so Tamil is a
   config swap: ``OCR_LANGUAGES=en,ta``).
3. **None** — callers degrade exactly as before (figure chunks), never fail.

Engines are lazy-loaded on first use (they cost hundreds of MB of RAM), only
inside the ingestion worker path, and cached for the process lifetime.
"""

from __future__ import annotations

import io
import logging
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_engine = None  # resolved lazily: "paddle" | "easyocr" | "none"
_paddle = None
_easy_latin = None  # English-only reader — best Latin accuracy
_easy_indic = None  # optional hi/ta reader — merged for Indic-script lines


def _resolve_languages() -> List[str]:
    from app.infrastructure.config.settings import settings

    raw = getattr(settings, "OCR_LANGUAGES", "en,hi") or "en"
    return [p.strip() for p in raw.split(",") if p.strip()]


def _load_engine() -> str:
    """Detect and initialise the best available OCR engine (once)."""
    global _engine, _paddle, _easy_latin, _easy_indic
    if _engine is not None:
        return _engine

    with _lock:
        if _engine is not None:
            return _engine

        # 1. PaddleOCR (original integration) — optional heavyweight.
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]

            _paddle = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            _engine = "paddle"
            logger.info("OCR engine: PaddleOCR")
            return _engine
        except Exception:  # noqa: BLE001 - optional dependency
            pass

        # 2. EasyOCR — rides the existing torch runtime; multilingual packs.
        # A mixed-script reader noticeably degrades Latin accuracy, so we run a
        # DUAL-READER strategy: the English reader handles every page (best
        # Latin quality) and, when a non-Latin language is configured, a second
        # Indic reader contributes only the lines written in that script.
        try:
            import easyocr  # type: ignore[import-not-found]

            _easy_latin = easyocr.Reader(["en"], gpu=False, verbose=False)
            indic = [lang for lang in _resolve_languages() if lang in ("hi", "ta")]
            if indic:
                try:
                    _easy_indic = easyocr.Reader(
                        [indic[0], "en"], gpu=False, verbose=False
                    )
                except Exception:  # noqa: BLE001 - model pack unavailable
                    logger.warning(
                        "EasyOCR Indic reader (%s) unavailable — Latin-only OCR.",
                        indic[0],
                    )
            _engine = "easyocr"
            logger.info(
                "OCR engine: EasyOCR (latin + %s)",
                indic[0] if indic and _easy_indic else "no indic",
            )
            return _engine
        except Exception as exc:  # noqa: BLE001 - optional dependency
            logger.warning(
                "No OCR engine available (%s) — images become figure chunks.", exc
            )

        _engine = "none"
        return _engine


def _is_indic(text: str) -> bool:
    """True when the line is predominantly Devanagari or Tamil script."""
    indic = sum(1 for ch in text if "ऀ" <= ch <= "ॿ" or "஀" <= ch <= "௿")
    letters = sum(1 for ch in text if ch.isalpha())
    return letters > 0 and indic / letters > 0.5


def ocr_available() -> bool:
    return _load_engine() != "none"


def _to_rgb_array(image_bytes: bytes):
    """Normalise any image format to an RGB numpy array (TIFF/BMP/WEBP safe)."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.array(img)


def ocr_image(image_bytes: bytes) -> Optional[str]:
    """Run OCR on an image, returning extracted text lines joined by newlines,
    or ``None`` when no engine is available / nothing was recognised."""
    engine = _load_engine()
    if engine == "none":
        return None

    try:
        arr = _to_rgb_array(image_bytes)
    except Exception:  # noqa: BLE001 - undecodable image
        return None

    try:
        lines: List[str] = []
        if engine == "paddle" and _paddle is not None:
            result = _paddle.ocr(arr, cls=True)
            if result and result[0]:
                for line in result:
                    for item in line:
                        txt = (item[1][0] or "").strip()
                        if txt:
                            lines.append(txt)
        elif engine == "easyocr" and _easy_latin is not None:
            # Pass 1 — English reader: authoritative for Latin text. When an
            # Indic reader is active, long letter-less digit runs are almost
            # always Devanagari/Tamil misread as numerals — drop them here and
            # let pass 2 recover the real script.
            for txt in _easy_latin.readtext(arr, detail=0, paragraph=True):
                txt = (txt or "").strip()
                if not txt or _is_indic(txt):
                    continue
                if _easy_indic is not None:
                    digits = sum(ch.isdigit() for ch in txt)
                    letters = sum(ch.isalpha() for ch in txt)
                    if digits >= 8 and letters == 0:
                        continue
                lines.append(txt)
            # Pass 2 — Indic reader (when configured): contributes only the
            # lines actually written in the Indic script, so mixed pages keep
            # accurate English AND readable Hindi/Tamil.
            if _easy_indic is not None:
                for txt in _easy_indic.readtext(arr, detail=0, paragraph=True):
                    txt = (txt or "").strip()
                    if txt and _is_indic(txt):
                        lines.append(txt)
        return "\n".join(lines) if lines else None
    except Exception as exc:  # noqa: BLE001 - OCR must never break ingestion
        logger.warning("OCR failed on image (%s) — falling back to figure chunk.", exc)
        return None
