import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.infrastructure.logging.logger import correlation_id_ctx
from industrial_brain_shared.constants import ErrorCode
from industrial_brain_shared.types import ErrorResponse


class DomainException(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict = None,
        status_code: int = 400,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)


async def domain_exception_handler(
    request: Request, exc: DomainException
) -> JSONResponse:
    correlation_id = correlation_id_ctx.get()
    error_payload = ErrorResponse(
        code=exc.code.value,
        message=exc.message,
        details=exc.details,
        correlation_id=correlation_id,
    )
    logging.warn(f"Domain error: {exc.code.value} - {exc.message}")
    return JSONResponse(status_code=exc.status_code, content=error_payload.model_dump())


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    correlation_id = correlation_id_ctx.get()
    details = {"errors": exc.errors()}
    error_payload = ErrorResponse(
        code=ErrorCode.VALIDATION_ERROR.value,
        message="Request validation failed",
        details=details,
        correlation_id=correlation_id,
    )
    logging.warn(f"Validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_payload.model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = correlation_id_ctx.get()
    error_payload = ErrorResponse(
        code=ErrorCode.INTERNAL_SERVER_ERROR.value,
        message="An unexpected server error occurred",
        details={"type": type(exc).__name__, "message": str(exc)},
        correlation_id=correlation_id,
    )
    logging.error(f"Unhandled server error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload.model_dump(),
    )
