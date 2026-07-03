import logging
import sys
from pythonjsonlogger import jsonlogger
from app.infrastructure.config.settings import settings

# Global correlation context var
import contextvars

correlation_id_ctx = contextvars.ContextVar("correlation_id", default="-")


class CorrelationIdJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["correlation_id"] = correlation_id_ctx.get()
        # M17 (ADR-016): stamp the active OTel trace id so structured logs and
        # Jaeger traces join on the same id. No-op (None) when tracing is off.
        try:
            from app.infrastructure.observability.tracing import current_trace_id

            trace_id = current_trace_id()
            if trace_id:
                log_record["trace_id"] = trace_id
        except Exception:
            pass
        if not log_record.get("level"):
            log_record["level"] = record.levelname
        if not log_record.get("timestamp"):
            log_record["timestamp"] = getattr(
                record, "asctime", None
            ) or self.formatTime(record, self.default_time_format)


def setup_logging():
    log_level = logging.getLevelName(settings.LOG_LEVEL.upper())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Console handler with JSON formatting
    handler = logging.StreamHandler(sys.stdout)
    formatter = CorrelationIdJsonFormatter(
        "%(timestamp)s %(level)s %(message)s %(correlation_id)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Disable propagation of default uvicorn access logs to prevent double logging
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.propagate = False

    logging.info("Logging configured successfully in JSON format")
