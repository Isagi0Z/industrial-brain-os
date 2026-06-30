"""Infrastructure initialization for M1.

Initialises Qdrant collections, Neo4j constraints/indexes, and MinIO buckets
on application startup. All operations are idempotent — safe to call on every
boot without side effects.
"""

import logging
from typing import TYPE_CHECKING

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PayloadSchemaType,
)
from neo4j import Driver
from minio import Minio
from minio.error import S3Error

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DOCUMENT_CHUNKS_COLLECTION = "document_chunks"
VECTOR_DIMENSION = 1024  # bge-large-en-v1.5
VECTOR_DISTANCE = Distance.COSINE

MINIO_BUCKETS = [
    "industrial-documents",  # primary document store
    "processed-chunks",  # extracted text artifacts
]

NEO4J_CONSTRAINTS = [
    ("asset_tag_unique", "Asset", "tag_number"),
    ("equipment_tag_unique", "Equipment", "tag_number"),
    ("sensor_tag_unique", "Sensor", "tag_number"),
    ("document_source_unique", "Document", "source_id"),
]

NEO4J_INDEXES = [
    ("failure_code_index", "FailureMode", "failure_code"),
    ("procedure_type_index", "Procedure", "procedure_type"),
]


# ---------------------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------------------
def init_qdrant(client: QdrantClient) -> None:
    """Create the document_chunks vector collection if it does not exist."""
    try:
        existing = {c.name for c in client.get_collections().collections}
        if DOCUMENT_CHUNKS_COLLECTION not in existing:
            client.create_collection(
                collection_name=DOCUMENT_CHUNKS_COLLECTION,
                vectors_config=VectorParams(
                    size=VECTOR_DIMENSION,
                    distance=VECTOR_DISTANCE,
                ),
            )
            logger.info("Qdrant: created collection '%s'.", DOCUMENT_CHUNKS_COLLECTION)
        else:
            logger.info(
                "Qdrant: collection '%s' already exists.", DOCUMENT_CHUNKS_COLLECTION
            )

        # Apply payload indexes for efficient metadata filtering (RBAC + query)
        _qdrant_payload_indexes(client)
    except Exception as exc:
        logger.error("Qdrant init failed: %s", exc)
        raise


def _qdrant_payload_indexes(client: QdrantClient) -> None:
    """Ensure payload indexes exist on filterable fields."""
    index_fields = [
        ("document_id", PayloadSchemaType.KEYWORD),
        ("role_scope", PayloadSchemaType.KEYWORD),
        ("page_number", PayloadSchemaType.INTEGER),
        ("chunk_type", PayloadSchemaType.KEYWORD),
    ]
    for field_name, schema_type in index_fields:
        try:
            client.create_payload_index(
                collection_name=DOCUMENT_CHUNKS_COLLECTION,
                field_name=field_name,
                field_schema=schema_type,
            )
            logger.info("Qdrant: payload index '%s' ensured.", field_name)
        except Exception as exc:
            # Index may already exist — Qdrant raises on duplicate; suppress.
            logger.debug("Qdrant payload index '%s' skipped: %s", field_name, exc)


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------
def init_neo4j(driver: Driver) -> None:
    """Apply ontology constraints and indexes to the Neo4j graph database."""
    try:
        with driver.session() as session:
            _apply_neo4j_constraints(session)
            _apply_neo4j_indexes(session)
        logger.info("Neo4j: schema constraints and indexes applied.")
    except Exception as exc:
        logger.error("Neo4j init failed: %s", exc)
        raise


def _apply_neo4j_constraints(session) -> None:
    for constraint_name, label, prop in NEO4J_CONSTRAINTS:
        cypher = (
            f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
        )
        try:
            session.run(cypher)
            logger.info("Neo4j: constraint '%s' ensured.", constraint_name)
        except Exception as exc:
            logger.debug("Neo4j constraint '%s' skipped: %s", constraint_name, exc)


def _apply_neo4j_indexes(session) -> None:
    for index_name, label, prop in NEO4J_INDEXES:
        cypher = (
            f"CREATE INDEX {index_name} IF NOT EXISTS " f"FOR (n:{label}) ON (n.{prop})"
        )
        try:
            session.run(cypher)
            logger.info("Neo4j: index '%s' ensured.", index_name)
        except Exception as exc:
            logger.debug("Neo4j index '%s' skipped: %s", index_name, exc)


# ---------------------------------------------------------------------------
# MinIO
# ---------------------------------------------------------------------------
def init_minio(client: Minio) -> None:
    """Create required MinIO buckets if they do not exist."""
    try:
        for bucket in MINIO_BUCKETS:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                logger.info("MinIO: bucket '%s' created.", bucket)
            else:
                logger.info("MinIO: bucket '%s' already exists.", bucket)
    except S3Error as exc:
        logger.error("MinIO init failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_all(
    qdrant_client: QdrantClient, neo4j_driver: Driver, minio_client: Minio
) -> None:
    """Run all infrastructure initialization steps in sequence."""
    logger.info("Infrastructure init: starting...")
    init_qdrant(qdrant_client)
    init_neo4j(neo4j_driver)
    init_minio(minio_client)
    logger.info("Infrastructure init: complete.")
