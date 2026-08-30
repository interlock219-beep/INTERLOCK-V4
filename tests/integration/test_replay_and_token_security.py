"""Phase 15: Replay and token security tests.

Tests verify that execution tokens enforce single-use semantics,
reject expired tokens, reject tampered signatures, and enforce
correct agent and tenant bindings.
"""

from __future__ import annotations

import base64
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions.domain_errors import ExecutionTokenError
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.infrastructure.security.ed25519_execution_token_service import (
    Ed25519ExecutionTokenService,
)
from app.infrastructure.security.jwt_token_service import JWTTokenService
from app.infrastructure.security.memory_nonce_store import MemoryNonceStore
from app.infrastructure.security.versioned_key_manager import VersionedKeyManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user(client: TestClient, email: str, tenant_id: str, role: str = "admin") -> str:
    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SQLAlchemyUserRepository(session)
        from app.domain.entities.user import User

        user = User(
            id=uuid4(),
            email=email,
            hashed_password=BcryptPasswordHasher(rounds=4).hash("Password123!"),
            is_active=True,
            created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
            role=role,
            tenant_id=tenant_id,
        )
        saved = await repo.save(user)
        token = JWTTokenService(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            expire_minutes=settings.jwt_access_token_expire_minutes,
            clock_skew_seconds=settings.jwt_clock_skew_seconds,
        ).create_access_token(user_id=saved.id, email=saved.email)
        session.commit()
        return token
    finally:
        session.close()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_token_service() -> Ed25519ExecutionTokenService:
    key_manager = VersionedKeyManager(key_dir=None)
    nonce_store = MemoryNonceStore()
    return Ed25519ExecutionTokenService(
        key_manager=key_manager,
        nonce_store=nonce_store,
        clock_skew_seconds=30,
    )


# ---------------------------------------------------------------------------
# 1. Execution token replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execution_token_replay_rejected(client: TestClient) -> None:
    token = await _create_user(client, f"replay-{uuid4()}@example.com", "tenant-replay")
    payload = client.post(
        "/api/v1/intent/verify",
        json={
            "user_prompt": "search records",
            "agent_id": "agent-1",
            "reasoning_step": "normal",
            "proposed_tool": "search",
            "tool_arguments": {"query": "test"},
        },
        headers=_auth_headers(token),
    ).json()
    assert payload["is_valid"] is True
    exec_token = payload["ephemeral_token"]
    assert exec_token is not None

    first = client.post(
        "/api/v1/intent/execute",
        json={"execution_token": exec_token},
        headers=_auth_headers(token),
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/intent/execute",
        json={"execution_token": exec_token},
        headers=_auth_headers(token),
    )
    assert second.status_code == 401
    assert "already been used" in second.json()["detail"]


# ---------------------------------------------------------------------------
# 2. Expired execution token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_execution_token_rejected(client: TestClient) -> None:
    token_service = _make_token_service()
    expired_token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="test_tool",
        ttl_seconds=-1,
    )
    with pytest.raises(ExecutionTokenError):
        token_service.verify_execution_token(expired_token)


# ---------------------------------------------------------------------------
# 3. Tampered execution token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tampered_execution_token_signature_rejected(client: TestClient) -> None:
    token_service = _make_token_service()
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="safe_tool",
        ttl_seconds=300,
    )
    parts = token.split(".")
    tampered_sig = base64.urlsafe_b64encode(b"tampered").decode().rstrip("=")
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    with pytest.raises(ExecutionTokenError):
        token_service.verify_execution_token(tampered_token)


@pytest.mark.asyncio
async def test_tampered_execution_token_payload_rejected(client: TestClient) -> None:
    token_service = _make_token_service()
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="safe_tool",
        ttl_seconds=300,
    )
    parts = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
    payload["tool"] = "dangerous_tool"
    new_payload = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    tampered_token = f"{parts[0]}.{new_payload}.{parts[2]}"

    with pytest.raises(ExecutionTokenError):
        token_service.verify_execution_token(tampered_token)


# ---------------------------------------------------------------------------
# 4. Wrong agent binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_agent_binding_rejected_via_api(client: TestClient) -> None:
    token = await _create_user(client, f"bind-{uuid4()}@example.com", "tenant-bind")
    payload = client.post(
        "/api/v1/intent/verify",
        json={
            "user_prompt": "search records",
            "agent_id": "agent-owner",
            "reasoning_step": "normal",
            "proposed_tool": "search",
            "tool_arguments": {"query": "test"},
        },
        headers=_auth_headers(token),
    ).json()
    exec_token = payload["ephemeral_token"]

    resp = client.post(
        "/api/v1/intent/execute",
        json={"execution_token": exec_token, "agent_id": "agent-intruder"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 5. Wrong tenant binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_tenant_binding_rejected_via_api(client: TestClient) -> None:
    token_a = await _create_user(
        client, f"tenant-a-{uuid4()}@example.com", "tenant-alpha"
    )
    token_b = await _create_user(
        client, f"tenant-b-{uuid4()}@example.com", "tenant-beta"
    )

    payload_a = client.post(
        "/api/v1/intent/verify",
        json={
            "user_prompt": "search records",
            "agent_id": "agent-1",
            "reasoning_step": "normal",
            "proposed_tool": "search",
            "tool_arguments": {"query": "test"},
            "tenant_id": "tenant-alpha",
        },
        headers=_auth_headers(token_a),
    ).json()
    exec_token = payload_a["ephemeral_token"]

    resp = client.post(
        "/api/v1/intent/execute",
        json={"execution_token": exec_token},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Additional token security tests
# ---------------------------------------------------------------------------


def test_execution_token_missing_type_rejected() -> None:
    token_service = _make_token_service()
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="test",
        ttl_seconds=300,
    )
    parts = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
    del payload["type"]
    new_payload = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    bad_token = f"{parts[0]}.{new_payload}.{parts[2]}"

    with pytest.raises(ExecutionTokenError):
        token_service.verify_execution_token(bad_token)


def test_execution_token_unknown_kid_rejected() -> None:
    token_service = _make_token_service()
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="test",
        ttl_seconds=300,
    )
    parts = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(parts[0] + "=="))
    header["kid"] = "unknown-key-id"
    new_header = (
        base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    bad_token = f"{new_header}.{parts[1]}.{parts[2]}"

    with pytest.raises(ExecutionTokenError):
        token_service.verify_execution_token(bad_token)


def test_execution_token_with_retired_key_rejected() -> None:
    key_manager = VersionedKeyManager(key_dir=None)
    nonce_store = MemoryNonceStore()
    token_service = Ed25519ExecutionTokenService(
        key_manager=key_manager,
        nonce_store=nonce_store,
        clock_skew_seconds=30,
    )
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="test",
        ttl_seconds=300,
    )
    key_manager.rotate()
    key_manager.rotate()
    key_manager.rotate()

    with pytest.raises(ExecutionTokenError):
        token_service.verify_execution_token(token)
