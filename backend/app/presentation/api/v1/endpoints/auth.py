from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional
from app.application.auth.services import AuthUseCase, AuthenticationError
from app.presentation.api.dependencies.auth import (
    get_auth_use_case,
    get_current_user,
    oauth2_scheme,
)
from app.domain.auth.models import User
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool


@router.post("/login", response_model=TokenResponse)
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_use_case: AuthUseCase = Depends(get_auth_use_case),
):
    try:
        tokens = auth_use_case.authenticate_user(
            email=form_data.username,
            password=form_data.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
        }
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    request: Request,
    refresh_data: RefreshRequest,
    auth_use_case: AuthUseCase = Depends(get_auth_use_case),
):
    try:
        tokens = auth_use_case.refresh_access_token(
            refresh_token=refresh_data.refresh_token,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
        }
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout")
def logout(
    request: Request,
    logout_data: LogoutRequest,
    access_token: str = Depends(oauth2_scheme),
    auth_use_case: AuthUseCase = Depends(get_auth_use_case),
):
    auth_use_case.logout(
        access_token=access_token,
        refresh_token=logout_data.refresh_token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
    )
