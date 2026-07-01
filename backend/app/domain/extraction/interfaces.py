from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.domain.document.models import DocumentChunk
from app.domain.extraction.models import (
    DocumentExtractionReport,
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)


class IEntityExtractor(ABC):
    """Extract named entities from a document chunk."""

    @abstractmethod
    def extract(self, chunk: DocumentChunk) -> List[ExtractedEntity]: ...


class IRelationExtractor(ABC):
    """Extract relations between already-resolved entities in a chunk."""

    @abstractmethod
    async def extract(
        self,
        chunk: DocumentChunk,
        entities: List[ExtractedEntity],
    ) -> List[ExtractedRelation]: ...


class IEntityResolver(ABC):
    """Resolve duplicate or near-duplicate entities into canonical forms."""

    @abstractmethod
    def resolve(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]: ...


class IKGWriter(ABC):
    """Write extraction results to the knowledge graph."""

    @abstractmethod
    def write_result(self, result: ExtractionResult) -> None: ...

    @abstractmethod
    def write_report(self, report: DocumentExtractionReport) -> None: ...
