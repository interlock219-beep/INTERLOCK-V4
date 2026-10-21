"""Credit enforcement around the REAL recovery engine and the HTTP routes.

Covers the mission's engine-integration matrix:
* billable point = completed AND executed_and_verified (real orchestrator runs),
* failed runs release their hold (nothing charged),
* a billed plan never charges again (retries/resumes are free),
* insufficient credits block before the engine runs (HTTP 402 + service raise),
* concurrent requests never overspend the wallet,
* evaluation tenants (no wallet) execute unbilled.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.entities.causal_state_types import DurableExecutionStep, VerificationStatus
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.recovery_plan import RecoveryPlan, RecoveryStatus
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    RecoveryAdapterType,
    RecoveryEvidence,
    VerificationResult,
)
from app.domain.exceptions.billing_errors import InsufficientCreditsError
from app.domain.repositories.causal_state_repositories import enforce_write_fence
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.recovery_credit_service import (
    CreditHold,
    RecoveryCreditService,
)
from app.infrastructure.persistence.models import UserModel
from app.infrastructure.persistence.repositories.sqlalchemy_containment_repository import (
    SQLAlchemyRecoveryPlanRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_credit_repositories import (
    SQLAlchemyCreditRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
    SQLAlchemyProtectedActionRepository,
)
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from app.presentation.api.v1.routes._recovery_billing import (
    is_billable_result,
    reserve_recovery_credit,
    settle_recovery_credit,
)

# ---------------------------------------------------------------------------
# Helpers (mirrors of the engine-test fixtures, kept local for independence)
# ---------------------------------------------------------------------------


def _available(wallet) -> int:
    """Domain invariant: available = allocated - consumed - reserved."""
    return wallet.allocated - wallet.consumed - wallet.reserved


def _make_action(action_id: str, tenant_id: str) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=uuid4(),
        agent_id="agent-1",
        authority_grant_id=None,
        tool="database",
        resource="record:1",
        action_type="insert",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        parent_action_id=None,
        before_state_ref="state:before:123",
        after_state_ref="state:after:456",
        status=ActionStatus.EXECUTED,
    )


def _make_evidence(action_id: str, tenant_id: str) -> RecoveryEvidence:
    return RecoveryEvidence(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id=tenant_id,
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=action_id,
        correlation_id="corr-1",
        incident_id="inc-1",
        target_system="mock",
        target_resource="record:1",
        action_type="insert",
        before_state_reference="state:before:123",
        after_state_reference="state:after:456",
        compensation_payload={"op": "restore"},
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
        self._evidence = {e.action_id: e for e in evidence_list}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None:
        ev = self._evidence.get(action_id)
        if ev and ev.tenant_id == tenant_id:
            return ev
        return None

    async def get_by_evidence_id(
        self, tenant_id: str, evidence_id: str
    ) -> RecoveryEvidence | None:
        for ev in self._evidence.values():
            if ev.evidence_id == evidence_id and ev.tenant_id == tenant_id:
                return ev
        return None

    async def list_by_incident(
        self, tenant_id: str, incident_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[RecoveryEvidence], int]:
        items = [
            e
            for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.incident_id == incident_id
        ]
        return items[offset : offset + limit], len(items)

    async def list_by_root_action(
        self, tenant_id: str, root_action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[RecoveryEvidence], int]:
        items = [
            e
            for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.root_action_id == root_action_id
        ]
        return items[offset : offset + limit], len(items)

    async def save(self, evidence: RecoveryEvidence) -> RecoveryEvidence:
        self._evidence[evidence.action_id] = evidence
        return evidence


class _ExecutionRepo:
    def __init__(self) -> None:
        self._steps: dict[str, DurableExecutionStep] = {}
        self._fences: dict[str, int] = {}

    async def get_by_step_id(
        self, tenant_id: str, step_id: str
    ) -> DurableExecutionStep | None:
        step = self._steps.get(step_id)
        if step and step.tenant_id == tenant_id:
            return step
        return None

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        items = sorted(
            [
                s
                for s in self._steps.values()
                if s.tenant_id == tenant_id and s.plan_id == plan_id
            ],
            key=lambda s: s.execution_order,
        )
        return items[offset : offset + limit], len(items)

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


class _VerifyingMockAdapter(MockRecoveryAdapter):
    """Mock adapter that passes independent verification.

    ``MockRecoveryAdapter.verify`` deliberately always fails (it performs no
    real verification), which correctly makes its runs NON-billable. The
    production adapters (e.g. ``FilesystemRecoveryAdapter``) verify the
    restored state; this subclass reproduces that behavior so the billable
    path (completed + executed_and_verified) can be exercised against the
    real orchestrator.
    """

    async def verify(self, compensation) -> VerificationResult:
        return VerificationResult(
            action_id=compensation.action_id,
            verified=True,
            details={"reason": "independent verification passed"},
        )


async def _allocate(
    service: RecoveryCreditService, tenant: str, amount: int, key: str
) -> None:
    now = datetime.now(tz=UTC)
    await service.allocate(
        tenant,
        amount=amount,
        period_start=now,
        period_end=now + timedelta(days=30),
        idempotency_key=key,
        reason="paid period allowance",
        plan_tier="pro",
        plan_name="Pro",
    )


async def _run_engine_flow(
    service: RecoveryCreditService,
    tenant: str,
    plan_id: str,
    *,
    scenario: str = "success",
    verifying: bool = True,
) -> dict:
    """The exact route contract: reserve -> engine -> settle from the outcome."""
    hold = await service.reserve_for_execution(tenant, plan_id)
    actions = [_make_action("a1", tenant), _make_action("a2", tenant)]
    evidence = [_make_evidence("a1", tenant), _make_evidence("a2", tenant)]
    adapter: MockRecoveryAdapter = (
        _VerifyingMockAdapter(scenario=scenario)
        if verifying
        else MockRecoveryAdapter(scenario=scenario)
    )
    orchestrator = DistributedRecoveryOrchestrator(
        _EvidenceRepo(evidence),
        _ExecutionRepo(),
        [adapter],
    )
    result: dict = {}
    try:
        await orchestrator.create_durable_plan(
            tenant, plan_id, actions, ["a1", "a2"]
        )
        result = await orchestrator.execute_durable_plan(tenant, plan_id)
    finally:
        await settle_recovery_credit(service, hold, result)
    return result


class TestBillablePoint:
    def test_completed_and_verified_is_billable(self) -> None:
        result = {
            "status": "completed",
            "verification_status": VerificationStatus.EXECUTED_AND_VERIFIED.value,
        }
        assert is_billable_result(result) is True

    @pytest.mark.parametrize(
        "result",
        [
            None,
            {},
            {"status": "completed", "verification_status": "verification_failed"},
            {"status": "completed", "verification_status": "pending"},
            {"status": "completed"},  # never bill without a verification status
            {"status": "partial", "verification_status": "executed_and_verified"},
            {"status": "failed", "verification_status": "executed_and_verified"},
            {"status": "stopped", "verification_status": "executed_and_verified"},
            {"status": "lease_lost", "verification_status": "executed_and_verified"},
        ],
    )
    def test_everything_else_is_not_billable(self, result: dict | None) -> None:
        assert is_billable_result(result) is False


class TestEngineIntegration:
    @pytest.mark.asyncio
    async def test_successful_recovery_consumes_exactly_one_credit(
        self, db_session: Session
    ) -> None:
        tenant = f"tenant-eng-ok-{uuid4().hex[:6]}"
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        await _allocate(service, tenant, 250, f"alloc:{tenant}:1")

        result = await _run_engine_flow(service, tenant, "plan-eng-1")

        assert result["status"] == "completed"
        assert (
            result["verification_status"]
            == VerificationStatus.EXECUTED_AND_VERIFIED.value
        )
        assert is_billable_result(result) is True
        wallet = await service.get_wallet(tenant)
        assert wallet is not None
        assert wallet.consumed == 1
        assert wallet.available == 249
        entries = await service.list_ledger(tenant)
        kinds = [e.kind.value for e in entries]
        assert kinds[0] == "consumption"
        assert entries[0].recovery_plan_id == "plan-eng-1"

    @pytest.mark.asyncio
    async def test_failed_recovery_is_not_charged(self, db_session: Session) -> None:
        tenant = f"tenant-eng-fail-{uuid4().hex[:6]}"
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        await _allocate(service, tenant, 250, f"alloc:{tenant}:1")

        result = await _run_engine_flow(
            service, tenant, "plan-eng-fail", scenario="execute_fail"
        )

        assert result["status"] != "completed" or not is_billable_result(result)
        assert result["status"] in ("partial", "failed", "stopped")
        wallet = await service.get_wallet(tenant)
        assert wallet is not None
        assert wallet.consumed == 0
        assert wallet.reserved == 0
        assert wallet.available == 250  # hold released back to the wallet

    @pytest.mark.asyncio
    async def test_completed_but_unverified_run_is_not_billed(
        self, db_session: Session
    ) -> None:
        """A completed run whose verification did NOT pass costs nothing.

        The stock Mock adapter completes the steps but never verifies, so the
        orchestrator reports executed_not_verified -- the billing policy must
        release the hold instead of charging for an unverified recovery.
        """
        tenant = f"tenant-eng-unv-{uuid4().hex[:6]}"
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        await _allocate(service, tenant, 250, f"alloc:{tenant}:1")

        result = await _run_engine_flow(
            service, tenant, "plan-eng-unverified", verifying=False
        )

        assert result["status"] == "completed"  # engine finished...
        assert (
            result["verification_status"]
            == VerificationStatus.EXECUTED_NOT_VERIFIED.value
        )  # ...but never verified
        assert is_billable_result(result) is False  # ...so never billed
        wallet = await service.get_wallet(tenant)
        assert wallet is not None
        assert wallet.consumed == 0
        assert _available(wallet) == 250

    @pytest.mark.asyncio
    async def test_reexecution_of_a_billed_plan_costs_nothing(
        self, db_session: Session
    ) -> None:
        tenant = f"tenant-eng-retry-{uuid4().hex[:6]}"
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        await _allocate(service, tenant, 250, f"alloc:{tenant}:1")

        await _run_engine_flow(service, tenant, "plan-eng-retry")
        # Resume / retry of the same plan after the first successful charge.
        hold = await service.reserve_for_execution(tenant, "plan-eng-retry")
        assert hold is not None and hold.already_billed is True
        outcome = await service.finalize_hold(hold, billable=True)
        assert outcome == "already_billed"

        wallet = await service.get_wallet(tenant)
        assert wallet is not None and wallet.consumed == 1
        assert wallet.available == 249

    @pytest.mark.asyncio
    async def test_insufficient_credits_blocks_before_engine_runs(
        self, db_session: Session
    ) -> None:
        tenant = f"tenant-eng-402-{uuid4().hex[:6]}"
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        await _allocate(service, tenant, 1, f"alloc:{tenant}:1")
        first = await _run_engine_flow(service, tenant, "plan-eng-a")
        assert first["status"] == "completed"  # the one credit was spent

        with pytest.raises(InsufficientCreditsError) as excinfo:
            await service.reserve_for_execution(tenant, "plan-eng-b")
        assert excinfo.value.available == 0
        # The engine was never invoked for plan-eng-b: no hold exists.
        wallet = await service.get_wallet(tenant)
        assert wallet is not None and wallet.reserved == 0

    @pytest.mark.asyncio
    async def test_concurrent_executions_never_overspend(
        self, db_session: Session
    ) -> None:
        tenant = f"tenant-eng-cc-{uuid4().hex[:6]}"
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        await _allocate(service, tenant, 3, f"alloc:{tenant}:1")

        attempts = 6
        results = await asyncio.gather(
            *(
                _guarded_flow(service, tenant, f"plan-cc-{i}")
                for i in range(attempts)
            )
        )
        successes = [r for r in results if r is not None]
        rejections = [r for r in results if r is None]
        assert len(successes) <= 3  # never more admitted than the balance
        assert len(successes) + len(rejections) == attempts
        assert len(rejections) >= attempts - 3

        wallet = await service.get_wallet(tenant)
        assert wallet is not None
        assert wallet.consumed <= 3
        assert wallet.reserved == 0
        assert wallet.allocated - wallet.consumed - wallet.reserved >= 0

    @pytest.mark.asyncio
    async def test_evaluation_tenant_executes_unbilled(
        self, db_session: Session
    ) -> None:
        tenant = f"tenant-eng-free-{uuid4().hex[:6]}"
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        result = await _run_engine_flow(service, tenant, "plan-eng-free")
        assert result["status"] == "completed"  # engine ran without a wallet
        assert await service.get_wallet(tenant) is None
        assert await service.list_ledger(tenant) == []


async def _guarded_flow(
    service: RecoveryCreditService, tenant: str, plan_id: str
) -> dict | None:
    """Run one flow; return None when the credit gate rejected it."""
    try:
        return await _run_engine_flow(service, tenant, plan_id)
    except InsufficientCreditsError:
        return None


class TestReserveHelper:
    @pytest.mark.asyncio
    async def test_reserve_maps_insufficient_to_http_402(
        self, db_session: Session
    ) -> None:
        tenant = f"tenant-hlp-{uuid4().hex[:6]}"
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        await _allocate(service, tenant, 1, f"alloc:{tenant}:1")
        hold = await service.reserve_for_execution(tenant, "plan-1")
        assert hold is not None
        await service.finalize_hold(hold, billable=True)

        with pytest.raises(HTTPException) as excinfo:
            await reserve_recovery_credit(service, tenant, "plan-2")
        assert excinfo.value.status_code == 402
        detail = excinfo.value.detail
        assert detail["available"] == 0
        assert detail["required"] == 1
        assert "renewal_at" in detail
        assert "Upgrade" in detail["upgrade_hint"]

    @pytest.mark.asyncio
    async def test_reserve_returns_none_for_evaluation_tenant(
        self, db_session: Session
    ) -> None:
        service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
        hold: CreditHold | None = await reserve_recovery_credit(
            service, "tenant-no-wallet", "plan-1"
        )
        assert hold is None


# ---------------------------------------------------------------------------
# HTTP-level enforcement on the real routes
# ---------------------------------------------------------------------------


def _register_admin(
    client: TestClient, db_session: Session, tenant: str
) -> dict[str, str]:
    email = f"billing-exec-{uuid4().hex[:8]}@test.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass1!", "tenant_id": tenant},
    )
    assert response.status_code == 201
    auth = response.json()
    # Recovery execution requires an executor role; promote for the test.
    db_session.query(UserModel).filter(UserModel.email == email).update(
        {"role": "admin"}
    )
    db_session.commit()
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def _seed_approved_plan(
    db_session: Session, tenant: str, plan_id: str, action_id: str
) -> None:
    action_repo = SQLAlchemyProtectedActionRepository(db_session)
    plan_repo = SQLAlchemyRecoveryPlanRepository(db_session)
    await action_repo.save(_make_action(action_id, tenant))
    await plan_repo.save(
        RecoveryPlan(
            plan_id=plan_id,
            tenant_id=tenant,
            incident_action_id=action_id,
            status=RecoveryStatus.APPROVED,
            topological_order=[action_id],
            approved_by="test-admin",
        )
    )
    db_session.commit()


async def _exhaust_credits(db_session: Session, tenant: str) -> None:
    service = RecoveryCreditService(SQLAlchemyCreditRepository(db_session))
    await _allocate(service, tenant, 1, f"alloc:{tenant}:1")
    hold = await service.reserve_for_execution(tenant, "already-billed-plan")
    assert hold is not None
    await service.finalize_hold(hold, billable=True)


class TestHTTPLimits:
    def test_execute_returns_402_when_allowance_exhausted(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-http-402-{uuid4().hex[:6]}"
        headers = _register_admin(client, db_session, tenant)
        asyncio.run(_exhaust_credits(db_session, tenant))
        plan_id = f"plan-http-402-{uuid4().hex[:6]}"
        asyncio.run(
            _seed_approved_plan(db_session, tenant, plan_id, f"act-http-{uuid4().hex[:6]}")
        )

        response = client.post(
            f"/api/v1/recovery/plan/{plan_id}/execute", headers=headers
        )

        assert response.status_code == 402
        detail = response.json()["detail"]
        assert detail["available"] == 0
        assert detail["required"] == 1
        assert detail["renewal_at"] is not None

    def test_execute_blocked_also_on_resume_route(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        tenant = f"tenant-http-402r-{uuid4().hex[:6]}"
        headers = _register_admin(client, db_session, tenant)
        asyncio.run(_exhaust_credits(db_session, tenant))
        plan_id = f"plan-http-402r-{uuid4().hex[:6]}"
        asyncio.run(
            _seed_approved_plan(db_session, tenant, plan_id, f"act-http-{uuid4().hex[:6]}")
        )

        response = client.post(
            f"/api/v1/recovery/plan/{plan_id}/resume", headers=headers
        )
        assert response.status_code == 402

    def test_evaluation_tenant_is_not_blocked_by_billing(
        self, client: TestClient, seed_plans: None, db_session: Session
    ) -> None:
        """No wallet = unbilled evaluation tier: the credit gate never fires."""
        tenant = f"tenant-http-free-{uuid4().hex[:6]}"
        headers = _register_admin(client, db_session, tenant)
        plan_id = f"plan-http-free-{uuid4().hex[:6]}"
        asyncio.run(
            _seed_approved_plan(db_session, tenant, plan_id, f"act-http-{uuid4().hex[:6]}")
        )

        response = client.post(
            f"/api/v1/recovery/plan/{plan_id}/execute", headers=headers
        )

        # The response reflects the engine outcome (no adapters configured in
        # tests, so the run fails operationally) -- but billing must not be the
        # reason: the tenant has no wallet and sees no 402.
        assert response.status_code != 402
        assert "allowance" not in response.text.lower()
