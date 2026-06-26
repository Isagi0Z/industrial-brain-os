from enum import Enum

class DocumentCategory(str, Enum):
    OEM_MANUAL = "OEM_MANUAL"
    SOP = "SOP"
    PID_DRAWING = "PID_DRAWING"
    MAINTENANCE_WORK_ORDER = "MAINTENANCE_WORK_ORDER"
    REGULATORY_AUDIT = "REGULATORY_AUDIT"
    UNKNOWN = "UNKNOWN"

class AssetCriticality(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

# Service names matching the architecture sub-brains
class SubBrainName(str, Enum):
    KNOWLEDGE = "KNOWLEDGE"
    MAINTENANCE = "MAINTENANCE"
    COMPLIANCE = "COMPLIANCE"
    RCA = "RCA"
    LESSONS_LEARNED = "LESSONS_LEARNED"

# Error Codes
class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    INFERENCE_ERROR = "INFERENCE_ERROR"
