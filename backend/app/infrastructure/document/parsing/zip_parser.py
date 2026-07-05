"""ZIP parser: expands a mixed archive and routes each entry to the correct leaf
parser, concatenating the results with a per-file heading so the document
hierarchy is preserved. Guards against zip bombs (entry count + uncompressed
size caps) and does not recurse into nested archives.
"""

from __future__ import annotations

import io
import logging
import uuid
import zipfile
from datetime import datetime, timezone
from typing import List

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IDocumentParser
from app.domain.document.mime import resolve_mime
from app.domain.document.models import DocumentChunk
from app.infrastructure.document.parsing.chunker import count_tokens

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 200
_MAX_TOTAL_BYTES = 200 * 1024 * 1024  # uncompressed cap (zip-bomb guard)


class ZipParser(IDocumentParser):
    def __init__(self, leaf_parsers: List[IDocumentParser]) -> None:
        # Leaf parsers only (no ZipParser) so nested archives cannot recurse.
        self._leaf = list(leaf_parsers)

    def can_parse(self, mime_type: str) -> bool:
        return (mime_type or "").split(";")[0].strip() == "application/zip"

    def parse(
        self,
        document_id: str,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
    ) -> List[DocumentChunk]:
        now = datetime.now(timezone.utc)
        try:
            zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        except zipfile.BadZipFile:
            return [
                self._note(document_id, 0, f"[Invalid ZIP archive: {filename}]", now)
            ]

        names = [n for n in zf.namelist() if not n.endswith("/")][:_MAX_ENTRIES]
        out: List[DocumentChunk] = []
        idx = 0
        total = 0

        for name in names:
            try:
                data = zf.read(name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("zip entry %s unreadable: %s", name, exc)
                continue
            total += len(data)
            if total > _MAX_TOTAL_BYTES:
                logger.warning("zip %s exceeds uncompressed cap; stopping", document_id)
                break

            inner_mime = resolve_mime("", name, data[:64])
            if inner_mime == "application/zip":
                continue  # no nested-archive recursion
            parser = next((p for p in self._leaf if p.can_parse(inner_mime)), None)
            if parser is None:
                continue
            try:
                inner = parser.parse(
                    document_id=document_id,
                    filename=name,
                    mime_type=inner_mime,
                    file_bytes=data,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("zip entry %s parse failed: %s", name, exc)
                continue
            if not inner:
                continue

            out.append(
                self._note(document_id, idx, f"File: {name}", now, ChunkType.HEADING)
            )
            idx += 1
            for c in inner:
                out.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        chunk_index=idx,
                        chunk_type=c.chunk_type,
                        text=c.text,
                        page_number=c.page_number,
                        parent_section_header=c.parent_section_header or name,
                        bbox_json=c.bbox_json,
                        token_count=c.token_count,
                        created_at=now,
                        table_data_json=c.table_data_json,
                        figure_storage_key=c.figure_storage_key,
                    )
                )
                idx += 1

        if not out:
            out.append(
                self._note(
                    document_id, 0, f"[Empty or unsupported ZIP: {filename}]", now
                )
            )
        return out

    @staticmethod
    def _note(document_id, idx, text, now, ctype=ChunkType.PARAGRAPH) -> DocumentChunk:
        return DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            chunk_index=idx,
            chunk_type=ctype,
            text=text,
            page_number=None,
            parent_section_header=None,
            bbox_json=None,
            token_count=count_tokens(text),
            created_at=now,
        )
