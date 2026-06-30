"""DOCX parser using python-docx."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from docx import Document as DocxDocument

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IDocumentParser
from app.domain.document.models import DocumentChunk
from app.infrastructure.document.parsing.chunker import count_tokens, finalize_chunks

import io


def _is_heading(paragraph) -> bool:
    style_name = paragraph.style.name if paragraph.style else ""
    return "Heading" in style_name or "Title" in style_name


def _table_to_data(table) -> List[dict]:
    rows = []
    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            text = cell.text.strip()
            if text:
                rows.append({"row": r_idx, "col": c_idx, "value": text})
    return rows


class DocxParser(IDocumentParser):
    def can_parse(self, mime_type: str) -> bool:
        return mime_type in {
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

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

        doc = DocxDocument(io.BytesIO(file_bytes))

        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                from docx.text.paragraph import Paragraph

                para = Paragraph(element, doc)
                text = para.text.strip()
                if not text:
                    continue
                if _is_heading(para):
                    current_heading = text
                    chunk_type = ChunkType.HEADING
                else:
                    chunk_type = ChunkType.PARAGRAPH

                raw.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        chunk_index=len(raw),
                        chunk_type=chunk_type,
                        text=text,
                        page_number=None,
                        parent_section_header=(
                            current_heading if chunk_type != ChunkType.HEADING else None
                        ),
                        bbox_json=None,
                        token_count=count_tokens(text),
                        created_at=now,
                    )
                )

            elif tag == "tbl":
                from docx.table import Table

                table = Table(element, doc)
                table_data = _table_to_data(table)
                table_text = " | ".join(
                    f"[{r['row']},{r['col']}] {r['value']}" for r in table_data
                )
                if not table_text.strip():
                    continue

                raw.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        chunk_index=len(raw),
                        chunk_type=ChunkType.TABLE,
                        text=table_text,
                        page_number=None,
                        parent_section_header=current_heading,
                        bbox_json=None,
                        token_count=count_tokens(table_text),
                        created_at=now,
                        table_data_json=table_data,
                    )
                )

        return finalize_chunks(raw)
