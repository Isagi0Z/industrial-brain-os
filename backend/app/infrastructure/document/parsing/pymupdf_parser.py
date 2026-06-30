"""PyMuPDF-based layout-aware PDF parser.

Uses PyMuPDF (fitz) block-level extraction as the layout detection engine —
the ADR-012-approved 'equivalent open model' to LayoutParser/PubLayNet for
standard PDF documents. Provides:
  - Block type detection (text=0, image=1)
  - Font-size-based heading classification
  - Bounding-box metadata per chunk
  - PaddleOCR fallback for image-heavy / scanned pages
"""

from __future__ import annotations

import io
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from app.domain.document.constants import LAYOUT_CONFIDENCE_THRESHOLD, ChunkType
from app.domain.document.interfaces import IDocumentParser
from app.domain.document.models import DocumentChunk
from app.infrastructure.document.parsing.chunker import count_tokens, finalize_chunks

logger = logging.getLogger(__name__)

_HEADING_FONT_RATIO = (
    1.2  # block avg font-size / page median font-size > this → heading
)
_MIN_TEXT_CHARS = 10  # blocks shorter than this are skipped as noise
_FOOTER_Y_FRACTION = 0.92  # blocks starting below 92% of page height → footer

try:
    from paddleocr import PaddleOCR

    _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    _PADDLE_AVAILABLE = True
    logger.info("PaddleOCR loaded successfully.")
except Exception:
    _paddle_ocr = None
    _PADDLE_AVAILABLE = False
    logger.warning(
        "PaddleOCR not available — image pages will be stored as figure chunks."
    )


def _median(values: List[float]) -> float:
    if not values:
        return 12.0
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _bbox_to_dict(rect) -> dict:
    return {"x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1}


def _block_text(block: dict) -> str:
    """Assemble text from span objects inside a PyMuPDF dict-mode block."""
    parts = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            t = span.get("text", "").strip()
            if t:
                parts.append(t)
    return " ".join(parts)


def _classify_block(
    block: dict,
    median_font_size: float,
    page_height: float,
) -> Tuple[ChunkType, float]:
    """
    Classify a PyMuPDF text block.
    Returns (ChunkType, confidence) where confidence ≥ LAYOUT_CONFIDENCE_THRESHOLD
    means we trust the classification; otherwise caller falls back.
    """
    text = _block_text(block)
    y0 = block["bbox"][1]

    if y0 / page_height > _FOOTER_Y_FRACTION and len(text) < 120:
        return ChunkType.FOOTER, 0.85

    spans = [s for line in block.get("lines", []) for s in line.get("spans", [])]
    if not spans:
        return ChunkType.PARAGRAPH, 0.60

    avg_size = sum(s.get("size", 12) for s in spans) / len(spans)
    ratio = avg_size / median_font_size if median_font_size else 1.0

    if ratio >= _HEADING_FONT_RATIO:
        return ChunkType.HEADING, min(0.95, 0.75 + (ratio - _HEADING_FONT_RATIO) * 0.2)

    if re.match(r"^\s*(\d+[.)]\s|[-•*]\s)", text):
        return ChunkType.LIST_ITEM, 0.80

    return ChunkType.PARAGRAPH, 0.80


def _ocr_image_page(page: fitz.Page) -> Optional[str]:
    if not _PADDLE_AVAILABLE or _paddle_ocr is None:
        return None
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    result = _paddle_ocr.ocr(img_bytes, cls=True)
    if not result or not result[0]:
        return None
    lines = [item[1][0] for line in result for item in line if item[1][0].strip()]
    return "\n".join(lines)


class PyMuPDFParser(IDocumentParser):
    """Layout-aware parser for PDF files using PyMuPDF block detection."""

    def can_parse(self, mime_type: str) -> bool:
        return mime_type == "application/pdf"

    def parse(
        self,
        document_id: str,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
    ) -> List[DocumentChunk]:
        now = datetime.now(timezone.utc)
        raw: List[DocumentChunk] = []
        current_heading: Optional[str] = None

        doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        try:
            for page_num, page in enumerate(doc, start=1):
                page_dict = page.get_text("dict")
                page_height = page.rect.height

                # Collect font sizes across all spans for median
                all_sizes: List[float] = [
                    s.get("size", 12)
                    for block in page_dict.get("blocks", [])
                    if block.get("type") == 0
                    for line in block.get("lines", [])
                    for s in line.get("spans", [])
                ]
                median_size = _median(all_sizes)

                # Detect image-only page (no text blocks with real content)
                text_content = page.get_text("text").strip()
                is_image_page = len(text_content) < _MIN_TEXT_CHARS

                if is_image_page:
                    ocr_text = _ocr_image_page(page)
                    if ocr_text:
                        raw.append(
                            DocumentChunk(
                                id=str(uuid.uuid4()),
                                document_id=document_id,
                                chunk_index=len(raw),
                                chunk_type=ChunkType.PARAGRAPH,
                                text=ocr_text,
                                page_number=page_num,
                                parent_section_header=current_heading,
                                bbox_json=_bbox_to_dict(page.rect),
                                token_count=count_tokens(ocr_text),
                                created_at=now,
                            )
                        )
                    else:
                        raw.append(
                            DocumentChunk(
                                id=str(uuid.uuid4()),
                                document_id=document_id,
                                chunk_index=len(raw),
                                chunk_type=ChunkType.FIGURE,
                                text=f"[Image page {page_num}]",
                                page_number=page_num,
                                parent_section_header=current_heading,
                                bbox_json=_bbox_to_dict(page.rect),
                                token_count=4,
                                created_at=now,
                            )
                        )
                    continue

                for block in page_dict.get("blocks", []):
                    if block.get("type") == 1:
                        # Embedded image block — store as figure
                        raw.append(
                            DocumentChunk(
                                id=str(uuid.uuid4()),
                                document_id=document_id,
                                chunk_index=len(raw),
                                chunk_type=ChunkType.FIGURE,
                                text=f"[Figure on page {page_num}]",
                                page_number=page_num,
                                parent_section_header=current_heading,
                                bbox_json=_bbox_to_dict(fitz.Rect(block["bbox"])),
                                token_count=4,
                                created_at=now,
                            )
                        )
                        continue

                    if block.get("type") != 0:
                        continue

                    text = _block_text(block)
                    if len(text) < _MIN_TEXT_CHARS:
                        continue

                    chunk_type, confidence = _classify_block(
                        block, median_size, page_height
                    )
                    if confidence < LAYOUT_CONFIDENCE_THRESHOLD:
                        chunk_type = ChunkType.PARAGRAPH

                    if chunk_type == ChunkType.HEADING:
                        current_heading = text

                    raw.append(
                        DocumentChunk(
                            id=str(uuid.uuid4()),
                            document_id=document_id,
                            chunk_index=len(raw),
                            chunk_type=chunk_type,
                            text=text,
                            page_number=page_num,
                            parent_section_header=(
                                current_heading
                                if chunk_type != ChunkType.HEADING
                                else None
                            ),
                            bbox_json=_bbox_to_dict(fitz.Rect(block["bbox"])),
                            token_count=count_tokens(text),
                            created_at=now,
                        )
                    )
        finally:
            doc.close()

        return finalize_chunks(raw)
