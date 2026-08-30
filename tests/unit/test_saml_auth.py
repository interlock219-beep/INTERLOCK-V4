from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.use_cases.saml_auth import SAMLAuthUseCase
from app.domain.entities.user import User
from app.domain.exceptions.domain_errors import AuthenticationError
from app.domain.services.sso_services import SSOCallbackResult


class StubUserRepository:
    def __init__(self, user: User | None) -> None:
        self._user = user

    async def get_by_id(self, user_id: str) -> User | None:
        return self._user


class StubTokenService:
    def create_access_token(self, *, user_id: str, email: str, session_id: str | None) -> str:
        return f"access-{user_id}"


class StubSessionService:
    async def create_session(self, *, user_id: str, ttl_seconds: int) -> tuple[str, str]:
        return f"session-{user_id}", "2025-01-01T00:00:00Z"


class StubAccountLinking:
    pass


@pytest.mark.asyncio
async def test_handle_callback_authorized_with_session() -> None:
    user_id = str(uuid4())
    user = User(
        id=user_id,
        email="user@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.now(UTC),
        role="user",
        tenant_id="tenant-1",
    )
    repo = StubUserRepository(user)
    token_service = StubTokenService()
    session_service = StubSessionService()
    use_case = SAMLAuthUseCase(
        user_repository=repo,
        token_service=token_service,
        session_service=session_service,
        account_linking=StubAccountLinking(),
    )
    result = await use_case.handle_callback(
        SSOCallbackResult(result="authorized", user_id=user_id)
    )
    assert result["access_token"] == f"access-{user_id}"
    assert result["refresh_token"] == f"session-{user_id}"
    assert result["token_type"] == "bearer"
    assert result["user"]["id"] == user_id
    assert result["user"]["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_handle_callback_authorized_without_session_service() -> None:
    user_id = str(uuid4())
    user = User(
        id=user_id,
        email="user@example.com",
        hashed_password="hashed",
        is_active=True,
        created_at=datetime.now(UTC),
        role="user",
        tenant_id="tenant-1",
    )
    repo = StubUserRepository(user)
    token_service = StubTokenService()
    use_case = SAMLAuthUseCase(
        user_repository=repo,
        token_service=token_service,
        session_service=None,
        account_linking=StubAccountLinking(),
    )
    result = await use_case.handle_callback(
        SSOCallbackResult(result="authorized", user_id=user_id)
    )
    assert result["access_token"] == f"access-{user_id}"
    assert result["refresh_token"] is None


@pytest.mark.asyncio
async def test_handle_callback_not_authorized() -> None:
    repo = StubUserRepository(None)
    token_service = StubTokenService()
    use_case = SAMLAuthUseCase(
        user_repository=repo,
        token_service=token_service,
        session_service=None,
        account_linking=StubAccountLinking(),
    )
    with pytest.raises(AuthenticationError):
        await use_case.handle_callback(SSOCallbackResult(result="denied", error="access_denied"))


@pytest.mark.asyncio
async def test_handle_callback_missing_user_id() -> None:
    repo = StubUserRepository(None)
    token_service = StubTokenService()
    use_case = SAMLAuthUseCase(
        user_repository=repo,
        token_service=token_service,
        session_service=None,
        account_linking=StubAccountLinking(),
    )
    with pytest.raises(AuthenticationError):
        await use_case.handle_callback(SSOCallbackResult(result="authorized", user_id=None))


@pytest.mark.asyncio
async def test_handle_callback_user_not_found() -> None:
    repo = StubUserRepository(None)
    token_service = StubTokenService()
    use_case = SAMLAuthUseCase(
        user_repository=repo,
        token_service=token_service,
        session_service=None,
        account_linking=StubAccountLinking(),
    )
    with pytest.raises(AuthenticationError, match="SAML user not found"):
        await use_case.handle_callback(
            SSOCallbackResult(result="authorized", user_id=str(uuid4()))
        )
