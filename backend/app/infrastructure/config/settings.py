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
    # Reliability: keep the model resident so it does not unload after idle.
    # "-1" = keep loaded indefinitely (survives demo gaps); or a duration ("30m").
    OLLAMA_KEEP_ALIVE: str = "-1"
    OLLAMA_NUM_CTX: int = 4096  # context window sent to Ollama
    OLLAMA_REQUEST_TIMEOUT: float = 180.0
    OLLAMA_MAX_RETRIES: int = 2  # connection retries with exponential backoff
    OLLAMA_WARM_ON_STARTUP: bool = True  # preload + pin the model during API startup
    # Bound cross-encoder rerank cost so it does not grow with corpus size.
    # Candidates arrive in fused-retrieval-score order; only the top N are
    # reranked. Benchmarked (docs/performance): bge-reranker-large on CPU costs
    # ~0.8-1.6s per candidate, so rerank(40)=33s vs rerank(12)=~9s. 12 keeps the
    # highest-relevance candidates (no drop at demo scale) while bounding latency.
    GRAPHRAG_RERANK_MAX_CANDIDATES: int = 12
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

    # GraphRAG / Hybrid Retrieval configuration (M8)
    GRAPHRAG_RERANKER_MODEL: str = "BAAI/bge-reranker-large"
    GRAPHRAG_CACHE_TTL_SECONDS: int = 300
    GRAPHRAG_TOKEN_BUDGET: int = 6000
    GRAPHRAG_MAX_KG_DEPTH: int = 2
    GRAPHRAG_KG_TRAVERSAL_LIMIT: int = 50

    # Stage 7 context compression (M14 — LLMLingua)
    GRAPHRAG_COMPRESSION_ENABLED: bool = True
    GRAPHRAG_COMPRESSION_RATIO: float = 0.7  # keep ~70% of tokens
    GRAPHRAG_COMPRESSION_MIN_TOKENS: int = 2000  # skip small contexts
    LLMLINGUA_MODEL: str = (
        "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
    )
    LLMLINGUA_DEVICE: str = "cpu"  # "cpu" | "cuda" — pin device for model load

    # Knowledge Brain agent configuration (M9)
    KNOWLEDGE_BRAIN_PROMPT_FILE: str = (
        "ai/prompts/knowledge_brain/synthesize_answer.yaml"
    )
    KNOWLEDGE_BRAIN_MAX_STEPS: int = 10
    KNOWLEDGE_BRAIN_TOP_K: int = 5

    # Maintenance Brain agent configuration (M10)
    MAINTENANCE_BRAIN_PROMPT_FILE: str = (
        "ai/prompts/maintenance_brain/synthesize_guidance.yaml"
    )
    MAINTENANCE_BRAIN_MAX_STEPS: int = 10
    MAINTENANCE_BRAIN_TOP_K: int = 5

    # Compliance Brain agent configuration (M11)
    COMPLIANCE_GAP_DETECTION_PROMPT_FILE: str = (
        "ai/prompts/compliance_brain/gap_detection.yaml"
    )
    COMPLIANCE_EVIDENCE_PROMPT_FILE: str = (
        "ai/prompts/compliance_brain/generate_evidence.yaml"
    )
    COMPLIANCE_BRAIN_MAX_STEPS: int = 10
    COMPLIANCE_BRAIN_TOP_K: int = 5

    # RCA Brain agent configuration (M12)
    RCA_SUGGEST_WHY_PROMPT_FILE: str = "ai/prompts/rca_brain/suggest_why.yaml"
    RCA_GENERATE_REPORT_PROMPT_FILE: str = "ai/prompts/rca_brain/generate_report.yaml"
    RCA_FISHBONE_PROMPT_FILE: str = "ai/prompts/rca_brain/fishbone.yaml"
    RCA_BRAIN_MAX_STEPS: int = 10
    RCA_BRAIN_MAX_WHYS: int = 5
    RCA_BRAIN_TOP_K: int = 5
    RCA_INCIDENT_HISTORY_LIMIT: int = 5

    # Lessons Learned Brain agent configuration (M13)
    LESSONS_GENERATE_SUMMARY_PROMPT_FILE: str = (
        "ai/prompts/lessons_brain/generate_summary.yaml"
    )
    LESSONS_CHAT_PROMPT_FILE: str = "ai/prompts/lessons_brain/chat_answer.yaml"
    LESSONS_BRAIN_MAX_STEPS: int = 10
    LESSONS_SIMILAR_LESSONS_LIMIT: int = 3
    LESSONS_BRAIN_CHAT_TOP_K: int = 5
    LESSONS_WARNING_SIMILARITY_THRESHOLD: float = 0.85

    # Event-driven ingestion (M15 — Celery + Redis)
    INGESTION_BACKEND: str = "celery"  # "celery" | "redis-queue" (legacy)
    CELERY_BROKER_DB: int = 1  # Redis logical DB for the broker
    CELERY_RESULT_DB: int = 2  # Redis logical DB for the result backend
    CELERY_WORKER_CONCURRENCY: int = 2

    @property
    def celery_broker_url(self) -> str:
        return (
            f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:"
            f"{self.REDIS_PORT}/{self.CELERY_BROKER_DB}"
        )

    @property
    def celery_result_backend(self) -> str:
        return (
            f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:"
            f"{self.REDIS_PORT}/{self.CELERY_RESULT_DB}"
        )

    # Observability (M17 — OpenTelemetry, ADR-016)
    OTEL_ENABLED: bool = False  # compose enables for ib_backend/ib_worker
    OTEL_SERVICE_NAME: str = "industrial-brain-api"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"

    # Evaluation Layer (M16)
    EVAL_FAITHFULNESS_PROMPT_FILE: str = "ai/prompts/evaluation/faithfulness.yaml"
    EVAL_CONTEXT_PRECISION_PROMPT_FILE: str = (
        "ai/prompts/evaluation/context_precision.yaml"
    )
    EVAL_GOLDEN_DATASET: str = "datasets/golden_qa.json"  # repo-root relative
    EVAL_TOP_K: int = 10
    EVAL_JUDGE_MAX_TOKENS: int = 64
    EVAL_HALLUCINATION_THRESHOLD: float = 0.15  # CI gate

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
