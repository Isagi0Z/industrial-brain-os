from fastapi import APIRouter, status, Response
from pydantic import BaseModel
from typing import Dict, Any

from app.infrastructure.di.container import container

router = APIRouter()


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    environment: str
    databases: Dict[str, Any]


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Get application and database connectivity health status",
)
def check_health(response: Response) -> HealthCheckResponse:
    db_status = {}
    is_healthy = True

    # 1. Check PostgreSQL
    try:
        conn = container.get_postgres()
        # Simple test query
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        db_status["postgres"] = "healthy"
    except Exception as e:
        db_status["postgres"] = f"unhealthy: {str(e)}"
        is_healthy = False

    # 2. Check Neo4j
    try:
        driver = container.get_neo4j()
        driver.verify_connectivity()
        db_status["neo4j"] = "healthy"
    except Exception as e:
        db_status["neo4j"] = f"unhealthy: {str(e)}"
        is_healthy = False

    # 3. Check Qdrant
    try:
        client = container.get_qdrant()
        # Simple request to qdrant
        client.get_collections()
        db_status["qdrant"] = "healthy"
    except Exception as e:
        db_status["qdrant"] = f"unhealthy: {str(e)}"
        is_healthy = False

    # 4. Check Redis
    try:
        r_client = container.get_redis()
        r_client.ping()
        db_status["redis"] = "healthy"
    except Exception as e:
        db_status["redis"] = f"unhealthy: {str(e)}"
        is_healthy = False

    # 5. Check MinIO
    try:
        minio_client = container.get_minio()
        minio_client.list_buckets()
        db_status["minio"] = "healthy"
    except Exception as e:
        db_status["minio"] = f"unhealthy: {str(e)}"
        is_healthy = False

    # If any database check fails, set HTTP status to 503
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        status_text = "unhealthy"
    else:
        status_text = "healthy"

    return HealthCheckResponse(
        status=status_text,
        version="0.1.0",
        environment="development",
        databases=db_status,
    )


@router.get(
    "/health/llm",
    status_code=status.HTTP_200_OK,
    summary="LLM (Ollama) availability and whether the target model is loaded",
)
async def check_llm_health() -> Dict[str, Any]:
    """Report LLM gateway health so the demo can detect an unavailable/unloaded
    model and its reason. Recovery (reconnect, keep_alive, warm-up) is automatic
    in the gateway; this endpoint is for monitoring."""
    gateway = container.get_model_gateway()
    health = getattr(gateway, "health", None)
    if health is None:
        return {"available": True, "detail": "gateway does not expose health()"}
    return await health()
