"""INTERLOCK V6 — WP-8: execution-boundary bypass tests (PILLAR 6).

Mission text quoted verbatim (relevant PILLAR 6 lines):

    - Require approval for high-impact and irreversible operations.
    - Support emergency deny, circuit breaking, containment, and kill switches.
    - Record proposed, authorized, executed, and verified actions separately.
    - Ensure recovery tooling cannot silently exceed the authority of the
      original operation.
    - Test bypasses through alternate APIs, direct adapter calls, race
      conditions, and malformed inputs.

    A policy decision in the UI is insufficient if an alternate execution
    path bypasses enforcement.

Scope: the reachable execution entry points of the recovery engine and
direct-adapter call paths, each probed for a bypass:

* emergency deny (PILLAR 6 "emergency deny") must actually block every
  execution entry point — activation without enforcement is exactly the
  "policy decision in the UI" the mission calls out;
* approval gates (DRAFT / PENDING_APPROVAL plans) must refuse execution
  through the API (malformed/alternate input probing);
* tenant scoping must refuse cross-tenant plan execution (malformed input);
* direct adapter calls (bypassing orchestrator/routes) must fail closed on
  idempotency-key mismatches and path traversal outside the adapter root.

Race-condition bypasses (duplicate/reordered requests, stale workers) are
covered by WP-7's fault-injection matrix and the lease contract tests; this
file probes the API/adapter boundary itself.

BLOCKED (not simulated): multi-instance emergency-deny propagation requires
a shared backend (Redis/Postgres) that is out of scope for this run — the
guarantee proven here is single-process, matching the in-memory deny store.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.application.dto.auth import UserResponse
from app.domain.entities.causal_state_types import DurableExecutionStep
from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.recovery_plan import (
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStatus,
)
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationAction,
    CompensationType,
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    RecoveryAdapterType,
    RecoveryEvidence,
    Reversibility,
)
from app.domain.entities.user import User
from app.domain.repositories.causal_state_repositories import enforce_write_fence
from app.domain.services.emergency_control_service import get_emergency_control_service
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from app.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JWTTokenService
from app.presentation.api.v1.routes.surgical_recovery import (
    execute_recovery_plan,
    resume_recovery_plan,
)

TENANT = "tenant-wp8"
TENANT_B = "tenant-b-wp8"
PLAN = "plan-wp8"


# ---------------------------------------------------------------------------
# Test doubles (same contracts as WP-7's disposable environment)
# ---------------------------------------------------------------------------


def _make_action(
    action_id: str, tenant_id: str = TENANT, parent_action_id: str | None = None
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=None,
        agent_id="agent-wp8",
        authority_grant_id=None,
        tool="database",
        resource=f"record:{action_id}",
        action_type="insert",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref=f"state:before:{action_id}",
        parent_action_id=parent_action_id,
    )


def _make_evidence(action_id: str, tenant_id: str = TENANT) -> RecoveryEvidence:
    return RecoveryEvidence(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id=tenant_id,
        agent_id="agent-wp8",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=action_id,
        correlation_id="corr-wp8",
        incident_id="inc-wp8",
        target_system="mock",
        target_resource=f"record:{action_id}",
        action_type="insert",
        before_state_reference=f"state:before:{action_id}",
        after_state_reference=f"state:after:{action_id}",
        compensation_payload={"op": "restore", "target": action_id},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.MOCK,
        idempotency_key=f"idem-{action_id}",
        dependency_edges=[],
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
        evidence_hash=f"hash-{action_id}",
        adapter_capability=AdapterCapability.MOCK,
    )


class _EvidenceRepo:
    def __init__(self, evidence_list: list[RecoveryEvidence]) -> None:
        self._by_action = {(e.tenant_id, e.action_id): e for e in evidence_list}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None:
        return self._by_action.get((tenant_id, action_id))


class _ExecutionRepo:
    def __init__(self) -> None:
        self._steps: dict[str, DurableExecutionStep] = {}
        self._fences: dict[str, int] = {}

    async def save(
        self, step: DurableExecutionStep, expected_fencing_token: int | None = None
    ) -> DurableExecutionStep:
        enforce_write_fence(
            self._fences.get(step.step_id, 0), expected_fencing_token, step.step_id
        )
        if expected_fencing_token is not None:
            self._fences[step.step_id] = expected_fencing_token
        self._steps[step.step_id] = step
        return step

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        await asyncio.sleep(0)
        items = sorted(
            [
                s
                for s in self._steps.values()
                if s.tenant_id == tenant_id and s.plan_id == plan_id
            ],
            key=lambda s: s.execution_order,
        )
        return items[offset : offset + limit], len(items)


class _PlanRepo:
    def __init__(self, plans: list[RecoveryPlan]) -> None:
        self._plans = {p.plan_id: p for p in plans}

    async def get_by_plan_id(self, tenant_id: str, plan_id: str) -> RecoveryPlan | None:
        plan = self._plans.get(plan_id)
        if plan is not None and plan.tenant_id == tenant_id:
            return plan
        return None

    async def update_status(
        self, tenant_id: str, plan_id: str, status: RecoveryStatus, **fields: Any
    ) -> RecoveryPlan | None:
        plan = await self.get_by_plan_id(tenant_id, plan_id)
        if plan is None:
            return None
        outcome = fields.get("outcome", plan.outcome)
        if not isinstance(outcome, RecoveryOutcome):
            outcome = RecoveryOutcome(outcome)
        updated = replace(
            plan,
            status=status,
            outcome=outcome,
            simulation_result=fields.get("simulation_result", plan.simulation_result),
            executed_by=fields.get("executed_by", plan.executed_by),
            execution_status=fields.get("execution_status", plan.execution_status),
        )
        self._plans[plan_id] = updated
        return updated


class _ActionRepo:
    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action is not None and action.tenant_id == tenant_id:
            return action
        return None

    async def list_descendants(
        self, tenant_id: str, root_action_id: str, **kwargs: Any
    ) -> tuple[list[ProtectedAction], int]:
        result = [
            a
            for a in self._actions.values()
            if a.parent_action_id == root_action_id and a.tenant_id == tenant_id
        ]
        return result, len(result)


def _user(tenant_id: str = TENANT) -> UserResponse:
    return UserResponse(
        id=uuid.uuid4(),
        email=f"wp8-{uuid.uuid4().hex[:8]}@test.com",
        is_active=True,
        role="admin",
        tenant_id=tenant_id,
    )


def _plan(
    status: RecoveryStatus = RecoveryStatus.APPROVED, tenant_id: str = TENANT
) -> RecoveryPlan:
    return RecoveryPlan(
        plan_id=PLAN,
        tenant_id=tenant_id,
        incident_action_id="a0",
        status=status,
        topological_order=["a0", "a1"],
    )


async def _call_execute_route(
    plan_status: RecoveryStatus = RecoveryStatus.APPROVED,
    user_tenant: str = TENANT,
    plan_tenant: str = TENANT,
    plan_present: bool = True,
    adapters: list[Any] | None = None,
) -> Any:
    a0 = _make_action("a0")
    a1 = replace(_make_action("a1"), parent_action_id="a0")
    plans = [_plan(plan_status, plan_tenant)] if plan_present else []
    current = _user(user_tenant)
    return await execute_recovery_plan(
        plan_id=PLAN,
        _authorized=current,
        current_user=current,
        plan_repo=_PlanRepo(plans),
        action_repo=_ActionRepo([a0, a1]),
        evidence_repo=_EvidenceRepo([_make_evidence("a0"), _make_evidence("a1")]),
        execution_repo=_ExecutionRepo(),
        adapters=adapters if adapters is not None else [MockRecoveryAdapter(scenario="success")],
    )


async def _call_resume_route(
    plan_status: RecoveryStatus = RecoveryStatus.APPROVED,
    user_tenant: str = TENANT,
    plan_tenant: str = TENANT,
) -> Any:
    plans = [_plan(plan_status, plan_tenant)]
    current = _user(user_tenant)
    return await resume_recovery_plan(
        plan_id=PLAN,
        _authorized=current,
        current_user=current,
        plan_repo=_PlanRepo(plans),
        evidence_repo=_EvidenceRepo([_make_evidence("a0"), _make_evidence("a1")]),
        execution_repo=_ExecutionRepo(),
        adapters=[MockRecoveryAdapter(scenario="success")],
    )


# ---------------------------------------------------------------------------
# Emergency deny must be enforced at every execution entry point
# ---------------------------------------------------------------------------


async def test_emergency_deny_blocks_surgical_plan_execution():
    """PILLAR 6: activating emergency deny must block plan execution."""
    service = get_emergency_control_service()
    await service.activate_emergency_deny(TENANT, "wp8-test", "bypass probe")
    try:
        with pytest.raises(HTTPException) as exc_info:
            await _call_execute_route()
        assert exc_info.value.status_code == 403
        assert "EMERGENCY DENY" in str(exc_info.value.detail)
    finally:
        await service.deactivate_emergency_deny(TENANT, "wp8-test")

    # Deactivation restores execution (the guard must not wedge).
    response = await _call_execute_route()
    assert response.status == RecoveryStatus.COMPLETED.value


async def test_emergency_deny_blocks_surgical_plan_resume():
    service = get_emergency_control_service()
    await service.activate_emergency_deny(TENANT, "wp8-test", "bypass probe")
    try:
        with pytest.raises(HTTPException) as exc_info:
            await _call_resume_route()
        assert exc_info.value.status_code == 403
    finally:
        await service.deactivate_emergency_deny(TENANT, "wp8-test")

    # With deny clear, resume reaches the orchestrator (no_steps: no durable
    # steps were ever created for this plan).
    result = await _call_resume_route()
    assert result["status"] == "no_steps"


def test_emergency_activation_routes_and_enforcement_share_one_state():
    """The emergency routes' service instance IS the enforcement instance.

    If activation wrote to a different object than the guard reads, deny
    state would be silently ignored (the classic UI-policy-only bypass).
    """
    from app.presentation.api.v1.routes.emergency import (
        emergency_service as route_emergency_service,
    )

    assert route_emergency_service is get_emergency_control_service()


def test_emergency_deny_blocks_control_execute_over_http(client: TestClient) -> None:
    """Alternate API probe: /api/v1/recovery/execute honours emergency deny."""
    token = asyncio.run(
        _create_admin_token(f"wp8-ctl-{uuid.uuid4()}@example.com", "tenant-wp8-ctl")
    )
    _create_agent(client, token, "agent-wp8-ctl")
    action_id = _create_action(client, token, "agent-wp8-ctl")
    sim = client.post(
        "/api/v1/recovery/simulate",
        json={
            "incident_action_id": action_id,
            "recovery_steps": [{"step": "revert"}],
        },
        headers=_auth_headers(token),
    )
    assert sim.status_code == 200
    plan_id = sim.json()["plan_id"]

    service = get_emergency_control_service()
    asyncio.run(service.activate_emergency_deny("tenant-wp8-ctl", "wp8-test"))
    try:
        blocked = client.post(
            "/api/v1/recovery/execute",
            json={"plan_id": plan_id, "approved_by": "admin"},
            headers=_auth_headers(token),
        )
        assert blocked.status_code == 403
        assert "EMERGENCY DENY" in blocked.json()["detail"]
    finally:
        asyncio.run(service.deactivate_emergency_deny("tenant-wp8-ctl", "wp8-test"))

    # Same request with deny cleared must not be rejected by the guard.
    allowed = client.post(
        "/api/v1/recovery/execute",
        json={"plan_id": plan_id, "approved_by": "admin"},
        headers=_auth_headers(token),
    )
    assert allowed.status_code != 403


def test_emergency_deny_blocks_intent_execution_over_http(client: TestClient) -> None:
    """Alternate API probe: /api/v1/intent/execute honours emergency deny."""
    tenant = "tenant-wp8-intent"
    token = asyncio.run(
        _create_admin_token(f"wp8-int-{uuid.uuid4()}@example.com", tenant)
    )
    exec_token = _mint_execution_token(client, token)

    service = get_emergency_control_service()
    asyncio.run(service.activate_emergency_deny(tenant, "wp8-test"))
    try:
        blocked = client.post(
            "/api/v1/intent/execute",
            json={"execution_token": exec_token},
            headers=_auth_headers(token),
        )
        assert blocked.status_code == 403
        assert "EMERGENCY DENY" in blocked.json()["detail"]
    finally:
        asyncio.run(service.deactivate_emergency_deny(tenant, "wp8-test"))

    # A fresh token executes normally once the deny is lifted.
    fresh_token = _mint_execution_token(client, token)
    allowed = client.post(
        "/api/v1/intent/execute",
        json={"execution_token": fresh_token},
        headers=_auth_headers(token),
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "executed"


# ---------------------------------------------------------------------------
# Approval gates and tenant scoping at the execution boundary
# ---------------------------------------------------------------------------


async def test_unapproved_draft_plan_cannot_be_executed():
    with pytest.raises(HTTPException) as exc_info:
        await _call_execute_route(plan_status=RecoveryStatus.DRAFT)
    assert exc_info.value.status_code == 400
    assert "does not allow execution" in str(exc_info.value.detail)


async def test_pending_approval_plan_cannot_be_executed():
    with pytest.raises(HTTPException) as exc_info:
        await _call_execute_route(plan_status=RecoveryStatus.PENDING_APPROVAL)
    assert exc_info.value.status_code == 400


async def test_unknown_plan_execute_is_not_found():
    with pytest.raises(HTTPException) as exc_info:
        await _call_execute_route(plan_present=False)
    assert exc_info.value.status_code == 404


async def test_cross_tenant_plan_execute_is_not_found():
    """A tenant-B user cannot execute tenant A's plan (malformed/alternate
    input: the plan id is valid, the tenant binding is not)."""
    with pytest.raises(HTTPException) as exc_info:
        await _call_execute_route(user_tenant=TENANT_B, plan_tenant=TENANT)
    assert exc_info.value.status_code == 404


async def test_resume_requires_approved_plan():
    with pytest.raises(HTTPException) as exc_info:
        await _call_resume_route(plan_status=RecoveryStatus.DRAFT)
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Direct adapter calls (bypassing orchestrator and routes) fail closed
# ---------------------------------------------------------------------------


async def test_direct_adapter_call_cannot_bypass_idempotency_contract():
    """Direct-call probe: mismatched idempotency key blocks the write."""
    adapter = MockRecoveryAdapter(scenario="success")
    compensation = CompensationAction(
        action_id="a0",
        incident_action_id="a0",
        compensation_type=CompensationType.REVERSE_OPERATION,
        compensation_payload={"op": "restore"},
        idempotency_key="idem-a0",
        target_system="mock",
        target_resource="record:a0",
        execution_order=0,
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        drift_status=DriftStatus.NO_DRIFT,
        conflict_status=ConflictStatus.NO_CONFLICT,
        verification_requirements=[],
        dependency_edges=[],
    )
    result = await adapter.execute_compensation(compensation, "forged-key")
    assert result.success is False
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT


async def test_direct_filesystem_adapter_call_cannot_escape_base_path(tmp_path: Path):
    """Direct-call probe: path traversal in the payload must fail closed and
    must not touch anything outside the adapter's base path."""
    base = tmp_path / "workspace"
    base.mkdir()
    inside = base / "app.conf"
    inside.write_text("original", encoding="utf-8")
    outside = tmp_path.parent / f"escaped-{uuid.uuid4().hex}.txt"

    adapter = FilesystemRecoveryAdapter(base_path=base)
    compensation = CompensationAction(
        action_id="fs-1",
        incident_action_id="fs-1",
        compensation_type=CompensationType.STATE_TRANSITION,
        compensation_payload={
            "operation": "restore_content",
            "base_path": str(base),
            "file_path": f"../{outside.name}",
            "before_snapshot": {"content": "pwned"},
        },
        idempotency_key="idem-fs-1",
        target_system="filesystem",
        target_resource=f"file:../{outside.name}",
        execution_order=0,
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        drift_status=DriftStatus.NO_DRIFT,
        conflict_status=ConflictStatus.NO_CONFLICT,
        verification_requirements=[],
        dependency_edges=[],
    )
    result = await adapter.execute_compensation(compensation, "idem-fs-1")

    assert result.success is False
    assert result.execution_state != ExecutionState.SUCCEEDED
    assert not outside.exists()
    assert inside.read_text(encoding="utf-8") == "original"


