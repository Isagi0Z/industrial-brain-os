import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.infrastructure.logging.logger import setup_logging
from app.infrastructure.di.container import container
from app.infrastructure.database.infra_init import run_all as init_infrastructure
from app.presentation.middleware.logging_middleware import (
    LoggingAndCorrelationMiddleware,
)
from app.presentation.middleware.error_handler import (
    DomainException,
    domain_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)
from app.presentation.api.v1.router import api_router

# 1. Setup logging system prior to app initialization
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logging.info("Starting up Industrial Brain OS API...")
    # 1. Verify all database connections
    try:
        postgres = container.get_postgres()  # noqa: F841
        neo4j = container.get_neo4j()
        qdrant = container.get_qdrant()
        redis = container.get_redis()  # noqa: F841
        minio = container.get_minio()
    except Exception as e:
        logging.error(f"Startup check failed: Some databases are not accessible. {e}")
        neo4j = None
        qdrant = None
        minio = None

    # 2. Initialise infrastructure (Qdrant collections, Neo4j schema, MinIO buckets)
    if neo4j and qdrant and minio:
        try:
            init_infrastructure(qdrant, neo4j, minio)
        except Exception as e:
            logging.error(f"Infrastructure init failed: {e}")

    yield

    # Shutdown actions
    logging.info("Shutting down Industrial Brain OS API...")
    container.close_all()


# 2. Instantiate FastAPI
app = FastAPI(
    title="Industrial Brain OS Backend Service",
    description="Production-grade unified operational intelligence system for Industrial assets.",
    version="0.1.0",
    lifespan=lifespan,
)

# 3. Add CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Add Custom Logging & Correlation ID Middleware
app.add_middleware(LoggingAndCorrelationMiddleware)

# 5. Register Exception Handlers
app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# 6. Include API Routers
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def read_root():
    return {
        "service": "Industrial Brain OS API",
        "version": "0.1.0",
        "docs_url": "/docs",
    }
