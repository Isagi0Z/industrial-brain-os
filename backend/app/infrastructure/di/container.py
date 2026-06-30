import logging
from typing import Optional
import psycopg2
from neo4j import GraphDatabase, Driver
from qdrant_client import QdrantClient
import redis
from minio import Minio

from app.infrastructure.config.settings import settings

from app.domain.auth.interfaces import IUserRepository, ITokenService, IPasswordHasher
from app.application.auth.services import AuthUseCase
from app.infrastructure.auth.jwt_service import JWTService
from app.infrastructure.auth.password_hasher import PasswordHasher
from app.infrastructure.auth.user_repository import PostgresUserRepository

from app.domain.document.interfaces import (
    IDocumentRepository,
    IStorageService,
    IJobRepository,
    IQueueService,
)
from app.application.document.services import DocumentUseCase
from app.infrastructure.document.minio_storage_service import MinioStorageService
from app.infrastructure.document.document_repository import PostgresDocumentRepository
from app.infrastructure.document.job_repository import PostgresJobRepository
from app.infrastructure.document.queue_service import RedisQueueService


class DIContainer:
    """Manages the lifecycles of all external connections and service singletons."""

    def __init__(self):
        self._postgres_conn = None
        self._neo4j_driver: Optional[Driver] = None
        self._qdrant_client: Optional[QdrantClient] = None
        self._redis_client: Optional[redis.Redis] = None
        self._minio_client: Optional[Minio] = None

    # ------------------------------------------------------------------
    # Infrastructure connections
    # ------------------------------------------------------------------

    def get_postgres(self):
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
            except Exception as exc:
                logging.error("Failed to connect to PostgreSQL: %s", exc)
                raise
        return self._postgres_conn

    def get_neo4j(self) -> Driver:
        if self._neo4j_driver is None:
            try:
                uri = f"bolt://{settings.NEO4J_HOST}:{settings.NEO4J_BOLT_PORT}"
                self._neo4j_driver = GraphDatabase.driver(
                    uri, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
                self._neo4j_driver.verify_connectivity()
                logging.info("Connected to Neo4j graph database successfully.")
            except Exception as exc:
                logging.error("Failed to connect to Neo4j: %s", exc)
                raise
        return self._neo4j_driver

    def get_qdrant(self) -> QdrantClient:
        if self._qdrant_client is None:
            try:
                self._qdrant_client = QdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                    timeout=3.0,
                    check_compatibility=False,
                )
                logging.info("Initialized Qdrant client successfully.")
            except Exception as exc:
                logging.error("Failed to connect to Qdrant: %s", exc)
                raise
        return self._qdrant_client

    def get_redis(self) -> redis.Redis:
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
            except Exception as exc:
                logging.error("Failed to connect to Redis: %s", exc)
                raise
        return self._redis_client

    def get_minio(self) -> Minio:
        if self._minio_client is None:
            try:
                endpoint = f"{settings.MINIO_HOST}:{settings.MINIO_PORT}"
                self._minio_client = Minio(
                    endpoint,
                    access_key=settings.MINIO_ROOT_USER,
                    secret_key=settings.MINIO_ROOT_PASSWORD,
                    secure=False,
                )
                self._minio_client.list_buckets()
                logging.info("Connected to MinIO object store successfully.")
            except Exception as exc:
                logging.error("Failed to connect to MinIO: %s", exc)
                raise
        return self._minio_client

    # ------------------------------------------------------------------
    # Auth services
    # ------------------------------------------------------------------

    def get_token_service(self) -> ITokenService:
        if not hasattr(self, "_token_service"):
            self._token_service = JWTService(self.get_redis)
        return self._token_service

    def get_password_hasher(self) -> IPasswordHasher:
        if not hasattr(self, "_password_hasher"):
            self._password_hasher = PasswordHasher()
        return self._password_hasher

    def get_user_repository(self) -> IUserRepository:
        if not hasattr(self, "_user_repository"):
            self._user_repository = PostgresUserRepository(self.get_postgres)
        return self._user_repository

    def get_auth_use_case(self) -> AuthUseCase:
        if not hasattr(self, "_auth_use_case"):
            self._auth_use_case = AuthUseCase(
                user_repo=self.get_user_repository(),
                token_service=self.get_token_service(),
                password_hasher=self.get_password_hasher(),
            )
        return self._auth_use_case

    # ------------------------------------------------------------------
    # Document services
    # ------------------------------------------------------------------

    def get_storage_service(self) -> IStorageService:
        if not hasattr(self, "_storage_service"):
            self._storage_service = MinioStorageService(self.get_minio)
        return self._storage_service

    def get_document_repository(self) -> IDocumentRepository:
        if not hasattr(self, "_document_repository"):
            self._document_repository = PostgresDocumentRepository(self.get_postgres)
        return self._document_repository

    def get_job_repository(self) -> IJobRepository:
        if not hasattr(self, "_job_repository"):
            self._job_repository = PostgresJobRepository(self.get_postgres)
        return self._job_repository

    def get_queue_service(self) -> IQueueService:
        if not hasattr(self, "_queue_service"):
            self._queue_service = RedisQueueService(self.get_redis)
        return self._queue_service

    def get_document_use_case(self) -> DocumentUseCase:
        if not hasattr(self, "_document_use_case"):
            self._document_use_case = DocumentUseCase(
                document_repo=self.get_document_repository(),
                storage_service=self.get_storage_service(),
                job_repo=self.get_job_repository(),
                queue_service=self.get_queue_service(),
            )
        return self._document_use_case

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def close_all(self):
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
