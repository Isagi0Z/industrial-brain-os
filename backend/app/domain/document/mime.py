"""Pure MIME resolution (no outward imports — safe for the domain layer).

Browsers and CLIs frequently send a generic or wrong content-type for many
industrial formats (``text/plain`` for CSV/Markdown, ``application/octet-stream``
for anything unusual). This module resolves a *canonical* MIME type from the
declared type, the filename extension, and a small magic-byte sniff, so the
parser registry can always route to the right parser.
"""

from __future__ import annotations

import os
from typing import Optional

# Canonical extension -> MIME. Extension is the most reliable routing signal for
# uploads, so it is checked first in resolve_mime().
EXTENSION_TO_MIME: dict = {
    # documents
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # text / structured
    ".txt": "text/plain",
    ".log": "text/plain",
    ".text": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".xml": "application/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".yaml": "application/x-yaml",
    ".yml": "application/x-yaml",
    # images
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    # email
    ".eml": "message/rfc822",
    ".msg": "application/vnd.ms-outlook",
    # archive
    ".zip": "application/zip",
}

_GENERIC = {"", "application/octet-stream", "binary/octet-stream", "application/binary"}


def sniff_mime(head: bytes) -> Optional[str]:
    """Best-effort magic-byte detection for when the declared type and extension
    are both unhelpful. Only covers formats with distinctive headers."""
    if not head:
        return None
    if head[:4] == b"%PDF":
        return "application/pdf"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:4] in (b"GIF8",):
        return "image/gif"
    if head[:2] == b"BM":
        return "image/bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if head[:4] == b"PK\x03\x04":
        # zip container: could be docx/xlsx/pptx or a real zip. Extension decides;
        # default to zip and let the registry route office types by extension.
        return "application/zip"
    stripped = head.lstrip()
    if stripped[:1] in (b"{", b"["):
        return "application/json"
    if stripped[:5].lower() == b"<?xml":
        return "application/xml"
    return None


def resolve_mime(declared: str, filename: str, head: bytes = b"") -> str:
    """Return the canonical MIME type. Extension wins (most reliable for
    uploads), then a specific declared type, then a magic-byte sniff."""
    ext = os.path.splitext(filename or "")[1].lower()
    by_ext = EXTENSION_TO_MIME.get(ext)
    if by_ext:
        return by_ext
    if declared and declared not in _GENERIC:
        return declared.split(";")[0].strip()
    sniffed = sniff_mime(head)
    if sniffed:
        return sniffed
    return declared or "text/plain"
