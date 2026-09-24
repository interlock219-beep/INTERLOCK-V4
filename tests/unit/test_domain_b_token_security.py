import hashlib
import time

import jwt
import pytest

from app.domain.exceptions.domain_errors import ExecutionTokenError
from app.domain.services.token_scope_enforcement_service import (
    TokenScopeEnforcementService,
)
from app.infrastructure.security.ed25519_execution_token_service import (
    Ed25519ExecutionTokenService,
)
from app.infrastructure.security.env_key_manager import EnvKeyManager
from app.infrastructure.security.memory_nonce_store import MemoryNonceStore


JWT_SECRET = "test-secret-key-that-is-at-least-32-characters-long"


@pytest.fixture
def token_service() -> Ed25519ExecutionTokenService:
    key_manager = EnvKeyManager(jwt_secret=JWT_SECRET)
    nonce_store = MemoryNonceStore()
    return Ed25519ExecutionTokenService(
        key_manager=key_manager,
        nonce_store=nonce_store,
        clock_skew_seconds=30,
    )


# ---------------------------------------------------------------------------
# Feature 16: Action restriction inside execution-token claims
# ---------------------------------------------------------------------------

def test_create_token_with_action_claim(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60, action="execute"
    )
    payload = token_service.verify_execution_token(
        token, expected_action="execute"
    )
    assert payload["action"] == "execute"


def test_verify_token_action_mismatch_denies(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60, action="execute"
    )
    with pytest.raises(ExecutionTokenError, match="action mismatch"):
        token_service.verify_execution_token(token, expected_action="approve")


def test_token_without_action_claim_allows_when_not_required(
    token_service: Ed25519ExecutionTokenService,
) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60
    )
    payload = token_service.verify_execution_token(token)
    assert "action" not in payload


# ---------------------------------------------------------------------------
# Feature 17: Resource restriction inside execution-token claims
# ---------------------------------------------------------------------------

def test_create_token_with_resource_hash(token_service: Ed25519ExecutionTokenService) -> None:
    resource = "files/report.pdf"
    expected_hash = Ed25519ExecutionTokenService.compute_resource_hash(resource)
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="read_file", ttl_seconds=60,
        resource=resource, resource_hash=expected_hash,
    )
    payload = token_service.verify_execution_token(
        token, expected_resource=resource
    )
    assert payload["resource"] == resource
    assert payload["resource_hash"] == expected_hash


def test_verify_token_resource_mismatch_denies(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60,
        resource="files/report.pdf",
    )
    with pytest.raises(ExecutionTokenError, match="resource mismatch"):
        token_service.verify_execution_token(token, expected_resource="files/other.pdf")


def test_verify_token_resource_hash_tamper_detected(token_service: Ed25519ExecutionTokenService) -> None:
    resource = "files/report.pdf"
    correct_hash = Ed25519ExecutionTokenService.compute_resource_hash(resource)
    tampered_hash = "a" * 64
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="read_file", ttl_seconds=60,
        resource=resource, resource_hash=tampered_hash,
    )
    with pytest.raises(ExecutionTokenError, match="resource hash mismatch"):
        token_service.verify_execution_token(
            token, expected_resource=resource
        )


# ---------------------------------------------------------------------------
# Feature 18: Session restriction inside execution-token claims
# ---------------------------------------------------------------------------

def test_create_token_with_session_id(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="run_task", ttl_seconds=60,
        session_id="session-abc-123",
    )
    payload = token_service.verify_execution_token(
        token, expected_session_id="session-abc-123"
    )
    assert payload["session_id"] == "session-abc-123"


def test_verify_token_session_mismatch_denies(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="run_task", ttl_seconds=60,
        session_id="session-abc-123",
    )
    with pytest.raises(ExecutionTokenError, match="session mismatch"):
        token_service.verify_execution_token(
            token, expected_session_id="session-other-456"
        )


def test_token_reuse_after_session_revoked_denies(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="run_task", ttl_seconds=60,
        session_id="session-frozen",
    )
    token_service.verify_execution_token(token, expected_session_id="session-frozen")
    with pytest.raises(ExecutionTokenError):
        token_service.verify_execution_token(
            token, expected_session_id="session-frozen"
        )


