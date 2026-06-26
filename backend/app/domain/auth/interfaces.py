from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from app.domain.auth.models import User


class IUserRepository(ABC):
    @abstractmethod
    def get_by_email(self, email: str) -> Optional[User]:
        pass

    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[User]:
        pass

    @abstractmethod
    def create(self, user: User) -> User:
        pass


class ITokenService(ABC):
    @abstractmethod
    def create_access_token(
        self, data: Dict[str, Any], expires_delta_minutes: Optional[int] = None
    ) -> str:
        pass

    @abstractmethod
    def create_refresh_token(
        self, data: Dict[str, Any], expires_delta_days: Optional[int] = None
    ) -> str:
        pass

    @abstractmethod
    def verify_token(self, token: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def revoke_token(self, jti: str, expires_in_seconds: int) -> None:
        pass


class IPasswordHasher(ABC):
    @abstractmethod
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        pass

    @abstractmethod
    def get_password_hash(self, password: str) -> str:
        pass
