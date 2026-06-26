import logging
import datetime
from typing import Optional, Dict
from app.domain.auth.interfaces import IUserRepository, ITokenService, IPasswordHasher
from app.domain.auth.models import User
from app.infrastructure.logging.audit import log_audit_event, AuditEvent
from app.infrastructure.logging.logger import correlation_id_ctx

logger = logging.getLogger(__name__)


class AuthException(Exception):
    pass


class AuthenticationError(AuthException):
    pass


class AuthUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        token_service: ITokenService,
        password_hasher: IPasswordHasher,
    ):
        self.user_repo = user_repo
        self.token_service = token_service
        self.password_hasher = password_hasher

    def authenticate_user(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Authenticates a user and returns access and refresh tokens.
        """
        correlation_id = correlation_id_ctx.get()
        user = self.user_repo.get_by_email(email)

        if not user:
            log_audit_event(
                AuditEvent.LOGIN_FAILED,
                "Failure: User not found",
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
                details={"email": email},
            )
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            log_audit_event(
                AuditEvent.LOGIN_FAILED,
                "Failure: Inactive account",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
            )
            raise AuthenticationError("User account is inactive")

        if not self.password_hasher.verify_password(password, user.hashed_password):
            log_audit_event(
                AuditEvent.LOGIN_FAILED,
                "Failure: Invalid password",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
            )
            raise AuthenticationError("Invalid email or password")

        data = {"sub": user.id, "email": user.email}
        access_token = self.token_service.create_access_token(data=data)
        refresh_token = self.token_service.create_refresh_token(data=data)

        log_audit_event(
            AuditEvent.LOGIN_SUCCESS,
            "Success",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )

        return {"access_token": access_token, "refresh_token": refresh_token}

    def verify_access_token(self, token: str) -> User:
        """
        Verifies a JWT token and returns the corresponding User.
        """
        try:
            payload = self.token_service.verify_token(token)
            if payload.get("type") != "access":
                raise AuthenticationError("Invalid token type")

            user_id = payload.get("sub")
            if user_id is None:
                raise AuthenticationError("Could not validate credentials")

            user = self.user_repo.get_by_id(user_id)
            if user is None:
                raise AuthenticationError("User not found")

            if not user.is_active:
                raise AuthenticationError("User account is inactive")

            return user
        except Exception as e:
            raise AuthenticationError(f"Token validation failed: {str(e)}")

    def refresh_access_token(
        self,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, str]:
        correlation_id = correlation_id_ctx.get()
        try:
            payload = self.token_service.verify_token(refresh_token)
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid token type")

            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Invalid token payload")
            user = self.user_repo.get_by_id(user_id)

            if not user or not user.is_active:
                raise AuthenticationError("Invalid user")

            # Revoke old refresh token (sliding session)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                expires_in = int(
                    exp - datetime.datetime.now(datetime.timezone.utc).timestamp()
                )
                if expires_in > 0:
                    self.token_service.revoke_token(jti, expires_in)

            data = {"sub": user.id, "email": user.email}
            new_access = self.token_service.create_access_token(data=data)
            new_refresh = self.token_service.create_refresh_token(data=data)

            log_audit_event(
                AuditEvent.TOKEN_REFRESH,
                "Success",
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
            )

            return {"access_token": new_access, "refresh_token": new_refresh}
        except Exception as e:
            log_audit_event(
                AuditEvent.TOKEN_REFRESH,
                f"Failure: {str(e)}",
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
            )
            raise AuthenticationError("Invalid refresh token")

    def logout(
        self,
        access_token: str,
        refresh_token: Optional[str],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        correlation_id = correlation_id_ctx.get()
        user_id = "unknown"

        try:
            payload = self.token_service.verify_token(access_token)
            user_id = payload.get("sub", "unknown")
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                expires_in = int(
                    exp - datetime.datetime.now(datetime.timezone.utc).timestamp()
                )
                if expires_in > 0:
                    self.token_service.revoke_token(jti, expires_in)
        except Exception:
            pass  # Ignore validation errors on logout (e.g. already expired)

        if refresh_token:
            try:
                rt_payload = self.token_service.verify_token(refresh_token)
                jti = rt_payload.get("jti")
                exp = rt_payload.get("exp")
                if jti and exp:
                    expires_in = int(
                        exp - datetime.datetime.now(datetime.timezone.utc).timestamp()
                    )
                    if expires_in > 0:
                        self.token_service.revoke_token(jti, expires_in)
            except Exception:
                pass

        log_audit_event(
            AuditEvent.LOGOUT,
            "Success",
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