# ---------------------------------------------------------------------------
# Feature 19: Tenant restriction inside execution-token claims
# ---------------------------------------------------------------------------

def test_token_cross_tenant_use_denied(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60,
        tenant_id="tenant-a",
    )
    with pytest.raises(ExecutionTokenError, match="tenant_id mismatch|cross-tenant"):
        token_service.verify_execution_token(
            token, expected_tenant_id="tenant-b"
        )


def test_token_missing_tenant_id_denied(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60,
    )
    with pytest.raises(ExecutionTokenError, match="tenant_id|cross-tenant|missing"):
        token_service.verify_execution_token(
            token, expected_tenant_id="tenant-a"
        )


def test_token_tenant_id_format_validated(token_service: Ed25519ExecutionTokenService) -> None:
    long_tenant = "x" * 65
    with pytest.raises(ValueError, match="tenant_id"):
        token_service.create_execution_token(
            agent_id="agent-123", tool="transfer_funds", ttl_seconds=60,
            tenant_id=long_tenant,
        )


# ---------------------------------------------------------------------------
# Feature 20: Parameter binding/hash inside execution-token claims
# ---------------------------------------------------------------------------

def test_create_token_with_param_hash(token_service: Ed25519ExecutionTokenService) -> None:
    params = {"amount": "100.00", "to": "user-456"}
    canonical = sorted(str(k) for k in params)
    expected_hash = hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60,
        param_hash=expected_hash,
    )
    payload = token_service.verify_execution_token(
        token, expected_param_hash=expected_hash
    )
    assert payload["param_hash"] == expected_hash


def test_verify_token_param_hash_mismatch_denies(token_service: Ed25519ExecutionTokenService) -> None:
    params = {"amount": "100.00", "to": "user-456"}
    canonical = sorted(str(k) for k in params)
    correct_hash = hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()
    wrong_hash = "a" * 64
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60,
        param_hash=correct_hash,
    )
    with pytest.raises(ExecutionTokenError, match="parameter hash mismatch"):
        token_service.verify_execution_token(token, expected_param_hash=wrong_hash)


def test_verify_token_param_hash_match_allows(token_service: Ed25519ExecutionTokenService) -> None:
    params = {"amount": "100.00", "to": "user-456"}
    canonical = sorted(str(k) for k in params)
    expected_hash = hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60,
        param_hash=expected_hash,
    )
    payload = token_service.verify_execution_token(
        token, expected_param_hash=expected_hash
    )
    assert payload["param_hash"] == expected_hash


# ---------------------------------------------------------------------------
# TokenScopeEnforcementService unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def scope_service() -> TokenScopeEnforcementService:
    return TokenScopeEnforcementService()


def test_token_scope_enforcement_service_action_check(scope_service: TokenScopeEnforcementService) -> None:
    payload = {"action": "execute", "tool": "run"}
    decision, reason = scope_service.enforce_scope(
        payload, expected_action="execute"
    )
    assert decision.value == "allow"

    decision, reason = scope_service.enforce_scope(
        payload, expected_action="approve"
    )
    assert decision.value == "deny"
    assert "action mismatch" in reason


def test_token_scope_enforcement_service_resource_check(scope_service: TokenScopeEnforcementService) -> None:
    resource = "files/report.pdf"
    resource_hash = TokenScopeEnforcementService.compute_resource_hash(resource)
    payload = {"resource": resource, "resource_hash": resource_hash}
    decision, _ = scope_service.enforce_scope(payload, expected_resource=resource)
    assert decision.value == "allow"

    decision, reason = scope_service.enforce_scope(
        payload, expected_resource="files/other.pdf"
    )
    assert decision.value == "deny"
    assert "resource mismatch" in reason


def test_token_scope_enforcement_service_session_check(scope_service: TokenScopeEnforcementService) -> None:
    payload = {"session_id": "session-123"}
    decision, _ = scope_service.enforce_scope(
        payload, expected_session_id="session-123"
    )
    assert decision.value == "allow"

    decision, reason = scope_service.enforce_scope(
        payload, expected_session_id="session-other"
    )
    assert decision.value == "deny"
    assert "session mismatch" in reason


