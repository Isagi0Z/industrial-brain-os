from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.domain.document.models import DocumentChunk
from app.domain.extraction.models import (
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)


class IEntityExtractor(ABC):
    @abstractmethod
    def extract(self, chunk: DocumentChunk) -> List[ExtractedEntity]: ...


class IRelationExtractor(ABC):
    @abstractmethod
    async def extract(
        self,
        chunk: DocumentChunk,
        entities: List[ExtractedEntity],
    ) -> List[ExtractedRelation]: ...


class IEntityResolver(ABC):
    @abstractmethod
    def resolve(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]: ...


class IKGWriter(ABC):
    @abstractmethod
    def write_result(self, result: ExtractionResult) -> None: ...
