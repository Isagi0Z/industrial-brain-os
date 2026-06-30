"""XLSX parser using openpyxl. Each sheet becomes a table chunk."""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from typing import List

import openpyxl

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IDocumentParser
from app.domain.document.models import DocumentChunk
from app.infrastructure.document.parsing.chunker import count_tokens, finalize_chunks


class XlsxParser(IDocumentParser):
    def can_parse(self, mime_type: str) -> bool:
        return mime_type in {
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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

        wb = openpyxl.load_workbook(
            io.BytesIO(file_bytes), read_only=True, data_only=True
        )
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            table_data = []
            text_rows = []

            for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
                for c_idx, cell_val in enumerate(row):
                    if cell_val is not None:
                        value_str = str(cell_val).strip()
                        if value_str:
                            table_data.append(
                                {"row": r_idx, "col": c_idx, "value": value_str}
                            )

                row_texts = [str(c) for c in row if c is not None and str(c).strip()]
                if row_texts:
                    text_rows.append(" | ".join(row_texts))

            if not text_rows:
                continue

            text = f"Sheet: {sheet_name}\n" + "\n".join(text_rows)
            raw.append(
                DocumentChunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    chunk_index=len(raw),
                    chunk_type=ChunkType.TABLE,
                    text=text,
                    page_number=None,
                    parent_section_header=f"Sheet: {sheet_name}",
                    bbox_json=None,
                    token_count=count_tokens(text),
                    created_at=now,
                    table_data_json=table_data,
                )
            )
        wb.close()

        return finalize_chunks(raw)