def test_token_scope_enforcement_service_tenant_check(scope_service: TokenScopeEnforcementService) -> None:
    payload = {"tenant_id": "tenant-a"}
    decision, _ = scope_service.enforce_scope(
        payload, expected_tenant_id="tenant-a"
    )
    assert decision.value == "allow"

    payload_empty = {"tenant_id": ""}
    decision, reason = scope_service.enforce_scope(
        payload_empty, expected_tenant_id="tenant-a"
    )
    assert decision.value == "deny"
    assert "missing tenant_id" in reason.lower() or "cross-tenant" in reason.lower()

    payload_cross = {"tenant_id": "tenant-b"}
    decision, reason = scope_service.enforce_scope(
        payload_cross, expected_tenant_id="tenant-a"
    )
    assert decision.value == "deny"
    assert "tenant mismatch" in reason.lower() or "cross-tenant" in reason.lower()


def test_token_scope_enforcement_service_param_check(scope_service: TokenScopeEnforcementService) -> None:
    params = {"key": "value"}
    expected_hash = scope_service.compute_param_hash(params)
    payload = {"param_hash": expected_hash}
    decision, _ = scope_service.enforce_scope(
        payload, expected_param_hash=expected_hash
    )
    assert decision.value == "allow"

    decision, reason = scope_service.enforce_scope(
        payload, expected_param_hash="a" * 64
    )
    assert decision.value == "deny"
    assert "parameter hash mismatch" in reason.lower() or "substitution" in reason.lower()


def test_compute_resource_hash_deterministic(scope_service: TokenScopeEnforcementService) -> None:
    h1 = scope_service.compute_resource_hash("api/v1/users")
    h2 = scope_service.compute_resource_hash("api/v1/users")
    assert h1 == h2
    assert len(h1) == 64


def test_compute_param_hash_deterministic(scope_service: TokenScopeEnforcementService) -> None:
    params = {"z": "1", "a": "2"}
    h1 = scope_service.compute_param_hash(params)
    h2 = scope_service.compute_param_hash(params)
    assert h1 == h2
    assert len(h1) == 64


# ---------------------------------------------------------------------------
# Regression / integration tests
# ---------------------------------------------------------------------------

def test_token_replay_still_blocked_by_nonce(token_service: Ed25519ExecutionTokenService) -> None:
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="transfer_funds", ttl_seconds=60,
    )
    token_service.verify_execution_token(token)
    with pytest.raises(ExecutionTokenError, match="already been used"):
        token_service.verify_execution_token(token)


def test_token_with_all_scope_restrictions(token_service: Ed25519ExecutionTokenService) -> None:
    resource = "api/v1/orders"
    resource_hash = Ed25519ExecutionTokenService.compute_resource_hash(resource)
    params = {"order_id": "1001", "action": "create"}
    param_hash = Ed25519ExecutionTokenService.compute_param_hash(params)
    token = token_service.create_execution_token(
        agent_id="agent-123", tool="manage_orders", ttl_seconds=60,
        tenant_id="tenant-x",
        resource=resource,
        resource_hash=resource_hash,
        action="create",
        session_id="session-789",
        param_hash=param_hash,
    )
    payload = token_service.verify_execution_token(
        token,
        expected_tenant_id="tenant-x",
        expected_resource=resource,
        expected_action="create",
        expected_session_id="session-789",
        expected_param_hash=param_hash,
    )
    assert payload["tenant_id"] == "tenant-x"
    assert payload["resource"] == resource
    assert payload["action"] == "create"
    assert payload["session_id"] == "session-789"


def test_cross_tenant_token_isolation(token_service: Ed25519ExecutionTokenService) -> None:
    token_a = token_service.create_execution_token(
        agent_id="agent-a", tool="transfer_funds", ttl_seconds=60,
        tenant_id="tenant-a",
    )
    token_service.verify_execution_token(token_a, expected_tenant_id="tenant-a")

    with pytest.raises(ExecutionTokenError, match="tenant_id mismatch|cross-tenant"):
        token_service.verify_execution_token(token_a, expected_tenant_id="tenant-b")
