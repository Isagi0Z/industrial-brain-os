from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.infrastructure.di.container import container
from app.domain.auth.models import User
from app.application.auth.services import AuthUseCase, AuthenticationError
from typing import Callable

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_auth_use_case() -> AuthUseCase:
    return container.get_auth_use_case()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_use_case: AuthUseCase = Depends(get_auth_use_case),
) -> User:
    try:
        user = auth_use_case.verify_access_token(token)
        return user
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(required_role: str) -> Callable:
    def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        has_role = False
        for role in current_user.roles:
            if role.name == required_role:
                has_role = True
                break
        if not has_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have required role: {required_role}",
            )
        return current_user

    return role_dependency
