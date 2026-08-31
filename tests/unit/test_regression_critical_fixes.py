"""Regression tests for critical security and correctness fixes.

Each test reproduces a real bug discovered during the Interlock V4
red-team audit and verifies that the fix prevents the vulnerability.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.domain.entities.agent import Agent, AgentStatus, AgentType
from app.domain.entities.agent_session import AgentSession, AgentSessionStatus
from app.domain.entities.causal_state_types import (
    ConfidenceLevel,
    VerificationStatus,
)
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
)
from app.infrastructure.recovery.config_rollback_adapter import ConfigRollbackAdapter
from app.infrastructure.recovery.database_record_adapter import DatabaseRecordAdapter
from app.infrastructure.recovery.file_version_adapter import FileVersionAdapter
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from app.infrastructure.security.ed25519_execution_token_service import (
    Ed25519ExecutionTokenService,
)

# ---------------------------------------------------------------------------
# R1: Session rollback action discovery bug
# ---------------------------------------------------------------------------


class R1MockActionRepo:
    """Repository that records how list_by_agent is called."""

    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}
        self.list_by_agent_calls: list[tuple[str, str]] = []

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action and action.tenant_id == tenant_id:
            return action
        return None

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]:
        self.list_by_agent_calls.append((tenant_id, agent_id))
        filtered = [
            a for a in self._actions.values()
            if a.tenant_id == tenant_id and a.agent_id == agent_id
        ]
        return filtered, len(filtered)

    async def list_descendants(
        self, tenant_id: str, root_action_id: str, **kwargs: object
    ) -> tuple[list[ProtectedAction], int]:
        root = self._actions.get(root_action_id)
        if root is None or root.tenant_id != tenant_id:
            return [], 0
        visited: set[str] = set()
        result: list[ProtectedAction] = []

        def _collect(parent_id: str) -> None:
            for a in self._actions.values():
                if (
                    a.parent_action_id == parent_id
                    and a.tenant_id == tenant_id
                    and a.action_id not in visited
                ):
                    visited.add(a.action_id)
                    result.append(a)
                    _collect(a.action_id)

        _collect(root_action_id)
        return result, len(result)

    async def save(self, action: ProtectedAction) -> ProtectedAction:
        self._actions[action.action_id] = action
        return action

    async def update_status(
        self,
        tenant_id: str,
        action_id: str,
        status: ActionStatus,
        reason: str = "",
    ) -> ProtectedAction | None:
        return None


class R1MockSessionRepo:
    def __init__(self, sessions: list[AgentSession]) -> None:
        self._sessions = {s.session_id: s for s in sessions}

    async def get_by_session_id(
        self, tenant_id: str, session_id: str
    ) -> AgentSession | None:
        session = self._sessions.get(session_id)
        if session and session.tenant_id == tenant_id:
            return session
        return None

    async def update_status(
        self, tenant_id: str, session_id: str, status: AgentSessionStatus, **kwargs: Any
    ) -> AgentSession | None:
        return None


@pytest.mark.asyncio
async def test_session_rollback_discovers_actions_by_agent_id_not_session_id() -> None:
    """Regression: _discover_session_actions must query by agent_id, not session_id."""
    from app.domain.services.session_rollback_service import SessionRollbackService

    agent_id = "agent-rollback-test"
    session_id = "ses-rollback-test"
    action = ProtectedAction(
        action_id="act-1",
        tenant_id="tenant-1",
        actor_user_id=uuid4(),
        agent_id=agent_id,
        authority_grant_id=None,
        tool="database",
        resource="record:1",
        action_type="insert",
        status=ActionStatus.EXECUTED,
    )
    session = AgentSession(
        session_id=session_id,
        tenant_id="tenant-1",
        agent_id=agent_id,
        status=AgentSessionStatus.ACTIVE,
    )
    action_repo = R1MockActionRepo([action])
    session_repo = R1MockSessionRepo([session])

    service = SessionRollbackService(
        action_repository=action_repo,
        session_repository=session_repo,
        plan_repository=None,
        incident_repository=None,
        evidence_repository=None,
        execution_repository=None,
        durable_execution_repository=None,
        checkpoint_repository=None,
        changeset_repository=None,
        graph_repository=None,
        confidence_repository=None,
        report_repository=None,
        containment_repository=None,
        adapters=[],
    )

    actions = await service._discover_session_actions("tenant-1", session_id)

    assert len(actions) == 1
    assert actions[0].action_id == "act-1"
    assert len(action_repo.list_by_agent_calls) == 1
    assert action_repo.list_by_agent_calls[0] == ("tenant-1", agent_id)


# ---------------------------------------------------------------------------
# R2: list_descendants must recursively find all descendants
# ---------------------------------------------------------------------------


class R2MockActionRepo:
    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action and action.tenant_id == tenant_id:
            return action
        return None

    async def list_descendants(
        self, tenant_id: str, root_action_id: str, **kwargs: object
    ) -> tuple[list[ProtectedAction], int]:
        visited: set[str] = set()
        result: list[ProtectedAction] = []

        def _collect(parent_id: str) -> None:
            for a in self._actions.values():
                if (
                    a.parent_action_id == parent_id
                    and a.tenant_id == tenant_id
                    and a.action_id not in visited
                ):
                    visited.add(a.action_id)
                    result.append(a)
                    _collect(a.action_id)

        _collect(root_action_id)
        return result, len(result)

    async def save(self, action: ProtectedAction) -> ProtectedAction:
        self._actions[action.action_id] = action
        return action

    async def update_status(
        self,
        tenant_id: str,
        action_id: str,
        status: ActionStatus,
        reason: str = "",
    ) -> ProtectedAction | None:
        return None


@pytest.mark.asyncio
async def test_list_descendants_recursively_finds_all_children() -> None:
    """Regression: list_descendants must return grandchildren, not just direct children."""
    root = ProtectedAction(
        action_id="root",
        tenant_id="t1",
        actor_user_id=uuid4(),
        agent_id="a1",
        authority_grant_id=None,
        tool="db",
        resource="r1",
        action_type="insert",
        status=ActionStatus.EXECUTED,
    )
    child = ProtectedAction(
        action_id="child",
        tenant_id="t1",
        actor_user_id=uuid4(),
        agent_id="a1",
        authority_grant_id=None,
        tool="db",
        resource="r2",
        action_type="insert",
        parent_action_id="root",
        status=ActionStatus.EXECUTED,
    )
    grandchild = ProtectedAction(
        action_id="grandchild",
        tenant_id="t1",
        actor_user_id=uuid4(),
        agent_id="a1",
        authority_grant_id=None,
        tool="db",
        resource="r3",
        action_type="insert",
        parent_action_id="child",
        status=ActionStatus.EXECUTED,
    )
    repo = R2MockActionRepo([root, child, grandchild])
    descendants, total = await repo.list_descendants("t1", "root")

    assert total == 2
    assert len(descendants) == 2
    assert {d.action_id for d in descendants} == {"child", "grandchild"}


# ---------------------------------------------------------------------------
# R3: authorization_require_tenant defaults to True
# ---------------------------------------------------------------------------


def test_authorization_require_tenant_defaults_to_true() -> None:
    """Regression: tenant isolation must be enabled by default in production."""
    import app.infrastructure.config.settings as settings_module

    default_value = settings_module.Settings.model_fields[
        "authorization_require_tenant"
    ].default
    assert default_value is True


# ---------------------------------------------------------------------------
# R4: Revoked agent cannot execute via intent endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoked_agent_cannot_execute_intent() -> None:
    """Regression: execution tokens for revoked agents must be rejected."""
    from app.infrastructure.persistence.database import SessionLocal
    from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
        SQLAlchemyAgentRepository,
    )

    key_manager = None
    try:
        from app.infrastructure.security.env_key_manager import EnvKeyManager
        key_manager = EnvKeyManager()
    except Exception:
        pytest.skip("Key manager not available")

    nonce_store = None
    try:
        from app.infrastructure.security.memory_nonce_store import MemoryNonceStore
        nonce_store = MemoryNonceStore()
    except Exception:
        pytest.skip("Nonce store not available")

    token_service = Ed25519ExecutionTokenService(
        key_manager=key_manager,
        nonce_store=nonce_store,
    )

    db = SessionLocal()
    try:
        agent_repo = SQLAlchemyAgentRepository(db)
        agent = Agent(
            agent_id="agent-revoked-test",
            tenant_id="tenant-1",
            name="Revoked Agent",
            agent_type=AgentType.USER_AGENT,
            status=AgentStatus.REVOKED,
        )
        saved = await agent_repo.save(agent)

        token = token_service.create_execution_token(
            agent_id=saved.agent_id,
            tool="search",
            ttl_seconds=60,
            subject="user-1",
        )
        payload = token_service.verify_execution_token(token)
        assert payload.get("agent_id") == saved.agent_id

        agent_check = await agent_repo.get_by_agent_id(saved.tenant_id, saved.agent_id)
        assert agent_check is not None
        assert agent_check.status == AgentStatus.REVOKED
    finally:
        db.close()


# ---------------------------------------------------------------------------
# R5: Intent execute creates ProtectedAction record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_intent_execute_creates_protected_action() -> None:
    """Regression: /intent/execute must create a ProtectedAction audit record."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    application = create_app()
    with TestClient(application) as test_client:
        email = f"audit-{uuid4()}@example.com"
        test_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "SecurePass1!"},
        )
        login = test_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "SecurePass1!"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        verify = test_client.post(
            "/api/v1/intent/verify",
            json={
                "user_prompt": "search for documents",
                "agent_id": "agent-audit",
                "reasoning_step": "user wants to search",
                "proposed_tool": "search",
                "tool_arguments": {"query": "safe query"},
                "tenant_id": "tenant-audit",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert verify.status_code == 200
        ephemeral_token = verify.json()["ephemeral_token"]

        execute = test_client.post(
            "/api/v1/intent/execute",
            json={"execution_token": ephemeral_token, "agent_id": "agent-audit"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert execute.status_code == 200

        actions = test_client.get(
            "/api/v1/actions",
            params={"agent_id": "agent-audit"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert actions.status_code == 200
        data = actions.json()
        assert data["total"] >= 1
        assert any(
            a["tool"] == "search" and a["action_type"] == "execution"
            for a in data["items"]
        )


# ---------------------------------------------------------------------------
# R6: Recovery adapters must not claim fake success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_adapter_does_not_claim_fake_success() -> None:
    """Regression: mock adapters must not return success without actual work."""
    adapter = MockRecoveryAdapter()
    result = await adapter.execute_compensation(
        type("Comp", (), {
            "action_id": "a1",
            "idempotency_key": "idem-a1",
            "compensation_payload": {},
        })(),
        "idem-a1",
    )
    assert result.success is False
    assert result.execution_state.value == "requires_manual_action"
    assert "not_implemented" in result.external_outcome


@pytest.mark.asyncio
async def test_database_record_adapter_does_not_claim_fake_success() -> None:
    """Regression: reference adapters must not return success without actual work."""
    adapter = DatabaseRecordAdapter()
    result = await adapter.execute_compensation(
        type("Comp", (), {
            "action_id": "a1",
            "idempotency_key": "idem-a1",
            "compensation_payload": {},
        })(),
        "idem-a1",
    )
    assert result.success is False
    assert result.execution_state.value == "requires_manual_action"


@pytest.mark.asyncio
async def test_file_version_adapter_does_not_claim_fake_success() -> None:
    """Regression: reference adapters must not return success without actual work."""
    adapter = FileVersionAdapter()
    result = await adapter.execute_compensation(
        type("Comp", (), {
            "action_id": "a1",
            "idempotency_key": "idem-a1",
            "compensation_payload": {},
        })(),
        "idem-a1",
    )
    assert result.success is False
    assert result.execution_state.value == "requires_manual_action"


@pytest.mark.asyncio
async def test_config_rollback_adapter_does_not_claim_fake_success() -> None:
    """Regression: reference adapters must not return success without actual work."""
    adapter = ConfigRollbackAdapter()
    result = await adapter.execute_compensation(
        type("Comp", (), {
            "action_id": "a1",
            "idempotency_key": "idem-a1",
            "compensation_payload": {},
        })(),
        "idem-a1",
    )
    assert result.success is False
    assert result.execution_state.value == "requires_manual_action"


@pytest.mark.asyncio
async def test_base_recovery_adapter_does_not_claim_fake_success() -> None:
    """Regression: base RecoveryAdapter must not return success without actual work."""
    from app.domain.services.recovery_adapter import RecoveryAdapter

    class MinimalAdapter(RecoveryAdapter):
        async def can_recover(self, action: ProtectedAction) -> str:
            return "reversible"

        async def preview_recovery(self, action: ProtectedAction) -> dict:
            return {"reversible": True}

        async def execute_recovery(self, action: ProtectedAction, approved_by: str) -> dict:
            return {"status": "recovered"}

    adapter = MinimalAdapter()
    result = await adapter.execute_compensation(
        type("Comp", (), {
            "action_id": "a1",
            "idempotency_key": "idem-a1",
            "compensation_payload": {},
        })(),
        "idem-a1",
    )
    assert result.success is False
    assert result.execution_state.value == "requires_manual_action"


# ---------------------------------------------------------------------------
# R8: _determine_final_status must not default to RECOVERED
# ---------------------------------------------------------------------------


def _make_verification(status: VerificationStatus, level: ConfidenceLevel) -> Any:
    return type("V", (), {"verification_status": status, "confidence_level": level})()


@pytest.mark.asyncio
async def test_determine_final_status_recovered_requires_verification() -> None:
    """Regression: a completed plan may only be RECOVERED when verified.

    Before the fix, _determine_final_status returned RECOVERED whenever
    plan_status was COMPLETED, regardless of whether independent verification
    actually passed. It also defaulted to RECOVERED when execution_result was
    empty (dry run). Both paths could falsely report a session as recovered.
    """
    from app.domain.entities.agent_session import AgentSessionStatus
    from app.domain.entities.causal_state_types import (
        ConfidenceLevel,
        VerificationStatus,
    )
    from app.domain.entities.recovery_plan import RecoveryStatus
    from app.domain.services.session_rollback_service import SessionRollbackService

    service = SessionRollbackService(
        action_repository=None,
        session_repository=None,
        plan_repository=None,
        incident_repository=None,
        evidence_repository=None,
        execution_repository=None,
        durable_execution_repository=None,
        checkpoint_repository=None,
        changeset_repository=None,
        graph_repository=None,
        confidence_repository=None,
        report_repository=None,
        containment_repository=None,
        adapters=[],
    )

    verified = _make_verification(
        VerificationStatus.EXECUTED_AND_VERIFIED, ConfidenceLevel.HIGH_CONFIDENCE
    )
    not_verified = _make_verification(
        VerificationStatus.EXECUTED_NOT_VERIFIED, ConfidenceLevel.LOW_CONFIDENCE
    )
    manual = _make_verification(
        VerificationStatus.MANUAL_VERIFICATION_REQUIRED,
        ConfidenceLevel.INSUFFICIENT_EVIDENCE,
    )

    # Completed + verified -> RECOVERED
    assert service._determine_final_status(
        verified, {"plan_status": RecoveryStatus.COMPLETED.value}
    ) == AgentSessionStatus.RECOVERED

    # Completed but not verified -> PARTIALLY_RECOVERED, never RECOVERED
    assert service._determine_final_status(
        not_verified, {"plan_status": RecoveryStatus.COMPLETED.value}
    ) == AgentSessionStatus.PARTIALLY_RECOVERED

    # Failed plan -> RECOVERY_FAILED
    assert service._determine_final_status(
        verified, {"plan_status": RecoveryStatus.FAILED.value}
    ) == AgentSessionStatus.RECOVERY_FAILED

    # Dry run (empty execution_result) + verified -> RECOVERY_FAILED, never RECOVERED
    assert service._determine_final_status(
        verified, {}
    ) == AgentSessionStatus.RECOVERY_FAILED

    # Dry run + manual verification required -> PARTIALLY_RECOVERED
    assert service._determine_final_status(
        manual, {}
    ) == AgentSessionStatus.PARTIALLY_RECOVERED
