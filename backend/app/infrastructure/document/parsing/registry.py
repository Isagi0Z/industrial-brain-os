"""Re-export of the domain-pure parser registry.

The registry lives in the domain layer (``app.domain.document.parser_registry``)
because it depends only on the ``IDocumentParser`` port and the domain MIME
resolver. This module keeps the infrastructure import path stable.
"""

from app.domain.document.parser_registry import ParserRegistry

__all__ = ["ParserRegistry"]