# ---------------------------------------------------------------------------
# HTTP helpers (register/agent/action/token flow shared by API probes)
# ---------------------------------------------------------------------------


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_admin_token(email: str, tenant_id: str) -> str:
    """Create an admin-role user directly and mint its JWT.

    ``/auth/register`` hard-codes role="viewer" while execution-boundary
    endpoints require an executor role (admin/operator); this helper mints
    the token the same way ``test_replay_and_token_security`` does.
    """
    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SQLAlchemyUserRepository(session)
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=BcryptPasswordHasher(rounds=4).hash("Password123!"),
            is_active=True,
            created_at=datetime.now(tz=UTC),
            role="admin",
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


def _create_agent(client: TestClient, token: str, agent_id: str) -> None:
    resp = client.post(
        "/api/v1/agents/",
        json={
            "agent_id": agent_id,
            "name": f"Agent {agent_id}",
            "agent_type": "service_agent",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201


def _create_action(client: TestClient, token: str, agent_id: str) -> str:
    resp = client.post(
        "/api/v1/actions/",
        json={
            "agent_id": agent_id,
            "tool": "search",
            "resource": "test-resource",
            "action_type": "query",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201
    return resp.json()["action_id"]


def _mint_execution_token(client: TestClient, token: str) -> str:
    verify_response = client.post(
        "/api/v1/intent/verify",
        json={
            "user_prompt": "Search for user records",
            "agent_id": "agent-123",
            "reasoning_step": "Execute search",
            "proposed_tool": "search",
            "tool_arguments": {"query": "SELECT * FROM users LIMIT 10"},
        },
        headers=_auth_headers(token),
    )
    assert verify_response.status_code == 200
    execution_token = verify_response.json()["ephemeral_token"]
    assert execution_token
    return execution_token
