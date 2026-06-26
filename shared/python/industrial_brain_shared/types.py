from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class BoundingBox(BaseModel):
    x: float = Field(..., description="X coordinate of top-left corner")
    y: float = Field(..., description="Y coordinate of top-left corner")
    w: float = Field(..., description="Width of bounding box")
    h: float = Field(..., description="Height of bounding box")
    page: int = Field(..., description="Page number the bounding box resides on")

class ServiceStatus(BaseModel):
    name: str
    status: str  # healthy, unhealthy, degraded
    version: str
    details: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None

class UserPrincipal(BaseModel):
    user_id: str
    username: str
    roles: List[str]
    workspaces: List[str]
