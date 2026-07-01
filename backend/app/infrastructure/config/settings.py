import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    SECRET_KEY: str = "replace-with-a-secure-secret-key-32-chars-long"
    LOG_LEVEL: str = "INFO"

    # Server configuration
    BACKEND_PORT: int = 8000
    BACKEND_HOST: str = "127.0.0.1"

    # PostgreSQL configuration
    POSTGRES_DB: str = "industrial_brain"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_dev_password"
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432

    # Neo4j configuration
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_dev_password"
    NEO4J_HOST: str = "127.0.0.1"
    NEO4J_PORT: int = 7474
    NEO4J_BOLT_PORT: int = 7687

    # Qdrant configuration
    QDRANT_HOST: str = "127.0.0.1"
    QDRANT_PORT: int = 6333

    # Redis configuration
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "redis_dev_password"

    # MinIO configuration
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin_dev_password"
    MINIO_HOST: str = "127.0.0.1"
    MINIO_PORT: int = 9000
    MINIO_CONSOLE_PORT: int = 9001
    MINIO_BUCKET_NAME: str = "industrial-brain-documents"

    # LLM / Chat configuration (M5)
    LLM_PROVIDER: str = "ollama"
    OLLAMA_HOST: str = "127.0.0.1"
    OLLAMA_PORT: int = 11434
    OLLAMA_MODEL: str = "llama3.2"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    CHAT_MAX_TOKENS: int = 2048
    CHAT_SESSION_TTL_SECONDS: int = 3600
    PROMPT_FILE: str = "ai/prompts/knowledge_copilot.yaml"

    # Ontology configuration (M6)
    ONTOLOGY_FILE: str = "ontology/industrial_ontology.yaml"

    # Extraction / KG configuration (M7)
    SPACY_MODEL: str = "en_core_web_sm"
    KG_CONFIDENCE_THRESHOLD: float = 0.6
    RELATION_EXTRACTION_PROMPT_FILE: str = "ai/prompts/relation_extraction.yaml"

    # Load from env file
    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                )
            ),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Instantiate settings singleton
settings = Settings()
