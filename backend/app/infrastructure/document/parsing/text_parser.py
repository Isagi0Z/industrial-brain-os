"""Text-family parser: plain text, Markdown, CSV/TSV, JSON, XML, HTML, YAML.

One parser covers every plain-text-derived format so we do not duplicate the
paragraph/heading/table chunking logic. Structured formats (CSV/JSON/XML) are
turned into readable, searchable chunks with the right ChunkType and metadata.
Standard library only; no new dependencies.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import List, Optional

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IDocumentParser
from app.domain.document.models import DocumentChunk
from app.infrastructure.document.parsing.chunker import count_tokens, finalize_chunks

logger = logging.getLogger(__name__)

_TEXT_MIMES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/tab-separated-values",
    "application/json",
    "application/xml",
    "text/xml",
    "text/html",
    "application/x-yaml",
    "application/yaml",
    "text/yaml",
}


def _decode(file_bytes: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="ignore")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._parts)


class TextParser(IDocumentParser):
    def can_parse(self, mime_type: str) -> bool:
        base = (mime_type or "").split(";")[0].strip()
        return base in _TEXT_MIMES or base.startswith("text/")

    def parse(
        self,
        document_id: str,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
    ) -> List[DocumentChunk]:
        base = (mime_type or "").split(";")[0].strip()
        text = _decode(file_bytes)
        if base in ("text/csv", "text/tab-separated-values"):
            raw = self._parse_delimited(document_id, text, base)
        elif base == "application/json":
            raw = self._parse_json(document_id, text)
        elif base in ("application/xml", "text/xml"):
            raw = self._parse_xml(document_id, text)
        elif base == "text/html":
            raw = self._parse_paragraphs(document_id, _HTMLTextExtractor_text(text))
        elif base == "text/markdown":
            raw = self._parse_markdown(document_id, text)
        else:  # text/plain, yaml, log, and any text/*
            raw = self._parse_paragraphs(document_id, text)
        return finalize_chunks(raw)

    # -- helpers ---------------------------------------------------------------
    def _chunk(
        self,
        document_id: str,
        idx: int,
        chunk_type: ChunkType,
        text: str,
        header: Optional[str] = None,
        page: Optional[int] = None,
        table_data=None,
    ) -> DocumentChunk:
        return DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            chunk_index=idx,
            chunk_type=chunk_type,
            text=text,
            page_number=page,
            parent_section_header=header,
            bbox_json=None,
            token_count=count_tokens(text),
            created_at=datetime.now(timezone.utc),
            table_data_json=table_data,
        )

    def _parse_paragraphs(self, document_id: str, text: str) -> List[DocumentChunk]:
        blocks = [
            b.strip() for b in text.replace("\r\n", "\n").split("\n\n") if b.strip()
        ]
        if not blocks and text.strip():
            blocks = [text.strip()]
        return [
            self._chunk(document_id, i, ChunkType.PARAGRAPH, b)
            for i, b in enumerate(blocks)
        ]

    def _parse_markdown(self, document_id: str, text: str) -> List[DocumentChunk]:
        chunks: List[DocumentChunk] = []
        current_heading: Optional[str] = None
        buf: List[str] = []
        idx = 0

        def flush() -> None:
            nonlocal idx
            body = "\n".join(buf).strip()
            buf.clear()
            if body:
                chunks.append(
                    self._chunk(
                        document_id,
                        idx,
                        ChunkType.PARAGRAPH,
                        body,
                        header=current_heading,
                    )
                )
                idx += 1

        for line in text.replace("\r\n", "\n").split("\n"):
            if line.lstrip().startswith("#"):
                flush()
                current_heading = line.lstrip("#").strip()
                chunks.append(
                    self._chunk(document_id, idx, ChunkType.HEADING, current_heading)
                )
                idx += 1
            elif not line.strip():
                flush()
            else:
                buf.append(line)
        flush()
        return chunks or self._parse_paragraphs(document_id, text)

    def _parse_delimited(
        self, document_id: str, text: str, base: str
    ) -> List[DocumentChunk]:
        delim = "\t" if base == "text/tab-separated-values" else ","
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        rows = [r for r in reader if any(c.strip() for c in r)]
        if not rows:
            return []
        header = rows[0]
        table_data = []
        lines = []
        for r_idx, row in enumerate(rows):
            for c_idx, value in enumerate(row):
                v = value.strip()
                if v:
                    table_data.append({"row": r_idx, "col": c_idx, "value": v})
            # readable row: "col=value" using header names when available
            named = []
            for c_idx, value in enumerate(row):
                if value.strip():
                    key = (
                        header[c_idx].strip()
                        if r_idx and c_idx < len(header)
                        else f"col{c_idx}"
                    )
                    named.append(f"{key}: {value.strip()}")
            if named:
                lines.append(" | ".join(named))
        text_repr = "\n".join(lines)
        return [
            self._chunk(
                document_id,
                0,
                ChunkType.TABLE,
                text_repr,
                header=None,
                table_data=table_data,
            )
        ]

    def _parse_json(self, document_id: str, text: str) -> List[DocumentChunk]:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return self._parse_paragraphs(document_id, text)
        pretty = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
        # A flat, readable key/value rendering aids retrieval alongside the raw form.
        flat = "\n".join(_flatten_json(obj))
        body = flat if flat else pretty
        return [self._chunk(document_id, 0, ChunkType.PARAGRAPH, body)]

    def _parse_xml(self, document_id: str, text: str) -> List[DocumentChunk]:
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(text)
            parts: List[str] = []
            for elem in root.iter():
                t = (elem.text or "").strip()
                if t:
                    tag = elem.tag.split("}")[-1]
                    parts.append(f"{tag}: {t}")
            body = "\n".join(parts)
            if body:
                return [self._chunk(document_id, 0, ChunkType.PARAGRAPH, body)]
        except Exception as exc:  # noqa: BLE001 - malformed xml falls back to text
            logger.warning("XML parse fallback for %s: %s", document_id, exc)
        return self._parse_paragraphs(document_id, text)


def _HTMLTextExtractor_text(html: str) -> str:
    ex = _HTMLTextExtractor()
    try:
        ex.feed(html)
    except Exception:  # noqa: BLE001
        return html
    return ex.text() or html


def _flatten_json(obj, prefix: str = "") -> List[str]:
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_flatten_json(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_flatten_json(v, f"{prefix}{i}."))
    else:
        out.append(f"{prefix.rstrip('.')}: {obj}")
    return out
