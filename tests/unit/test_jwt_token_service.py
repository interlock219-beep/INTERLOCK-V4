from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.exceptions.domain_errors import AuthenticationError
from app.infrastructure.security.jwt_token_service import JWTTokenService


def make_service():
    return JWTTokenService(
        secret_key="test-secret-key-that-is-at-least-32-characters-long",
        algorithm="HS256",
        expire_minutes=30,
        clock_skew_seconds=30,
    )


def test_create_access_token_without_session():
    service = make_service()
    user_id = UUID(int=1)
    token = service.create_access_token(user_id=user_id, email="user@example.com")
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_access_token_with_session():
    service = make_service()
    user_id = UUID(int=1)
    token = service.create_access_token(
        user_id=user_id, email="user@example.com", session_id="session-1"
    )
    assert isinstance(token, str)


def test_decode_access_token_success():
    service = make_service()
    user_id = UUID(int=1)
    token = service.create_access_token(user_id=user_id, email="user@example.com")
    payload = service.decode_access_token(token)
    assert payload.sub == user_id
    assert payload.email == "user@example.com"
    assert payload.jti is not None
    assert payload.sid == ""


def test_decode_access_token_invalid():
    service = make_service()
    with pytest.raises(AuthenticationError, match="Invalid or expired access token"):
        service.decode_access_token("invalid.token.here")


def test_decode_access_token_wrong_type():
    service = make_service()
    import jwt
    payload = {
        "sub": str(UUID(int=1)),
        "email": "user@example.com",
        "iat": datetime.now(UTC),
        "nbf": datetime.now(UTC),
        "exp": datetime.now(UTC)
        + __import__("datetime").timedelta(minutes=30),
        "jti": str(uuid4()),
        "type": "refresh",
    }
    token = jwt.encode(
        payload,
        "test-secret-key-that-is-at-least-32-characters-long",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError, match="Invalid token type"):
        service.decode_access_token(token)
