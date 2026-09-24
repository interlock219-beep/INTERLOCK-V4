from __future__ import annotations

import time

import pytest

from app.domain.exceptions.domain_errors import ExecutionTokenError
from app.infrastructure.security.ed25519_execution_token_service import (
    Ed25519ExecutionTokenService,
)
from app.infrastructure.security.env_key_manager import EnvKeyManager
from app.infrastructure.security.memory_nonce_store import MemoryNonceStore


@pytest.fixture
def token_service():
    key_manager = EnvKeyManager(jwt_secret="test-secret-key-that-is-at-least-32-characters-long")
    nonce_store = MemoryNonceStore()
    return Ed25519ExecutionTokenService(
        key_manager=key_manager,
        nonce_store=nonce_store,
        clock_skew_seconds=30,
    )


def test_create_token_with_audience_and_resource(token_service):
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="file_reader",
        ttl_seconds=60,
        tenant_id="tenant-1",
        audience="api.intentlock.io",
        resource="db.users",
    )
    payload = token_service.verify_execution_token(
        token,
        expected_tenant_id="tenant-1",
        expected_audience="api.intentlock.io",
        expected_resource="db.users",
    )
    assert payload["agent_id"] == "agent-1"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["aud"] == "api.intentlock.io"
    assert payload["resource"] == "db.users"


def test_verify_token_rejects_wrong_tenant(token_service):
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="file_reader",
        ttl_seconds=60,
        tenant_id="tenant-1",
    )
    with pytest.raises(ExecutionTokenError, match="tenant_id mismatch"):
        token_service.verify_execution_token(
            token,
            expected_tenant_id="tenant-2",
        )


def test_verify_token_rejects_wrong_audience(token_service):
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="file_reader",
        ttl_seconds=60,
        audience="api.intentlock.io",
    )
    with pytest.raises(ExecutionTokenError, match="audience mismatch"):
        token_service.verify_execution_token(
            token,
            expected_audience="other.api",
        )


def test_verify_token_rejects_wrong_resource(token_service):
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="file_reader",
        ttl_seconds=60,
        resource="db.users",
    )
    with pytest.raises(ExecutionTokenError, match="resource mismatch"):
        token_service.verify_execution_token(
            token,
            expected_resource="db.other",
        )


def test_verify_token_allows_none_expected_when_claim_present(token_service):
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="file_reader",
        ttl_seconds=60,
        tenant_id="tenant-1",
    )
    payload = token_service.verify_execution_token(token)
    assert payload["tenant_id"] == "tenant-1"


def test_peek_token_does_not_consume_nonce(token_service):
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="file_reader",
        ttl_seconds=60,
    )
    payload1 = token_service.peek_execution_token(token)
    assert payload1["agent_id"] == "agent-1"

    payload2 = token_service.verify_execution_token(token)
    assert payload2["agent_id"] == "agent-1"


def test_peek_token_enforces_claims(token_service):
    token = token_service.create_execution_token(
        agent_id="agent-1",
        tool="file_reader",
        ttl_seconds=60,
        audience="api.intentlock.io",
    )
    with pytest.raises(ExecutionTokenError, match="audience mismatch"):
        token_service.peek_execution_token(
            token,
            expected_audience="other.api",
        )
