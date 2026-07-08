"""Image parser (PNG/JPEG/TIFF/...) — OCR via the shared engine seam
(PaddleOCR -> EasyOCR -> figure-chunk fallback)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IDocumentParser
from app.domain.document.models import DocumentChunk
from app.infrastructure.document.parsing.chunker import count_tokens, finalize_chunks
from app.infrastructure.document.parsing.ocr_engine import ocr_image

logger = logging.getLogger(__name__)

_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/webp",
}


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

        text = ocr_image(file_bytes)
        if text:
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
