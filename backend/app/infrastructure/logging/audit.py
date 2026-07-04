import logging
from typing import Optional

logger = logging.getLogger("audit")


class AuditEvent:
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    TOKEN_REFRESH = "TOKEN_REFRESH"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    ROLE_CHANGED = "ROLE_CHANGED"
    PERMISSION_CHANGED = "PERMISSION_CHANGED"
    USER_REGISTERED = "USER_REGISTERED"


def log_audit_event(
    event_type: str,
    result: str,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    correlation_id: Optional[str] = None,
    details: Optional[dict] = None,
):
    audit_data = {
        "event_type": event_type,
        "result": result,
        "user_id": user_id or "unknown",
        "ip_address": ip_address or "unknown",
        "user_agent": user_agent or "unknown",
        "correlation_id": correlation_id or "unknown",
        "details": details or {},
    }

    # We use INFO level for audit logs
    logger.info("AUDIT_EVENT", extra={"audit": audit_data})
