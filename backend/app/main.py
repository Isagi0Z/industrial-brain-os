import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.infrastructure.logging.logger import setup_logging
from app.infrastructure.di.container import container
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
    # Trigger database connectivity checks to verify configuration on boot
    try:
        container.get_postgres()
        container.get_neo4j()
        container.get_qdrant()
        container.get_redis()
        container.get_minio()
    except Exception as e:
        logging.error(f"Startup check failed: Some databases are not accessible. {e}")

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
