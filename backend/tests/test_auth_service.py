"""M20 auth-service unit tests.

`AuthUseCase` was the least-covered security-critical module. These tests
exercise its branches with mocked domain ports (repo / token service / hasher)
— no DB, no network.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from app.application.auth.services import AuthenticationError, AuthUseCase


def _user(active=True):
    return SimpleNamespace(
        id="u-1", email="a@b.local", hashed_password="hashed", is_active=active
    )


class _Repo:
    def __init__(self, by_email=None, by_id=None):
        self._by_email = by_email
        self._by_id = by_id

    def get_by_email(self, email):
        return self._by_email

    def get_by_id(self, uid):
        return self._by_id


class _Tokens:
    def __init__(self, payload=None):
        self._payload = payload or {}
        self.revoked = []

    def create_access_token(self, data):
        return "access-token"

    def create_refresh_token(self, data):
        return "refresh-token"

    def verify_token(self, token):
        return self._payload

    def revoke_token(self, jti, expires_in):
        self.revoked.append((jti, expires_in))


class _Hasher:
    def __init__(self, ok=True):
        self._ok = ok

    def verify_password(self, raw, hashed):
        return self._ok


def _future_exp():
    return datetime.datetime.now(datetime.timezone.utc).timestamp() + 3600


# --- authenticate_user --------------------------------------------------------


def test_authenticate_success_returns_tokens():
    uc = AuthUseCase(_Repo(by_email=_user()), _Tokens(), _Hasher(ok=True))
    out = uc.authenticate_user("a@b.local", "pw")
    assert out == {"access_token": "access-token", "refresh_token": "refresh-token"}


def test_authenticate_unknown_user_raises():
    uc = AuthUseCase(_Repo(by_email=None), _Tokens(), _Hasher())
    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        uc.authenticate_user("nope@b.local", "pw")


def test_authenticate_inactive_user_raises():
    uc = AuthUseCase(_Repo(by_email=_user(active=False)), _Tokens(), _Hasher())
    with pytest.raises(AuthenticationError, match="inactive"):
        uc.authenticate_user("a@b.local", "pw")


def test_authenticate_bad_password_raises():
    uc = AuthUseCase(_Repo(by_email=_user()), _Tokens(), _Hasher(ok=False))
    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        uc.authenticate_user("a@b.local", "wrong")


# --- verify_access_token ------------------------------------------------------


def test_verify_access_token_valid():
    tokens = _Tokens(payload={"type": "access", "sub": "u-1"})
    uc = AuthUseCase(_Repo(by_id=_user()), tokens, _Hasher())
    assert uc.verify_access_token("t").id == "u-1"


def test_verify_access_token_wrong_type():
    tokens = _Tokens(payload={"type": "refresh", "sub": "u-1"})
    uc = AuthUseCase(_Repo(by_id=_user()), tokens, _Hasher())
    with pytest.raises(AuthenticationError):
        uc.verify_access_token("t")


def test_verify_access_token_missing_sub():
    tokens = _Tokens(payload={"type": "access"})
    uc = AuthUseCase(_Repo(by_id=_user()), tokens, _Hasher())
    with pytest.raises(AuthenticationError):
        uc.verify_access_token("t")


def test_verify_access_token_user_not_found():
    tokens = _Tokens(payload={"type": "access", "sub": "u-1"})
    uc = AuthUseCase(_Repo(by_id=None), tokens, _Hasher())
    with pytest.raises(AuthenticationError):
        uc.verify_access_token("t")


def test_verify_access_token_inactive():
    tokens = _Tokens(payload={"type": "access", "sub": "u-1"})
    uc = AuthUseCase(_Repo(by_id=_user(active=False)), tokens, _Hasher())
    with pytest.raises(AuthenticationError):
        uc.verify_access_token("t")


# --- refresh_access_token -----------------------------------------------------


def test_refresh_success_revokes_old_and_issues_new():
    tokens = _Tokens(
        payload={"type": "refresh", "sub": "u-1", "jti": "j1", "exp": _future_exp()}
    )
    uc = AuthUseCase(_Repo(by_id=_user()), tokens, _Hasher())
    out = uc.refresh_access_token("rt")
    assert out["access_token"] == "access-token"
    assert tokens.revoked and tokens.revoked[0][0] == "j1"


def test_refresh_wrong_type_raises():
    tokens = _Tokens(payload={"type": "access", "sub": "u-1"})
    uc = AuthUseCase(_Repo(by_id=_user()), tokens, _Hasher())
    with pytest.raises(AuthenticationError, match="Invalid refresh token"):
        uc.refresh_access_token("rt")


def test_refresh_invalid_user_raises():
    tokens = _Tokens(payload={"type": "refresh", "sub": "u-1"})
    uc = AuthUseCase(_Repo(by_id=None), tokens, _Hasher())
    with pytest.raises(AuthenticationError):
        uc.refresh_access_token("rt")


# --- logout -------------------------------------------------------------------


def test_logout_revokes_both_tokens():
    tokens = _Tokens(payload={"sub": "u-1", "jti": "j1", "exp": _future_exp()})
    uc = AuthUseCase(_Repo(), tokens, _Hasher())
    uc.logout("at", "rt")
    # access + refresh both verified via the same payload → two revocations
    assert len(tokens.revoked) == 2


def test_logout_swallows_invalid_token():
    class _Boom(_Tokens):
        def verify_token(self, token):
            raise ValueError("bad token")

    uc = AuthUseCase(_Repo(), _Boom(), _Hasher())
    uc.logout("at", None)  # must not raise
