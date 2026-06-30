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
    IChunkRepository,
)
from app.application.document.services import DocumentUseCase
from app.application.document.parsing_service import DocumentParsingUseCase
from app.infrastructure.document.minio_storage_service import MinioStorageService
from app.infrastructure.document.document_repository import PostgresDocumentRepository
from app.infrastructure.document.job_repository import PostgresJobRepository
from app.infrastructure.document.queue_service import RedisQueueService
from app.infrastructure.document.chunk_repository import PostgresChunkRepository
from app.infrastructure.document.parsing.pymupdf_parser import PyMuPDFParser
from app.infrastructure.document.parsing.docx_parser import DocxParser
from app.infrastructure.document.parsing.xlsx_parser import XlsxParser
from app.infrastructure.document.parsing.image_parser import ImageParser
from app.infrastructure.document.worker import IngestionWorker

from app.domain.search.interfaces import (
    IEmbeddingService,
    IVectorRepository,
    IBM25Repository,
)
from app.application.search.embedding_use_case import EmbeddingUseCase
from app.infrastructure.search.embedding_service import (
    SentenceTransformerEmbedder,
    VECTOR_DIM,
)
from app.infrastructure.search.qdrant_repository import QdrantVectorRepository
from app.infrastructure.search.bm25_repository import PostgresBM25Repository

from app.application.chat.chat_use_case import ChatUseCase
from app.infrastructure.chat.ollama_gateway import OllamaGateway
from app.infrastructure.chat.gemini_gateway import GeminiGateway
from app.infrastructure.chat.redis_history_repository import RedisChatHistoryRepository
from app.infrastructure.chat.context_builder import ContextBuilder
from app.infrastructure.chat.prompt_loader import YamlPromptLoader


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

    def get_chunk_repository(self) -> IChunkRepository:
        if not hasattr(self, "_chunk_repository"):
            self._chunk_repository = PostgresChunkRepository(self.get_postgres)
        return self._chunk_repository

    def get_parsing_use_case(self) -> DocumentParsingUseCase:
        if not hasattr(self, "_parsing_use_case"):
            self._parsing_use_case = DocumentParsingUseCase(
                document_repo=self.get_document_repository(),
                storage_service=self.get_storage_service(),
                job_repo=self.get_job_repository(),
                chunk_repo=self.get_chunk_repository(),
                parsers=[PyMuPDFParser(), DocxParser(), XlsxParser(), ImageParser()],
            )
        return self._parsing_use_case

    # ------------------------------------------------------------------
    # Search services (M4)
    # ------------------------------------------------------------------

    def get_embedding_service(self) -> IEmbeddingService:
        if not hasattr(self, "_embedding_service"):
            self._embedding_service = SentenceTransformerEmbedder()
        return self._embedding_service

    def get_vector_repository(self) -> IVectorRepository:
        if not hasattr(self, "_vector_repository"):
            self._vector_repository = QdrantVectorRepository(self.get_qdrant)
        return self._vector_repository

    def get_bm25_repository(self) -> IBM25Repository:
        if not hasattr(self, "_bm25_repository"):
            self._bm25_repository = PostgresBM25Repository(self.get_postgres)
        return self._bm25_repository

    def get_embedding_use_case(self) -> EmbeddingUseCase:
        if not hasattr(self, "_embedding_use_case"):
            self._embedding_use_case = EmbeddingUseCase(
                document_repo=self.get_document_repository(),
                chunk_repo=self.get_chunk_repository(),
                job_repo=self.get_job_repository(),
                embedding_service=self.get_embedding_service(),
                vector_repo=self.get_vector_repository(),
                bm25_repo=self.get_bm25_repository(),
                vector_dim=VECTOR_DIM,
            )
        return self._embedding_use_case

    # ------------------------------------------------------------------
    # Chat services (M5)
    # ------------------------------------------------------------------

    def get_chat_use_case(self) -> ChatUseCase:
        if not hasattr(self, "_chat_use_case"):
            from pathlib import Path

            prompt_path = Path(settings.PROMPT_FILE)
            if not prompt_path.is_absolute():
                prompt_path = Path(__file__).parents[4] / settings.PROMPT_FILE

            prompt_loader = YamlPromptLoader(prompt_path)
            context_builder = ContextBuilder()
            history_repo = RedisChatHistoryRepository(self.get_redis)

            primary: OllamaGateway | GeminiGateway
            fallback: OllamaGateway | GeminiGateway | None = None

            if settings.LLM_PROVIDER == "gemini":
                primary = GeminiGateway(
                    api_key=settings.GEMINI_API_KEY,
                    model=settings.GEMINI_MODEL,
                )
                if settings.OLLAMA_HOST:
                    fallback = OllamaGateway(
                        host=settings.OLLAMA_HOST,
                        port=settings.OLLAMA_PORT,
                        model=settings.OLLAMA_MODEL,
                    )
            else:
                primary = OllamaGateway(
                    host=settings.OLLAMA_HOST,
                    port=settings.OLLAMA_PORT,
                    model=settings.OLLAMA_MODEL,
                )
                if settings.GEMINI_API_KEY:
                    fallback = GeminiGateway(
                        api_key=settings.GEMINI_API_KEY,
                        model=settings.GEMINI_MODEL,
                    )

            self._chat_use_case = ChatUseCase(
                embedding_use_case=self.get_embedding_use_case(),
                primary_gateway=primary,
                fallback_gateway=fallback,
                history_repo=history_repo,
                context_builder=context_builder,
                prompt_loader=prompt_loader,
                max_tokens=settings.CHAT_MAX_TOKENS,
                session_ttl_seconds=settings.CHAT_SESSION_TTL_SECONDS,
            )
            logging.info(
                "ChatUseCase initialized",
                extra={
                    "provider": settings.LLM_PROVIDER,
                    "has_fallback": fallback is not None,
                },
            )
        return self._chat_use_case

    def get_ingestion_worker(self) -> IngestionWorker:
        if not hasattr(self, "_ingestion_worker"):
            self._ingestion_worker = IngestionWorker(
                get_redis_fn=self.get_redis,
                get_parsing_use_case_fn=self.get_parsing_use_case,
                get_embedding_use_case_fn=self.get_embedding_use_case,
            )
        return self._ingestion_worker

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
