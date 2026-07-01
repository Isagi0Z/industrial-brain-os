from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExtractedEntity:
    """An entity identified within a document chunk.

    tag_number and manufacturer/model_number drive entity resolution.
    confidence reflects how certain the extractor is about the classification.
    """

    text: str
    entity_type: str  # Must match an OntologySchema node_type key
    chunk_id: str
    tag_number: Optional[str] = None
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    start_char: int = 0
    end_char: int = 0


@dataclass
class ExtractedRelation:
    """A directional relationship between two extracted entities."""

    source_tag: str
    source_type: str
    relation_type: str
    target_tag: str
    target_type: str
    confidence: float = 1.0
    # Relations below the configured threshold are written with tentative=True
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Aggregated extraction output for a single document chunk."""

    document_id: str
    chunk_id: str
    entities: List[ExtractedEntity] = field(default_factory=list)
    relations: List[ExtractedRelation] = field(default_factory=list)


@dataclass
class DocumentExtractionReport:
    """Per-document extraction summary logged after KG population completes."""

    document_id: str
    job_id: str
    chunks_processed: int
    chunks_failed: int
    total_entities: int
    total_relations: int

    @property
    def success_rate(self) -> float:
        if self.chunks_processed == 0:
            return 1.0
        return (self.chunks_processed - self.chunks_failed) / self.chunks_processed
