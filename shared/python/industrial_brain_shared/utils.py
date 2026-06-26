import re
from typing import Optional

def normalize_asset_tag(tag: str) -> str:
    """
    Standardizes tag names, e.g. "vlv-101" -> "VLV-101" and "Valve 101" -> "VLV-101"
    """
    cleaned = tag.strip().upper()
    # Replace spaces or hyphens to keep tag formats normalized
    cleaned = re.sub(r'[\s_]+', '-', cleaned)
    
    # Simple rule-based normalization examples
    if cleaned.startswith("VALVE-"):
        cleaned = cleaned.replace("VALVE-", "VLV-")
    elif cleaned.startswith("SENSOR-"):
        cleaned = cleaned.replace("SENSOR-", "SEN-")
    elif cleaned.startswith("PUMP-"):
        cleaned = cleaned.replace("PUMP-", "P-")
        
    return cleaned

def validate_uuid(uuid_str: str) -> bool:
    """
    Checks if a string is a valid UUIDv4
    """
    uuid4_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(uuid4_pattern.match(uuid_str))
