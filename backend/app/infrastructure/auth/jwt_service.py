import jwt
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from app.domain.auth.interfaces import ITokenService
from app.infrastructure.config.settings import settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 15  # Short-lived access token
DEFAULT_REFRESH_EXPIRE_DAYS = 7  # Long-lived refresh token


class JWTService(ITokenService):
    def __init__(self, get_redis_fn):
        self.get_redis_fn = get_redis_fn

    def _create_token(
        self, data: Dict[str, Any], expires_delta: timedelta, token_type: str
    ) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + expires_delta
        jti = str(uuid.uuid4())
        to_encode.update({"exp": expire, "jti": jti, "type": token_type})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

    def create_access_token(
        self, data: Dict[str, Any], expires_delta_minutes: Optional[int] = None
    ) -> str:
        delta = timedelta(minutes=expires_delta_minutes or DEFAULT_EXPIRE_MINUTES)
        return self._create_token(data, delta, "access")

    def create_refresh_token(
        self, data: Dict[str, Any], expires_delta_days: Optional[int] = None
    ) -> str:
        delta = timedelta(days=expires_delta_days or DEFAULT_REFRESH_EXPIRE_DAYS)
        return self._create_token(data, delta, "refresh")

    def verify_token(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
            jti = payload.get("jti")
            if jti:
                redis_client = self.get_redis_fn()
                if redis_client.exists(f"revoked_token:{jti}"):
                    logger.warning(f"Attempt to use revoked token {jti}")
                    raise ValueError("Token has been revoked")
            return payload
        except jwt.PyJWTError as e:
            raise ValueError(f"Invalid token: {str(e)}")

    def revoke_token(self, jti: str, expires_in_seconds: int) -> None:
        if expires_in_seconds > 0:
            redis_client = self.get_redis_fn()
            redis_client.setex(f"revoked_token:{jti}", expires_in_seconds, "true")
