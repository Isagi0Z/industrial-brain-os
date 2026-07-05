"""Image parser (PNG/JPEG) using PaddleOCR with PyMuPDF fallback."""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IDocumentParser
from app.domain.document.models import DocumentChunk
from app.infrastructure.document.parsing.chunker import count_tokens, finalize_chunks

logger = logging.getLogger(__name__)

try:
    from paddleocr import PaddleOCR

    _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    _PADDLE_AVAILABLE = True
except Exception:
    _paddle_ocr = None
    _PADDLE_AVAILABLE = False
    logger.warning(
        "PaddleOCR unavailable — image files will produce figure chunks only."
    )


_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/webp",
}


def _to_ocr_input(file_bytes: bytes):
    """Normalise any image format to an RGB numpy array for PaddleOCR (handles
    TIFF/BMP/WEBP that raw bytes may not). Falls back to the raw bytes."""
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        return np.array(img)
    except Exception:  # noqa: BLE001
        return file_bytes


class ImageParser(IDocumentParser):
    def can_parse(self, mime_type: str) -> bool:
        base = (mime_type or "").split(";")[0].strip()
        return base in _IMAGE_MIMES or base.startswith("image/")

    def parse(
        self,
        document_id: str,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
    ) -> List[DocumentChunk]:
        now = datetime.now(timezone.utc)

        if _PADDLE_AVAILABLE and _paddle_ocr is not None:
            result = _paddle_ocr.ocr(_to_ocr_input(file_bytes), cls=True)
            lines = []
            if result and result[0]:
                for line in result:
                    for item in line:
                        txt = item[1][0].strip() if item[1][0] else ""
                        if txt:
                            lines.append(txt)

            if lines:
                text = "\n".join(lines)
                return finalize_chunks(
                    [
                        DocumentChunk(
                            id=str(uuid.uuid4()),
                            document_id=document_id,
                            chunk_index=0,
                            chunk_type=ChunkType.PARAGRAPH,
                            text=text,
                            page_number=1,
                            parent_section_header=None,
                            bbox_json=None,
                            token_count=count_tokens(text),
                            created_at=now,
                        )
                    ]
                )

        # Fallback: figure chunk pointing to stored binary
        return [
            DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                chunk_index=0,
                chunk_type=ChunkType.FIGURE,
                text=f"[Image: {filename}]",
                page_number=1,
                parent_section_header=None,
                bbox_json=None,
                token_count=4,
                created_at=now,
            )
        ]
