"""Email parser: .eml via the standard library, .msg via extract-msg (optional).

Preserves the header block (from/to/subject/date) as a heading chunk and the
body as paragraphs, and notes attachment filenames so they remain searchable.
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from typing import List

from app.domain.document.constants import ChunkType
from app.domain.document.interfaces import IDocumentParser
from app.domain.document.models import DocumentChunk
from app.infrastructure.document.parsing.chunker import count_tokens, finalize_chunks

logger = logging.getLogger(__name__)

_MIMES = {"message/rfc822", "application/vnd.ms-outlook"}


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _html_to_text(html: str) -> str:
    s = _Strip()
    try:
        s.feed(html)
    except Exception:  # noqa: BLE001
        return html
    return "\n".join(s.parts)


class EmailParser(IDocumentParser):
    def can_parse(self, mime_type: str) -> bool:
        return (mime_type or "").split(";")[0].strip() in _MIMES

    def parse(
        self,
        document_id: str,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
    ) -> List[DocumentChunk]:
        base = (mime_type or "").split(";")[0].strip()
        if base == "application/vnd.ms-outlook":
            headers, body, attachments = self._parse_msg(file_bytes, filename)
        else:
            headers, body, attachments = self._parse_eml(file_bytes)

        now = datetime.now(timezone.utc)
        raw: List[DocumentChunk] = []
        header_text = "\n".join(f"{k}: {v}" for k, v in headers.items() if v)
        subject = headers.get("Subject") or filename
        if header_text:
            raw.append(
                self._mk(document_id, 0, ChunkType.HEADING, header_text, subject, now)
            )
        for para in [p.strip() for p in (body or "").split("\n\n") if p.strip()]:
            raw.append(
                self._mk(document_id, len(raw), ChunkType.PARAGRAPH, para, subject, now)
            )
        if attachments:
            raw.append(
                self._mk(
                    document_id,
                    len(raw),
                    ChunkType.PARAGRAPH,
                    "Attachments: " + ", ".join(attachments),
                    subject,
                    now,
                )
            )
        if not raw:
            raw.append(
                self._mk(
                    document_id,
                    0,
                    ChunkType.PARAGRAPH,
                    f"[Email: {filename}]",
                    None,
                    now,
                )
            )
        return finalize_chunks(raw)

    def _parse_eml(self, file_bytes: bytes):
        msg = BytesParser(policy=policy.default).parsebytes(file_bytes)
        headers = {
            "From": str(msg.get("from", "")),
            "To": str(msg.get("to", "")),
            "Cc": str(msg.get("cc", "")),
            "Date": str(msg.get("date", "")),
            "Subject": str(msg.get("subject", "")),
        }
        body = ""
        attachments: List[str] = []
        try:
            plain = msg.get_body(preferencelist=("plain",))
            html = None if plain else msg.get_body(preferencelist=("html",))
            if plain is not None:
                body = plain.get_content()
            elif html is not None:
                body = _html_to_text(html.get_content())
        except Exception as exc:  # noqa: BLE001
            logger.warning("eml body extraction fallback: %s", exc)
            payload = msg.get_payload()
            body = payload if isinstance(payload, str) else ""
        for part in msg.iter_attachments():
            name = part.get_filename()
            if name:
                attachments.append(name)
        return headers, body, attachments

    def _parse_msg(self, file_bytes: bytes, filename: str):
        try:
            import extract_msg  # type: ignore

            m = extract_msg.Message(io.BytesIO(file_bytes))
            headers = {
                "From": m.sender or "",
                "To": m.to or "",
                "Cc": getattr(m, "cc", "") or "",
                "Date": str(m.date or ""),
                "Subject": m.subject or "",
            }
            attachments = [
                a.longFilename or a.shortFilename
                for a in getattr(m, "attachments", [])
                if a
            ]
            return headers, (m.body or ""), [a for a in attachments if a]
        except Exception as exc:  # noqa: BLE001
            logger.warning("extract-msg unavailable/failed for %s: %s", filename, exc)
            return (
                {"Subject": filename},
                f"[Outlook .msg email: {filename} — extract-msg not installed]",
                [],
            )

    @staticmethod
    def _mk(document_id, idx, ctype, text, header, now) -> DocumentChunk:
        return DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            chunk_index=idx,
            chunk_type=ctype,
            text=text,
            page_number=None,
            parent_section_header=header,
            bbox_json=None,
            token_count=count_tokens(text),
            created_at=now,
        )
