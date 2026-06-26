import logging
from typing import Optional
import psycopg2
from neo4j import GraphDatabase, Driver
from qdrant_client import QdrantClient
import redis
from minio import Minio

from app.infrastructure.config.settings import settings


class DIContainer:
    """
    Dependency Injection Container managing lifecycles of external connections.
    """

    def __init__(self):
        self._postgres_conn = None
        self._neo4j_driver: Optional[Driver] = None
        self._qdrant_client: Optional[QdrantClient] = None
        self._redis_client: Optional[redis.Redis] = None
        self._minio_client: Optional[Minio] = None

    def get_postgres(self):
        """
        Returns Postgres connection pool or connection.
        In production, a database pool should be used, but for baseline, returns connection.
        """
        if self._postgres_conn is None or self._postgres_conn.closed != 0:
            try:
                self._postgres_conn = psycopg2.connect(
                    dbname=settings.POSTGRES_DB,
                    user=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD,
                    host=settings.POSTGRES_HOST,
                    port=settings.POSTGRES_PORT,
                    connect_timeout=3,
                )
                logging.info("Connected to PostgreSQL database successfully.")
            except Exception as e:
                logging.error(f"Failed to connect to PostgreSQL: {e}")
                raise e
        return self._postgres_conn

    def get_neo4j(self) -> Driver:
        """
        Returns Neo4j Bolt driver.
        """
        if self._neo4j_driver is None:
            try:
                uri = f"bolt://{settings.NEO4J_HOST}:{settings.NEO4J_BOLT_PORT}"
                self._neo4j_driver = GraphDatabase.driver(
                    uri, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
                # Test connection connectivity
                self._neo4j_driver.verify_connectivity()
                logging.info("Connected to Neo4j graph database successfully.")
            except Exception as e:
                logging.error(f"Failed to connect to Neo4j: {e}")
                raise e
        return self._neo4j_driver

    def get_qdrant(self) -> QdrantClient:
        """
        Returns Qdrant vector database client.
        """
        if self._qdrant_client is None:
            try:
                self._qdrant_client = QdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                    timeout=3.0,
                    check_compatibility=False,
                )
                logging.info("Initialized Qdrant client successfully.")
            except Exception as e:
                logging.error(f"Failed to connect to Qdrant: {e}")
                raise e
        return self._qdrant_client

    def get_redis(self) -> redis.Redis:
        """
        Returns Redis connection client.
        """
        if self._redis_client is None:
            try:
                self._redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    password=settings.REDIS_PASSWORD,
                    socket_connect_timeout=3,
                    decode_responses=True,
                )
                self._redis_client.ping()
                logging.info("Connected to Redis cache successfully.")
            except Exception as e:
                logging.error(f"Failed to connect to Redis: {e}")
                raise e
        return self._redis_client

    def get_minio(self) -> Minio:
        """
        Returns MinIO S3 object store client.
        """
        if self._minio_client is None:
            try:
                endpoint = f"{settings.MINIO_HOST}:{settings.MINIO_PORT}"
                self._minio_client = Minio(
                    endpoint,
                    access_key=settings.MINIO_ROOT_USER,
                    secret_key=settings.MINIO_ROOT_PASSWORD,
                    secure=False,
                )
                # Verify access by checking if a bucket exists or list buckets
                self._minio_client.list_buckets()
                logging.info("Connected to MinIO object store successfully.")
            except Exception as e:
                logging.error(f"Failed to connect to MinIO: {e}")
                raise e
        return self._minio_client

    def close_all(self):
        """
        Closes all open connections safely.
        """
        if self._postgres_conn and not self._postgres_conn.closed:
            self._postgres_conn.close()
            logging.info("PostgreSQL database connection closed.")
        if self._neo4j_driver:
            self._neo4j_driver.close()
            logging.info("Neo4j database connection closed.")
        if self._qdrant_client:
            self._qdrant_client.close()
            logging.info("Qdrant database client closed.")
        if self._redis_client:
            self._redis_client.close()
            logging.info("Redis client connection closed.")


# Container singleton
container = DIContainer()
