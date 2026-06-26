import time
import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.infrastructure.logging.logger import correlation_id_ctx


class LoggingAndCorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Retrieve or generate Correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # 2. Set context variable for logs
        token = correlation_id_ctx.set(correlation_id)

        # Record start time
        start_time = time.perf_counter()

        logging.info(f"Incoming request: {request.method} {request.url.path}")

        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Inject correlation ID into response headers
            response.headers["X-Correlation-ID"] = correlation_id

            logging.info(
                f"Request completed: {request.method} {request.url.path} "
                f"Status: {response.status_code} Duration: {duration_ms:.2f}ms",
                extra={
                    "execution_time_ms": duration_ms,
                    "status_code": response.status_code,
                },
            )
            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logging.error(
                f"Unhandled error processing request {request.method} {request.url.path}: {str(e)}",
                exc_info=True,
                extra={"execution_time_ms": duration_ms},
            )
            raise e
        finally:
            # 3. Clean up context variable
            correlation_id_ctx.reset(token)
