from typing import Dict, Any

def get_default_headers(correlation_id: str) -> Dict[str, str]:
    return {
        "X-Correlation-ID": correlation_id,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
