from passlib.context import CryptContext
from app.domain.auth.interfaces import IPasswordHasher

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class PasswordHasher(IPasswordHasher):
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)
