"""Parser registry / factory (domain-pure).

Resolves an uploaded file to a canonical MIME type and the single parser that
handles it. Detection is extension-first, then the declared content-type, then a
magic-byte sniff (see ``domain.document.mime``). This is the one place document
type detection lives, so parsers never duplicate that logic. It depends only on
the domain ``IDocumentParser`` port, so both the application use case and
infrastructure can use it without breaking the dependency rule (ADR-013).
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.domain.document.interfaces import IDocumentParser
from app.domain.document.mime import resolve_mime

logger = logging.getLogger(__name__)


class ParserRegistry:
    def __init__(self, parsers: List[IDocumentParser]) -> None:
        self._parsers = list(parsers)

    @property
    def parsers(self) -> List[IDocumentParser]:
        return list(self._parsers)

    def resolve(
        self, declared_mime: str, filename: str, file_bytes: bytes
    ) -> Tuple[str, Optional[IDocumentParser]]:
        """Return (canonical_mime, parser). parser is None if nothing handles it."""
        head = file_bytes[:64] if file_bytes else b""
        mime = resolve_mime(declared_mime, filename, head)
        parser = next((p for p in self._parsers if p.can_parse(mime)), None)
        if parser is None:
            logger.warning(
                "No parser for file '%s' (declared=%s, resolved=%s)",
                filename,
                declared_mime,
                mime,
            )
        return mime, parser
