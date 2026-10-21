"""V6 doc-WP-6: Phase Five scenario proofs A-J (mission, verbatim).

Mission Phase Five: "Build end-to-end scenarios in disposable environments.
At minimum demonstrate:" scenarios A-J (quoted verbatim in each test's
docstring) and "Record reproducible results for every scenario. If an
environment is unavailable, label the scenario blocked instead of simulating
a pass."

Every scenario asserts the six PILLAR 7 properties (mission, verbatim)::

    For every scenario, assert:
    1. The resulting resource state.
    2. Whether recovery is complete, partial, failed, or uncertain.
    3. Whether unrelated user data remains intact.
    4. Whether retry is safe.
    5. Whether evidence accurately reflects what occurred.
    6. Whether the system refuses unsupported guarantees.

Evidence classes (honest labelling). No scenario is BLOCKED: all ten run in
local-only disposable environments (tmp_path sandboxes, the in-memory lease
store with a controllable clock, the SQLite ``db_session``, the TestClient
app) - no external infrastructure is required by any of them:

- A/C/G/H: production ``FilesystemRecoveryAdapter`` against real files
  (byte-level production code paths; no mock at the filesystem layer).
- B: mixed adapters - production filesystem adapter for the filesystem steps
  plus ``MockRecoveryAdapter(scenario="execute_fail")`` as the deliberately
  failing non-filesystem step (the mock stands in for an unavailable external
  system; documented as such, never presented as a live integration proof).
- D/E: real orchestrator + real SQLAlchemy durable-execution repository
  (SQLite); deterministic one-shot fault injection and a controllable lease
  clock - no sleeps, no timing races.
- F: real HTTP route, real auth tokens, real audit-log file. Scope deviation
  (documented in the section 8 run log): the cross-tenant denial path was not
  audited before this work package - the regression test first fails RED and
  a minimal route-level audit event closes the gap.
- I: production v2 evidence-hash verification (``seal_evidence``).
- J: production backup/restore utility in a tmp_path disposable environment.

RED/GREEN results are recorded honestly in
``INTERLOCK_V6_PHASE0_BASELINE.md`` section 8 - never simulated.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.entities.causal_state_types import RecoveryReport, VerificationStatus
from app.domain.entities.independent_verification_types import (
    IndependentVerifierRole,
    VerificationLayer,
    VerificationOutcome,
)
from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.entities.recovery_plan import RecoveryOutcome, RecoveryPlan, RecoveryStatus
from app.domain.entities.surgical_recovery_types import (
    CompensationResult,
    ConflictStatus,
    ExecutionState,
    RecoveryEvidence,
    VerificationResult,
)
from app.domain.repositories.causal_state_repositories import StaleFencingTokenError
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
    InMemoryPlanLeaseStore,
)
from app.domain.services.evidence_hash import compute_evidence_hash_v2, seal_evidence
from app.domain.services.independent_verification_service import IndependentVerificationService
from app.domain.services.recovery_planning_service import RecoveryPlanningService
from app.infrastructure.backup_restore import (
    BackupVerificationError,
    export_backup,
    restore_backup,
)
from app.infrastructure.logging.audit_logger import LOG_PATH
from app.infrastructure.persistence.models.recovery_plan_model import RecoveryPlanModel
from app.infrastructure.persistence.repositories.sqlalchemy_causal_state_repositories import (
    SQLAlchemyDurableExecutionRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_recovery_evidence_repository import (
    SQLAlchemyRecoveryEvidenceRepository,
)
from app.infrastructure.recovery.filesystem_recovery_adapter import FilesystemRecoveryAdapter
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from tests.unit.recovery_lab.factories import make_action, make_evidence
from tests.unit.test_backup_restore_drill import (
    EVIDENCE_ROWS as DRILL_EVIDENCE_ROWS,
)
from tests.unit.test_backup_restore_drill import (
    PLAN_ID as DRILL_PLAN_ID,
)
from tests.unit.test_backup_restore_drill import (
    TENANT as DRILL_TENANT,
)
from tests.unit.test_backup_restore_drill import _chain_from_db, _seed, _sha256

# ---------------------------------------------------------------------------
# Constants
#
# Content constants deliberately contain NO newline characters: text-mode
# writes translate ``\n`` to the OS line separator, which would make raw
# snapshot content differ from the literal on Windows and turn honest
# byte-level assertions platform-dependent.
# ---------------------------------------------------------------------------

TENANT = "tenant-wp6"
TENANT_A = "tenant-a-wp6"
TENANT_B = "tenant-b-wp6"

BASELINE_1 = "baseline alpha config v1"
BASELINE_2 = "baseline beta config v1"
AGENT_1 = "agent modified alpha v2"
AGENT_2 = "agent modified beta v2"
HUMAN_1 = "human edit after agent v2.1"
UNRELATED = "unrelated user data must not change"


# ---------------------------------------------------------------------------
# Test doubles and helpers
# ---------------------------------------------------------------------------


class _EvidenceStore:
    """In-memory RecoveryEvidence repository with optional one-shot crash.

    The crash injection models a process death at a state-transition
    boundary: the FIRST evidence lookup for ``crash_on_action`` raises, then
    the injection disarms itself so a restart/takeover can proceed.
    """

    def __init__(self) -> None:
        self._by_action: dict[tuple[str, str], RecoveryEvidence] = {}
        self._by_id: dict[str, RecoveryEvidence] = {}
        self.crash_on_action: str | None = None
        self._crash_fired = False

    async def save(self, evidence: RecoveryEvidence) -> RecoveryEvidence:
        self._by_action[(evidence.tenant_id, evidence.action_id)] = evidence
        self._by_id[evidence.evidence_id] = evidence
        return evidence

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None:
        if self.crash_on_action == action_id and not self._crash_fired:
            self._crash_fired = True
            raise RuntimeError("simulated worker crash at state transition")
        return self._by_action.get((tenant_id, action_id))

    async def get_by_evidence_id(
        self, tenant_id: str, evidence_id: str
    ) -> RecoveryEvidence | None:
        evidence = self._by_id.get(evidence_id)
        if evidence is not None and evidence.tenant_id == tenant_id:
            return evidence
        return None


class MockActionRepo:
    """ProtectedActionRepository test double (copied from
    ``test_surgical_recovery_pipeline`` with the missing ``_by_action``
    initialization fixed so missing-id lookups cannot raise AttributeError)."""

    def __init__(self, actions: list[ProtectedAction]) -> None:
        self._actions = {a.action_id: a for a in actions}
        self._by_action: dict[str, ProtectedAction] = {}

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> ProtectedAction | None:
        action = self._actions.get(action_id)
        if action and action.tenant_id == tenant_id:
            return action
        return self._by_action.get(action_id)

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


class MockPlanRepo:
    """RecoveryPlanRepository test double (copied from
    ``test_surgical_recovery_pipeline``)."""

    def __init__(self, plans: list[RecoveryPlan] | None = None) -> None:
        self._plans: dict[str, RecoveryPlan] = {
            p.plan_id: p for p in (plans or [])
        }

    async def get_by_plan_id(
        self, tenant_id: str, plan_id: str
    ) -> RecoveryPlan | None:
        plan = self._plans.get(plan_id)
        if plan and plan.tenant_id == tenant_id:
            return plan
        return None

    async def list_by_incident(
        self,
        tenant_id: str,
        incident_action_id: str,
        **kwargs: object,
    ) -> tuple[list[RecoveryPlan], int]:
        filtered = [
            p
            for p in self._plans.values()
            if p.tenant_id == tenant_id
            and p.incident_action_id == incident_action_id
        ]
        return filtered, len(filtered)

    async def save(self, plan: RecoveryPlan) -> RecoveryPlan:
        self._plans[plan.plan_id] = plan
        return plan

    async def update_status(
        self,
        tenant_id: str,
        plan_id: str,
        status: RecoveryStatus,
        **fields: object,
    ) -> RecoveryPlan | None:
        plan = await self.get_by_plan_id(tenant_id, plan_id)
        if plan is None:
            return None
        updated = RecoveryPlan(
            plan_id=plan.plan_id,
            tenant_id=plan.tenant_id,
            incident_action_id=plan.incident_action_id,
            status=status,
            outcome=fields.get("outcome", plan.outcome),
            simulation_result=fields.get("simulation_result", plan.simulation_result),
            steps=plan.steps,
            approved_by=fields.get("approved_by", plan.approved_by),
            executed_by=fields.get("executed_by", plan.executed_by),
            created_at=plan.created_at,
            updated_at=datetime.now(UTC),
            executed_at=fields.get("executed_at", plan.executed_at),
            plan_version=plan.plan_version,
            plan_hash=plan.plan_hash,
            topological_order=plan.topological_order,
            dependency_graph_reference=plan.dependency_graph_reference,
            execution_status=plan.execution_status,
            approval_policy=plan.approval_policy,
            approval_threshold=plan.approval_threshold,
            stop_conditions=plan.stop_conditions,
            compensation_summary=plan.compensation_summary,
            incident_id=plan.incident_id,
            root_action_id=plan.root_action_id,
            affected_action_ids=plan.affected_action_ids,
        )
        self._plans[plan_id] = updated
        return updated


class _CountingMockAdapter(MockRecoveryAdapter):
    """``MockRecoveryAdapter(scenario="success")`` with an execution ledger.

    Scenario D/E need to prove "no duplicate destructive actions": the ledger
    records every ``execute_compensation`` call per action id so a replay or
    a stale worker would be caught as a count > 1.
    """

    def __init__(self, scenario: str | None = "success") -> None:
        super().__init__(scenario)
        self.execute_counts: dict[str, int] = {}

    async def execute_compensation(
        self, compensation: Any, idempotency_key: str
    ) -> CompensationResult:
        action_id = compensation.action_id
        self.execute_counts[action_id] = self.execute_counts.get(action_id, 0) + 1
        return await super().execute_compensation(compensation, idempotency_key)


class _LyingFilesystemAdapter(FilesystemRecoveryAdapter):
    """Adapter that claims success + verification without touching the file.

    Scenario G: "An adapter returns success while leaving incorrect state;
    independent verification detects the mismatch."
    """

    async def execute_compensation(
        self, compensation: Any, idempotency_key: str
    ) -> CompensationResult:
        # Deliberately performs NO write - the file keeps the agent's state.
        return CompensationResult(
            action_id=compensation.action_id,
            success=True,
            execution_state=ExecutionState.SUCCEEDED,
            idempotency_key=idempotency_key,
            details={
                "operation": compensation.compensation_payload.get("operation", "unknown")
            },
            external_outcome="lying_adapter_claimed_success",
        )

    async def verify(self, compensation: Any) -> VerificationResult:
        # Deliberately claims byte-exact verification without reading the file.
        return VerificationResult(
            action_id=compensation.action_id,
            verified=True,
            details={"reason": "lying adapter claims verification"},
        )


class _TestClock:
    """Controllable clock for deterministic lease expiry (no sleeps)."""

    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def _observe(path: Path, expected: str) -> str:
    """Independent observation derived from actual bytes, not adapter claims."""
    if path.exists() and path.read_text(encoding="utf-8") == expected:
        return VerificationStatus.EXECUTED_AND_VERIFIED.value
    return VerificationStatus.EXECUTION_FAILED.value


def _register(client: TestClient, email: str, tenant_id: str) -> str:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass1!", "tenant_id": tenant_id},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePass1!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _audit_events_of(event_type: str, evidence_id: str) -> list[dict[str, Any]]:
    """All audit records of ``event_type`` referencing ``evidence_id``."""
    if not LOG_PATH.exists():
        return []
    found: list[dict[str, Any]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            record.get("event_type") == event_type
            and record.get("evidence_id") == evidence_id
        ):
            found.append(record)
    return found


async def _save_evidence_rows(
    session: Any, evidences: list[RecoveryEvidence]
) -> None:
    repo = SQLAlchemyRecoveryEvidenceRepository(session)
    for evidence in evidences:
        await repo.save(evidence)
    session.commit()


# ---------------------------------------------------------------------------
# Scenario A
# ---------------------------------------------------------------------------


async def test_scenario_a_agent_file_change_restored_and_independently_verified(
    tmp_path: Path,
) -> None:
    """Scenario A (mission, verbatim): "An AI agent modifies a project file;
    Interlock captures the baseline, records the change, restores the prior
    state, and independently verifies it."

    Evidence class: LIVE local proof - production FilesystemRecoveryAdapter on
    real files in a disposable tmp_path sandbox; real evidence capture, real
    restore, real independent verification. No external infrastructure needed
    (not BLOCKED).
    """
    base = tmp_path / "sandbox"
    base.mkdir()
    target = base / "app_config.txt"
    target.write_text(BASELINE_1, encoding="utf-8")
    bystander = base / "notes.txt"
    bystander.write_text(UNRELATED, encoding="utf-8")

    baseline_snap = FilesystemRecoveryAdapter._capture_file_snapshot(target)
    assert baseline_snap is not None, "baseline must be captured while file exists"

    action = make_action(
        action_id="act-wp6-a",
        tenant_id=TENANT,
        tool="filesystem",
        resource="file:app_config.txt",
        action_type="modify",
    )
    action = replace(action, before_state_snapshot=baseline_snap)

    ev_store = _EvidenceStore()
    fs = FilesystemRecoveryAdapter(base_path=base)
    action_repo = MockActionRepo([action])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(
        action_repo, plan_repo, adapters=[fs], evidence_repo=ev_store
    )

    # The AI agent modifies the file AFTER the decision-time baseline snapshot.
    target.write_text(AGENT_1, encoding="utf-8")

    plan = await service.create_plan(TENANT, action.action_id)
    sim = await service.simulate_plan(TENANT, plan.plan_id)

    # P1: the resulting resource state (as recorded): evidence captures the
    #     baseline exactly and the agent's change exactly.
    evidence = await ev_store.get_by_action_id(TENANT, action.action_id)
    assert evidence is not None, "P1: no evidence captured for the agent change"
    payload = evidence.compensation_payload
    assert payload["before_snapshot"]["content"] == BASELINE_1
    assert payload["after_snapshot"]["content"] == AGENT_1
    sim_step = sim["surgical_simulation_results"][action.action_id]
    assert sim_step["reversibility"] == Reversibility.AUTOMATICALLY_REVERSIBLE.value
    assert sim_step["would_succeed"] is True

    executed = await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-a")

    # P2: recovery is complete - the run finished AND every result succeeded
    #     with verification passed at plan level.
    assert executed.status == RecoveryStatus.COMPLETED
    assert executed.outcome == RecoveryOutcome.SAFE_AUTOMATIC
    step_res = executed.simulation_result["execution_results"][action.action_id]
    assert step_res["execution_state"] == ExecutionState.SUCCEEDED.value
    assert step_res["success"] is True
    assert step_res["verification_passed"] is True
    assert step_res["adapter"] == "filesystem_recovery"

    # P1 (post-execution): the file is byte-identical to the baseline again.
    assert target.read_text(encoding="utf-8") == BASELINE_1

    # P3: unrelated user data remains intact.
    assert bystander.read_text(encoding="utf-8") == UNRELATED

    # P4: retry is safe - the completed plan refuses re-execution outright and
    #     the refusal does not disturb the restored state.
    with pytest.raises(ValueError, match="does not allow execution"):
        await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-a")
    assert target.read_text(encoding="utf-8") == BASELINE_1

    # P5: evidence accurately reflects what occurred - the sealed record of
    #     baseline + agent change is unchanged by execution and retry.
    assert payload["before_snapshot"]["content"] == BASELINE_1
    assert payload["after_snapshot"]["content"] == AGENT_1

    # Independent verification from actual bytes (never from adapter claims).
    verifier = IndependentVerificationService().create_verifier(
        "v-wp6-a", IndependentVerifierRole.AUTOMATED_VERIFIER, TENANT
    )
    report = RecoveryReport(
        report_id="rep-wp6-a",
        tenant_id=TENANT,
        plan_id=plan.plan_id,
        incident_id=plan.incident_id,
        resource_results={
            action.action_id: {
                "status": VerificationStatus.EXECUTED_AND_VERIFIED.value,
                "verification": True,
            }
        },
        summary="plan-level restore claim",
    )
    observed = _observe(target, BASELINE_1)
    assert observed == VerificationStatus.EXECUTED_AND_VERIFIED.value
    ind = await IndependentVerificationService().independent_verify(
        TENANT,
        plan.plan_id,
        plan.incident_id,
        verifier,
        report,
        observed_states={action.action_id: observed},
    )
    # P2 (verification): the recovery is verified complete from real bytes.
    assert ind.outcome == VerificationOutcome.VERIFIED
    assert ind.execution_verified is True

    # P6: the system refuses unsupported guarantees - the same claim observed
    #     against a NON-restored state must never verify (no rubber-stamping).
    contradicted = await IndependentVerificationService().independent_verify(
        TENANT,
        plan.plan_id,
        plan.incident_id,
        verifier,
        report,
        observed_states={
            action.action_id: VerificationStatus.EXECUTION_FAILED.value
        },
    )
    assert contradicted.outcome == VerificationOutcome.VERIFICATION_FAILED
    assert contradicted.execution_verified is False


# ---------------------------------------------------------------------------
# Scenario B
# ---------------------------------------------------------------------------


async def test_scenario_b_mixed_adapters_partial_failure_reported_accurately(
    tmp_path: Path,
) -> None:
    """Scenario B (mission, verbatim): "An agent modifies multiple files and
    one recovery step fails; Interlock reports partial recovery accurately and
    preserves unrelated changes."

    Evidence class: mixed - production FilesystemRecoveryAdapter on real files
    for the filesystem steps; ``MockRecoveryAdapter(scenario="execute_fail")``
    stands in for the unavailable external database system (the failing step).
    The mock is never presented as live integration proof (not BLOCKED: all
    resources are local).
    """
    base = tmp_path / "sandbox-mixed"
    base.mkdir()
    file1 = base / "alpha.txt"
    file2 = base / "beta.txt"
    bystander = base / "notes.txt"
    file1.write_text(BASELINE_1, encoding="utf-8")
    file2.write_text(BASELINE_2, encoding="utf-8")
    bystander.write_text(UNRELATED, encoding="utf-8")

    snap1 = FilesystemRecoveryAdapter._capture_file_snapshot(file1)
    snap2 = FilesystemRecoveryAdapter._capture_file_snapshot(file2)
    assert snap1 is not None and snap2 is not None

    # The agent modifies both files after the decision-time snapshots.
    file1.write_text(AGENT_1, encoding="utf-8")
    file2.write_text(AGENT_2, encoding="utf-8")

    db_action = make_action(
        action_id="act-wp6-b-db",
        tenant_id=TENANT,
        tool="database",
        resource="record:wp6-b-db",
        action_type="insert",
    )
    act1 = make_action(
        action_id="act-wp6-b-f1",
        tenant_id=TENANT,
        resource="file:alpha.txt",
        action_type="modify",
        parent_action_id=db_action.action_id,
    )
    act2 = make_action(
        action_id="act-wp6-b-f2",
        tenant_id=TENANT,
        resource="file:beta.txt",
        action_type="modify",
        parent_action_id=act1.action_id,
    )
    act1 = replace(act1, before_state_snapshot=snap1)
    act2 = replace(act2, before_state_snapshot=snap2)
    actions = [db_action, act1, act2]

    ev_store = _EvidenceStore()
    fs = FilesystemRecoveryAdapter(base_path=base)
    # Pre-seed real filesystem evidence for the two file actions so
    # simulate/execute reuse the genuine baseline/agent snapshots.
    await ev_store.save(
        await fs.capture_recovery_evidence(act1, before_snapshot=snap1)
    )
    await ev_store.save(
        await fs.capture_recovery_evidence(act2, before_snapshot=snap2)
    )

    mock_fail = MockRecoveryAdapter(scenario="execute_fail")
    action_repo = MockActionRepo(actions)
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(
        action_repo,
        plan_repo,
        adapters=[mock_fail, fs],  # mock FIRST: proves explicit selection
        evidence_repo=ev_store,
    )

    plan = await service.create_plan(TENANT, db_action.action_id)
    # Leaf-first order puts the failing DB step LAST so every filesystem
    # step's result is recorded before the failure stops the run.
    assert plan.topological_order == [act2.action_id, act1.action_id, db_action.action_id]

    sim = await service.simulate_plan(TENANT, plan.plan_id)

    # P1: resulting state as recorded - all three actions have evidence; the
    #     file evidence carries baseline + agent change, simulation sees all
    #     steps as reversible (the failure has not happened yet).
    ev_db = await ev_store.get_by_action_id(TENANT, db_action.action_id)
    ev_f1 = await ev_store.get_by_action_id(TENANT, act1.action_id)
    ev_f2 = await ev_store.get_by_action_id(TENANT, act2.action_id)
    assert ev_db is not None and ev_f1 is not None and ev_f2 is not None
    assert ev_f1.compensation_payload["before_snapshot"]["content"] == BASELINE_1
    assert ev_f1.compensation_payload["after_snapshot"]["content"] == AGENT_1
    assert ev_f2.compensation_payload["before_snapshot"]["content"] == BASELINE_2
    assert ev_f2.compensation_payload["after_snapshot"]["content"] == AGENT_2
    assert sim["irreversible_actions"] == []

    executed = await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-b")
    results = executed.simulation_result["execution_results"]

    # P2: recovery is PARTIAL and reported as such - the run completed, the
    #     two filesystem steps succeeded + verified, the database step failed,
    #     and the plan-level outcome is UNKNOWN (never a full-success claim).
    assert executed.status == RecoveryStatus.COMPLETED
    assert executed.outcome == RecoveryOutcome.UNKNOWN
    assert results[act1.action_id]["execution_state"] == ExecutionState.SUCCEEDED.value
    assert results[act1.action_id]["success"] is True
    assert results[act1.action_id]["verification_passed"] is True
    assert results[act2.action_id]["execution_state"] == ExecutionState.SUCCEEDED.value
    assert results[act2.action_id]["success"] is True
    assert results[act2.action_id]["verification_passed"] is True
    assert results[db_action.action_id]["execution_state"] == ExecutionState.FAILED.value
    assert results[db_action.action_id]["success"] is False
    assert results[db_action.action_id]["verification_passed"] is False

    # P1 (post): file1/file2 restored to baseline; the failure did not leak
    #            into them.
    assert file1.read_text(encoding="utf-8") == BASELINE_1
    assert file2.read_text(encoding="utf-8") == BASELINE_2

    # P3: unrelated user data remains intact.
    assert bystander.read_text(encoding="utf-8") == UNRELATED

    # P4: retry is safe - the partial run leaves the plan outcome UNKNOWN, so
    #     any re-execution attempt is refused at the fail-closed outcome gate
    #     (the failed step cannot silently re-fire) and the restored files
    #     stay untouched by the refusal.
    with pytest.raises(ValueError, match="fail closed"):
        await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-b")
    assert file1.read_text(encoding="utf-8") == BASELINE_1
    assert file2.read_text(encoding="utf-8") == BASELINE_2

    # P5: evidence accurately reflects what occurred - the file evidence still
    #     shows baseline -> agent change, and the failure itself is recorded
    #     in the plan's execution results with explicit adapter attribution.
    assert ev_f1.compensation_payload["before_snapshot"]["content"] == BASELINE_1
    assert ev_f1.compensation_payload["after_snapshot"]["content"] == AGENT_1
    assert results[act1.action_id]["adapter"] == "filesystem_recovery"
    assert (
        results[act1.action_id]["adapter_selection"]
        == "filesystem_recovery_selected_for_live_execution"
    )
    assert results[db_action.action_id]["adapter"] == "mock"

    # P6: the system refuses unsupported guarantees - partial recovery is
    #     NEVER promoted to SAFE_AUTOMATIC, and the failure cannot be retried
    #     through the plan API.
    assert executed.outcome != RecoveryOutcome.SAFE_AUTOMATIC


# ---------------------------------------------------------------------------
# Scenario C
# ---------------------------------------------------------------------------


async def test_scenario_c_concurrent_user_edit_detected_not_overwritten(
    tmp_path: Path,
) -> None:
    """Scenario C (mission, verbatim): "A user edits a file after the agent's
    change; Interlock detects the conflict and does not silently overwrite the
    user's edit."

    Evidence class: LIVE local proof - production FilesystemRecoveryAdapter on
    real files (drift detection + conflict layer both run on real bytes) in a
    disposable tmp_path sandbox (not BLOCKED).
    """
    base = tmp_path / "sandbox-conflict"
    base.mkdir()
    target = base / "app_config.txt"
    target.write_text(BASELINE_1, encoding="utf-8")
    bystander = base / "notes.txt"
    bystander.write_text(UNRELATED, encoding="utf-8")

    baseline_snap = FilesystemRecoveryAdapter._capture_file_snapshot(target)
    assert baseline_snap is not None

    action = make_action(
        action_id="act-wp6-c",
        tenant_id=TENANT,
        tool="filesystem",
        resource="file:app_config.txt",
        action_type="modify",
    )
    action = replace(action, before_state_snapshot=baseline_snap)

    ev_store = _EvidenceStore()
    fs = FilesystemRecoveryAdapter(base_path=base)
    action_repo = MockActionRepo([action])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(
        action_repo, plan_repo, adapters=[fs], evidence_repo=ev_store
    )

    # Agent change first, then plan + simulation while the agent state holds.
    target.write_text(AGENT_1, encoding="utf-8")
    plan = await service.create_plan(TENANT, action.action_id)
    sim = await service.simulate_plan(TENANT, plan.plan_id)
    assert sim["surgical_simulation_results"][action.action_id][
        "would_succeed"
    ] is True

    # A user edits the file AFTER simulation (concurrent human modification).
    target.write_text(HUMAN_1, encoding="utf-8")

    executed = await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-c")
    results = executed.simulation_result["execution_results"]
    step_res = results[action.action_id]

    # P1: the resulting resource state is the USER's edit - the attempt was
    #     blocked and the file was NOT silently overwritten back to baseline.
    assert step_res["execution_state"] == ExecutionState.BLOCKED_BY_DRIFT.value
    assert step_res["success"] is False
    assert "Drift detected" in str(step_res.get("error", ""))
    assert target.read_text(encoding="utf-8") == HUMAN_1

    # P2: recovery status is UNCERTAIN (blocked) - never complete, never a
    #     silent success.
    assert executed.status == RecoveryStatus.COMPLETED  # the run itself finished
    assert executed.outcome == RecoveryOutcome.UNKNOWN

    # P3: unrelated user data remains intact.
    assert bystander.read_text(encoding="utf-8") == UNRELATED

    # P4: retry is safe - the blocked run leaves the plan outcome UNKNOWN, so
    #     re-execution is refused at the fail-closed outcome gate (the user's
    #     edit survives every retry attempt).
    with pytest.raises(ValueError, match="fail closed"):
        await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-c")
    assert target.read_text(encoding="utf-8") == HUMAN_1

    # P5: evidence accurately reflects what occurred at capture time - it
    #     still records baseline -> agent change (the human edit happened
    #     after, and was detected, not absorbed into the evidence).
    evidence = await ev_store.get_by_action_id(TENANT, action.action_id)
    assert evidence is not None
    assert evidence.compensation_payload["before_snapshot"]["content"] == BASELINE_1
    assert evidence.compensation_payload["after_snapshot"]["content"] == AGENT_1

    # The conflict layer independently classifies the human edit as a
    # concurrent mutation (second view beyond the drift gate that fired).
    conflict = await fs.check_conflicts(action, evidence)
    assert conflict.status == ConflictStatus.CONCURRENT_MUTATION.value

    # P6: the system refuses unsupported guarantees - no SAFE_AUTOMATIC claim
    #     exists anywhere for this run.
    assert executed.outcome != RecoveryOutcome.SAFE_AUTOMATIC
    assert step_res["success"] is False


# ---------------------------------------------------------------------------
# Scenario D
# ---------------------------------------------------------------------------


async def test_scenario_d_worker_crash_restart_resumes_without_duplicates(
    db_session: Any,
) -> None:
    """Scenario D (mission, verbatim): "A recovery worker crashes and
    restarts; orchestration resumes safely without duplicate destructive
    actions."

    Evidence class: LIVE local proof - real orchestrator, real SQLAlchemy
    durable-execution repository (SQLite), deterministic one-shot crash
    injection at a state-transition boundary, controllable lease clock.
    No sleeps and no timing races; no external infrastructure (not BLOCKED).
    """
    ev_store = _EvidenceStore()
    exec_repo = SQLAlchemyDurableExecutionRepository(db_session)
    counting = _CountingMockAdapter()
    clock = _TestClock()
    lease_store = InMemoryPlanLeaseStore(clock=clock)
    orch1 = DistributedRecoveryOrchestrator(
        evidence_repository=ev_store,
        execution_repository=exec_repo,
        adapters=[counting],
        lease_store=lease_store,
        lease_ttl_seconds=300.0,
    )
    orch2 = DistributedRecoveryOrchestrator(
        evidence_repository=ev_store,
        execution_repository=exec_repo,
        adapters=[counting],
        lease_store=lease_store,
        lease_ttl_seconds=300.0,
    )

    actions = [
        make_action(
            action_id=f"act-d-{i}",
            tenant_id=TENANT,
            tool="database",
            resource=f"record:wp6-d-{i}",
            action_type="insert",
        )
        for i in (1, 2, 3)
    ]
    for a in actions:
        await ev_store.save(make_evidence(a))
    order = [a.action_id for a in actions]
    plan_id = "plan-wp6-d"
    steps = await orch1.create_durable_plan(TENANT, plan_id, actions, order)
    assert len(steps) == 3

    # An unrelated plan must never be touched by this recovery run.
    other = make_action(
        action_id="act-wp6-d-other",
        tenant_id=TENANT,
        tool="database",
        resource="record:wp6-d-other",
        action_type="insert",
    )
    await ev_store.save(make_evidence(other))
    other_steps = await orch1.create_durable_plan(
        TENANT, "plan-wp6-d-unrelated", [other], [other.action_id]
    )

    # Deterministic crash: first evidence lookup for act-d-2 (state-transition
    # boundary of step 2, outside the adapter try-block) raises once.
    ev_store.crash_on_action = "act-d-2"
    lease1 = await lease_store.try_acquire(plan_id, orch1._instance_id, 300.0)
    assert lease1 is not None and lease1.fencing_token == 1

    with pytest.raises(RuntimeError, match="simulated worker crash"):
        await orch1._do_execute_durable_plan(TENANT, plan_id, lease=lease1)

    # P1: resulting resource state after the crash - step 1 committed, step 2
    #     never written, step 3 untouched.
    persisted = [
        (await exec_repo.get_by_step_id(TENANT, s.step_id)) for s in steps
    ]
    assert [p.execution_state for p in persisted] == [
        "succeeded",
        "pending",
        "pending",
    ]

    # P2: recovery status after the crash is PARTIAL/uncertain - the crashed
    #     run raised instead of returning any completion report, and only
    #     step 1 executed.
    assert dict(counting.execute_counts) == {"act-d-1": 1}

    # P4: retry safety while the crashed worker's lease is still unexpired -
    #     a concurrent submission collapses to already_running (no second
    #     executor starts, nothing double-fires).
    probe = await orch2.execute_durable_plan(TENANT, plan_id)
    assert probe["status"] == "already_running"
    assert dict(counting.execute_counts) == {"act-d-1": 1}

    # P3: unrelated plan data remains intact through crash + probe.
    other_row = await exec_repo.get_by_step_id(TENANT, other_steps[0].step_id)
    assert other_row is not None
    assert other_row.execution_state == "pending"

    # Deterministic lease expiry -> restart/takeover by the second instance.
    clock.advance(301)
    takeover = await orch2.execute_durable_plan(TENANT, plan_id)

    # P2 (post-restart): recovery is COMPLETE under a new fencing token, and
    #     the previously succeeded step is recognised as already completed
    #     (not re-executed).
    assert takeover["status"] == "completed"
    assert takeover["fencing_token"] == 2
    assert takeover["completed"] == 3
    assert takeover["execution_results"][actions[0].action_id][
        "already_completed"
    ] is True

    # P4/P6: no duplicate destructive actions - each step executed exactly
    #     once across crash, probe, and takeover.
    assert dict(counting.execute_counts) == {
        "act-d-1": 1,
        "act-d-2": 1,
        "act-d-3": 1,
    }
    final_states = [
        (await exec_repo.get_by_step_id(TENANT, s.step_id)).execution_state
        for s in steps
    ]
    assert final_states == ["succeeded", "succeeded", "succeeded"]

    # P4: replay after completion executes nothing (idempotent retry) and the
    #     fencing token keeps advancing (never repeats).
    replay = await orch2.execute_durable_plan(TENANT, plan_id)
    assert replay["status"] == "completed"
    assert replay["fencing_token"] == 3
    assert dict(counting.execute_counts) == {
        "act-d-1": 1,
        "act-d-2": 1,
        "act-d-3": 1,
    }

    # P3: unrelated plan still untouched after the replay.
    other_row = await exec_repo.get_by_step_id(TENANT, other_steps[0].step_id)
    assert other_row is not None
    assert other_row.execution_state == "pending"

    # P5: evidence accurately reflects what occurred - the stored steps carry
    #     exactly the evidence-recorded idempotency keys (a resumed run can
    #     never invent a divergent key).
    for a in actions:
        row = next(s for s in steps if s.action_id == a.action_id)
        stored = await exec_repo.get_by_step_id(TENANT, row.step_id)
        assert stored is not None
        assert stored.idempotency_key == f"idem-{a.action_id}"

    # P6: the crashed run never claimed completion (it raised - recorded above
    #     as a partial state, never as a success report).
    assert ev_store._crash_fired is True
    db_session.commit()


# ---------------------------------------------------------------------------
# Scenario E
# ---------------------------------------------------------------------------


async def test_scenario_e_stale_worker_cannot_commit_after_takeover(
    db_session: Any,
) -> None:
    """Scenario E (mission, verbatim): "Two workers compete for the same
    recovery plan; stale workers cannot commit writes after losing authority."

    Evidence class: LIVE local proof - real orchestrator, real SQLite durable
    repository fencing (conditional UPDATE with monotonic write fence),
    controllable clock for lease expiry (deterministic takeover; no sleeps;
    not BLOCKED).
    """
    ev_store = _EvidenceStore()
    exec_repo = SQLAlchemyDurableExecutionRepository(db_session)
    counting = _CountingMockAdapter()
    clock = _TestClock()
    lease_store = InMemoryPlanLeaseStore(clock=clock)
    orch_a = DistributedRecoveryOrchestrator(
        evidence_repository=ev_store,
        execution_repository=exec_repo,
        adapters=[counting],
        lease_store=lease_store,
        lease_ttl_seconds=300.0,
    )
    orch_b = DistributedRecoveryOrchestrator(
        evidence_repository=ev_store,
        execution_repository=exec_repo,
        adapters=[counting],
        lease_store=lease_store,
        lease_ttl_seconds=300.0,
    )

    actions = [
        make_action(
            action_id=f"act-e-{i}",
            tenant_id=TENANT,
            tool="database",
            resource=f"record:wp6-e-{i}",
            action_type="insert",
        )
        for i in (1, 2, 3)
    ]
    for a in actions:
        await ev_store.save(make_evidence(a))
    order = [a.action_id for a in actions]
    plan_id = "plan-wp6-e"
    steps = await orch_a.create_durable_plan(TENANT, plan_id, actions, order)

    other = make_action(
        action_id="act-wp6-e-other",
        tenant_id=TENANT,
        tool="database",
        resource="record:wp6-e-other",
        action_type="insert",
    )
    await ev_store.save(make_evidence(other))
    other_steps = await orch_a.create_durable_plan(
        TENANT, "plan-wp6-e-unrelated", [other], [other.action_id]
    )

    # Worker A acquires the lease (fencing token 1) and executes step 1.
    lease_a = await lease_store.try_acquire(plan_id, orch_a._instance_id, 300.0)
    assert lease_a is not None and lease_a.fencing_token == 1
    r1 = await orch_a._execute_single_step(
        TENANT, steps[0], fencing_token=lease_a.fencing_token
    )
    assert r1["execution_state"] == ExecutionState.SUCCEEDED.value
    assert dict(counting.execute_counts) == {"act-e-1": 1}

    # The lease expires (deterministic clock); worker B takes over with a
    # NEWER fencing token (2) and executes step 2.
    clock.advance(301)
    lease_b = await lease_store.try_acquire(plan_id, orch_b._instance_id, 300.0)
    assert lease_b is not None and lease_b.fencing_token == 2
    r2 = await orch_b._execute_single_step(
        TENANT, steps[1], fencing_token=lease_b.fencing_token
    )
    assert r2["execution_state"] == ExecutionState.SUCCEEDED.value
    assert dict(counting.execute_counts) == {"act-e-1": 1, "act-e-2": 1}

    # P6: the stale worker's plan-level attempt stops at the lease boundary -
    #     renew fails against the newer owner, so NOTHING executes, NOTHING is
    #     counted completed, and NO result is fabricated.
    stale_run = await orch_a._do_execute_durable_plan(
        TENANT, plan_id, lease=lease_a
    )
    assert stale_run["status"] == "lease_lost"
    assert stale_run["completed"] == 0
    assert stale_run["execution_results"] == {}
    assert dict(counting.execute_counts) == {"act-e-1": 1, "act-e-2": 1}

    # P6 (durable write boundary): a direct stale-token write is rejected by
    #     the fencing condition, and the newer worker's persisted state stays
    #     intact.
    step2_now = await exec_repo.get_by_step_id(TENANT, steps[1].step_id)
    assert step2_now is not None
    assert step2_now.execution_state == "succeeded"
    assert step2_now.write_fence == 2
    with pytest.raises(StaleFencingTokenError):
        await orch_a._update_step_state(
            step2_now,
            ExecutionState.FAILED.value,
            fencing_token=lease_a.fencing_token,
        )
    step2_after = await exec_repo.get_by_step_id(TENANT, steps[1].step_id)
    assert step2_after is not None
    assert step2_after.execution_state == "succeeded", "stale write landed"
    assert step2_after.write_fence == 2
    assert dict(counting.execute_counts) == {"act-e-1": 1, "act-e-2": 1}

    # P1/P2: the authoritative worker finishes the plan under its lease -
    #     recovery completes; earlier steps are recognised, not re-run.
    finish = await orch_b._do_execute_durable_plan(TENANT, plan_id, lease=lease_b)
    assert finish["status"] == "completed"
    assert finish["completed"] == 3
    await lease_store.release(plan_id, orch_b._instance_id)

    # P4: retry/takeover safety - exactly-once execution across both workers.
    assert dict(counting.execute_counts) == {
        "act-e-1": 1,
        "act-e-2": 1,
        "act-e-3": 1,
    }
    final_states = [
        (await exec_repo.get_by_step_id(TENANT, s.step_id)).execution_state
        for s in steps
    ]
    assert final_states == ["succeeded", "succeeded", "succeeded"]

    # P3: unrelated plan data remains intact throughout the competition.
    other_row = await exec_repo.get_by_step_id(TENANT, other_steps[0].step_id)
    assert other_row is not None
    assert other_row.execution_state == "pending"

    # P5: evidence accurately reflects what occurred - every persisted step
    #     carries exactly the evidence-recorded idempotency key, and the
    #     evidence itself is unchanged by the competition.
    for a in actions:
        row = next(s for s in steps if s.action_id == a.action_id)
        stored = await exec_repo.get_by_step_id(TENANT, row.step_id)
        assert stored is not None
        assert stored.idempotency_key == f"idem-{a.action_id}"
        evidence = await ev_store.get_by_action_id(TENANT, a.action_id)
        assert evidence is not None
        assert evidence.idempotency_key == f"idem-{a.action_id}"

    db_session.commit()


# ---------------------------------------------------------------------------
# Scenario F
# ---------------------------------------------------------------------------


def test_scenario_f_cross_tenant_evidence_access_denied_and_audited(
    client: TestClient, db_session: Any
) -> None:
    """Scenario F (mission, verbatim): "A tenant attempts to access another
    tenant's recovery evidence; access is denied and audited."

    Evidence class: LIVE local proof - real HTTP route through the real app,
    real auth tokens, real audit-log file. Documented scope deviation (section
    8 run log): the cross-tenant denial path was NOT audited before this work
    package, so this regression test was RED first; a minimal route-level
    ``log_security_event`` call closed the gap. Sync test: TestClient is sync,
    evidence seeding runs through ``asyncio.run``.
    """
    token_a = _register(client, f"wp6-a-{uuid4().hex[:8]}@example.com", TENANT_A)
    token_b = _register(client, f"wp6-b-{uuid4().hex[:8]}@example.com", TENANT_B)

    action_a = make_action(
        action_id=f"act-f-a-{uuid4().hex[:8]}",
        tenant_id=TENANT_A,
        tool="database",
        resource="record:wp6-f-a",
        action_type="insert",
    )
    action_b = make_action(
        action_id=f"act-f-b-{uuid4().hex[:8]}",
        tenant_id=TENANT_B,
        tool="database",
        resource="record:wp6-f-b",
        action_type="insert",
    )
    evidence_a = seal_evidence(replace(make_evidence(action_a), incident_id="inc-wp6-f-a"))
    evidence_b = seal_evidence(replace(make_evidence(action_b), incident_id="inc-wp6-f-b"))
    asyncio.run(_save_evidence_rows(db_session, [evidence_a, evidence_b]))

    url_a = f"/api/v1/recovery/evidence/{evidence_a.evidence_id}"

    # P6: the system refuses unsupported guarantees - tenant B gets a plain
    #     404 with NO evidence payload (no hash, no id, no state content).
    resp_b1 = client.get(url_a, headers=_auth_headers(token_b))
    assert resp_b1.status_code == 404
    assert "Recovery evidence not found" in resp_b1.text
    assert evidence_a.evidence_hash not in resp_b1.text
    assert evidence_a.evidence_id not in resp_b1.text

    # P2: the attempt resolves to a clean denial - no recovery outcome exists
    #     to claim (nothing was executed, nothing was disclosed).
    # P5: the denial is audited (the RED gap this test pins shut).
    denials = _audit_events_of(
        "recovery_evidence_access_denied", evidence_a.evidence_id
    )
    assert len(denials) == 1, "cross-tenant denial must be audited"
    assert denials[0]["tenant_id"] == TENANT_B

    # P1: resulting resource state - the denied attempt changed nothing; the
    #     owner still reads the identical sealed evidence.
    resp_a1 = client.get(url_a, headers=_auth_headers(token_a))
    assert resp_a1.status_code == 200
    assert resp_a1.json()["evidence_id"] == evidence_a.evidence_id
    assert resp_a1.json()["evidence_hash"] == evidence_a.evidence_hash
    views = _audit_events_of("recovery_evidence_viewed", evidence_a.evidence_id)
    assert len(views) == 1
    assert views[0]["tenant_id"] == TENANT_A

    # P3: isolation is scope-based - tenant B still reads its OWN evidence
    #     (the denial is not an outage for the denied tenant).
    resp_b_own = client.get(
        f"/api/v1/recovery/evidence/{evidence_b.evidence_id}",
        headers=_auth_headers(token_b),
    )
    assert resp_b_own.status_code == 200
    assert resp_b_own.json()["evidence_id"] == evidence_b.evidence_id

    # P4: retry is deterministic - the repeated attempt is denied again and
    #     audited again (no state from the first attempt leaked through).
    resp_b2 = client.get(url_a, headers=_auth_headers(token_b))
    assert resp_b2.status_code == 404
    assert (
        len(_audit_events_of("recovery_evidence_access_denied", evidence_a.evidence_id))
        == 2
    )

    # P1 (final): owner access still intact after all attempts.
    resp_a2 = client.get(url_a, headers=_auth_headers(token_a))
    assert resp_a2.status_code == 200
    assert resp_a2.json()["evidence_hash"] == evidence_a.evidence_hash


# ---------------------------------------------------------------------------
# Scenario G
# ---------------------------------------------------------------------------


async def test_scenario_g_lying_adapter_detected_by_independent_verification(
    tmp_path: Path,
) -> None:
    """Scenario G (mission, verbatim): "An adapter returns success while
    leaving incorrect state; independent verification detects the mismatch."

    Evidence class: LIVE local proof - the production planning pipeline runs
    against a real file in a disposable tmp_path sandbox; the adapter lies
    about execution + verification; the production independent-verification
    service decides from actual bytes (not BLOCKED).
    """
    base = tmp_path / "sandbox-lying"
    base.mkdir()
    target = base / "app_config.txt"
    target.write_text(BASELINE_1, encoding="utf-8")
    bystander = base / "notes.txt"
    bystander.write_text(UNRELATED, encoding="utf-8")

    baseline_snap = FilesystemRecoveryAdapter._capture_file_snapshot(target)
    assert baseline_snap is not None

    action = make_action(
        action_id="act-wp6-g",
        tenant_id=TENANT,
        tool="filesystem",
        resource="file:app_config.txt",
        action_type="modify",
    )
    action = replace(action, before_state_snapshot=baseline_snap)

    ev_store = _EvidenceStore()
    lying = _LyingFilesystemAdapter(base_path=base)
    action_repo = MockActionRepo([action])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(
        action_repo, plan_repo, adapters=[lying], evidence_repo=ev_store
    )

    # The agent's change; the lying adapter will "restore" it by doing nothing.
    target.write_text(AGENT_1, encoding="utf-8")
    plan = await service.create_plan(TENANT, action.action_id)
    await service.simulate_plan(TENANT, plan.plan_id)
    executed = await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-g")

    # P1: resulting resource state - the adapter CLAIMED success, the plan
    #     accepts the claim at plan level, but the file is still the agent's
    #     state (not restored).
    res = executed.simulation_result["execution_results"][action.action_id]
    assert res["success"] is True
    assert res["verification_passed"] is True
    assert executed.outcome == RecoveryOutcome.SAFE_AUTOMATIC  # the claim
    assert target.read_text(encoding="utf-8") == AGENT_1  # reality

    # Independent verification derives the observation from ACTUAL bytes.
    svc = IndependentVerificationService()
    verifier = svc.create_verifier(
        "v-wp6-g", IndependentVerifierRole.AUTOMATED_VERIFIER, TENANT
    )
    report = RecoveryReport(
        report_id="rep-wp6-g",
        tenant_id=TENANT,
        plan_id=plan.plan_id,
        incident_id=plan.incident_id,
        resource_results={
            action.action_id: {
                "status": VerificationStatus.EXECUTED_AND_VERIFIED.value,
                "verification": True,
            }
        },
        summary="adapter-claimed restore",
    )
    observed = _observe(target, BASELINE_1)
    assert observed == VerificationStatus.EXECUTION_FAILED.value
    ind = await svc.independent_verify(
        TENANT,
        plan.plan_id,
        plan.incident_id,
        verifier,
        report,
        observed_states={action.action_id: observed},
    )

    # P2: recovery is reported FAILED (never complete) despite the adapter's
    #     success claim, because the observation contradicts the claim.
    assert ind.outcome == VerificationOutcome.VERIFICATION_FAILED
    check = ind.checks[0]
    assert check.passed is False
    assert check.details["claim_diverged"] is True
    assert check.details["observed_status"] == VerificationStatus.EXECUTION_FAILED.value

    # P6: the system refuses unsupported guarantees - the verification never
    #     upgrades a contradicted claim to VERIFIED.
    assert ind.outcome != VerificationOutcome.VERIFIED
    assert ind.execution_verified is False

    # P4: retry is safe and deterministic - re-verification yields the same
    #     verdict, and the plan refuses a second execution outright.
    ind2 = await svc.independent_verify(
        TENANT,
        plan.plan_id,
        plan.incident_id,
        verifier,
        report,
        observed_states={action.action_id: observed},
    )
    assert ind2.outcome == VerificationOutcome.VERIFICATION_FAILED
    with pytest.raises(ValueError, match="does not allow execution"):
        await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-g")

    # P5: evidence accurately reflects what occurred - the sealed record of
    #     the agent's change is intact, and verification was read-only (the
    #     file is exactly as the adapter left it).
    evidence = await ev_store.get_by_action_id(TENANT, action.action_id)
    assert evidence is not None
    assert evidence.compensation_payload["before_snapshot"]["content"] == BASELINE_1
    assert evidence.compensation_payload["after_snapshot"]["content"] == AGENT_1
    assert target.read_text(encoding="utf-8") == AGENT_1

    # P3: unrelated user data remains intact.
    assert bystander.read_text(encoding="utf-8") == UNRELATED


# ---------------------------------------------------------------------------
# Scenario H
# ---------------------------------------------------------------------------


async def test_scenario_h_irreversible_operation_refuses_rollback_promise(
    tmp_path: Path,
) -> None:
    """Scenario H (mission, verbatim): "A recovery operation is unsupported or
    irreversible; Interlock refuses to promise rollback and reports the safe
    alternative."

    Evidence class: LIVE local proof - production planning pipeline against a
    real filesystem action marked IRREVERSIBLE, in a disposable tmp_path
    sandbox (not BLOCKED).
    """
    base = tmp_path / "sandbox-irreversible"
    base.mkdir()
    target = base / "destructive.sql"
    target.write_text(BASELINE_1, encoding="utf-8")
    bystander = base / "notes.txt"
    bystander.write_text(UNRELATED, encoding="utf-8")

    baseline_snap = FilesystemRecoveryAdapter._capture_file_snapshot(target)
    assert baseline_snap is not None

    action = make_action(
        action_id="act-wp6-h",
        tenant_id=TENANT,
        tool="filesystem",
        resource="file:destructive.sql",
        action_type="write",
        reversibility=Reversibility.IRREVERSIBLE,
    )
    action = replace(action, before_state_snapshot=baseline_snap)

    ev_store = _EvidenceStore()
    fs = FilesystemRecoveryAdapter(base_path=base)
    action_repo = MockActionRepo([action])
    plan_repo = MockPlanRepo([])
    service = RecoveryPlanningService(
        action_repo, plan_repo, adapters=[fs], evidence_repo=ev_store
    )

    plan = await service.create_plan(TENANT, action.action_id)

    # P6 (from creation): the plan NEVER promises a guaranteed rollback for an
    #     irreversible operation.
    assert plan.outcome == RecoveryOutcome.NOT_REVERSIBLE

    sim = await service.simulate_plan(TENANT, plan.plan_id)

    # P1: resulting resource state as recorded - the baseline exists in
    #     evidence and the simulation records the operation as irreversible.
    evidence = await ev_store.get_by_action_id(TENANT, action.action_id)
    assert evidence is not None
    assert evidence.compensation_payload["before_snapshot"]["content"] == BASELINE_1
    step_sim = sim["surgical_simulation_results"][action.action_id]
    assert step_sim["reversibility"] == Reversibility.IRREVERSIBLE.value
    assert step_sim["would_succeed"] is False

    # P5: evidence/simulation accurately reflect what occurred - the safe
    #     alternatives are reported: no automatic reversal, human approval
    #     required, explicit warnings.
    assert sim["irreversible_actions"] == [action.action_id]
    assert sim["approval_required_actions"] == [action.action_id]
    assert any(
        "irreversible actions cannot be automatically reversed" in w
        for w in sim["warnings"]
    )
    assert any(
        "require human approval" in w for w in sim["warnings"]
    )
    plan_after_sim = await plan_repo.get_by_plan_id(TENANT, plan.plan_id)
    assert plan_after_sim is not None
    assert plan_after_sim.status == RecoveryStatus.SIMULATED
    assert plan_after_sim.outcome == RecoveryOutcome.NOT_REVERSIBLE

    # P2: recovery status - execution is REFUSED (failed closed), twice, with
    #     the identical error; no partial run ever starts.
    with pytest.raises(ValueError, match="irreversible"):
        await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-h")
    with pytest.raises(ValueError, match="irreversible"):
        await service.execute_plan(TENANT, plan.plan_id, "approver-wp6-h")

    # P1 (post): resulting resource state - the file is untouched by the
    #     refusals.
    assert target.read_text(encoding="utf-8") == BASELINE_1

    # P4: retry is safe - repeated attempts keep refusing; plan status/outcome
    #     remain refused rather than degrading into a partial execution.
    plan_final = await plan_repo.get_by_plan_id(TENANT, plan.plan_id)
    assert plan_final is not None
    assert plan_final.status == RecoveryStatus.SIMULATED
    assert plan_final.outcome == RecoveryOutcome.NOT_REVERSIBLE

    # P3: unrelated user data remains intact.
    assert bystander.read_text(encoding="utf-8") == UNRELATED

    # P6: the system refuses unsupported guarantees - no SAFE_AUTOMATIC claim
    #     and no COMPLETED status can exist for the refused plan.
    assert plan_final.outcome != RecoveryOutcome.SAFE_AUTOMATIC
    assert plan_final.status != RecoveryStatus.COMPLETED


# ---------------------------------------------------------------------------
# Scenario I
# ---------------------------------------------------------------------------


async def test_scenario_i_corrupted_or_unavailable_evidence_reports_uncertainty(
) -> None:
    """Scenario I (mission, verbatim): "Evidence is corrupted or unavailable;
    Interlock reports uncertainty rather than inventing success."

    Evidence class: LIVE local proof - production v2 seal
    (``seal_evidence``) and production integrity verification; three-way
    discrimination (verified / tampered / inconclusive) with an intact control
    so the assertions cannot pass by always failing (not BLOCKED).
    """
    svc = IndependentVerificationService()
    action = make_action(
        action_id="act-wp6-i",
        tenant_id=TENANT,
        tool="database",
        resource="record:wp6-i",
        action_type="insert",
    )
    other_action = make_action(
        action_id="act-wp6-i-other",
        tenant_id=TENANT,
        tool="database",
        resource="record:wp6-i-other",
        action_type="insert",
    )
    sealed = seal_evidence(replace(make_evidence(action), incident_id="inc-wp6-i"))
    sealed_other = seal_evidence(make_evidence(other_action))
    sealed_hash_before = sealed.evidence_hash

    def _integrity(results: list[Any]) -> Any:
        return next(r for r in results if r.layer == VerificationLayer.INTEGRITY)

    # P1: resulting resource state of the evidence layer - the seal chain
    #     verifies for intact evidence, and the tamper diverges from it.
    assert compute_evidence_hash_v2(sealed) == sealed.evidence_hash
    tampered = replace(sealed, target_resource="file:evil-tampered.txt")
    assert tampered != sealed
    assert compute_evidence_hash_v2(tampered) != tampered.evidence_hash

    intact = _integrity(
        svc.run_multi_layer_verification(
            TENANT, "plan-wp6-i", action.action_id, evidence=sealed
        )
    )
    corrupt = _integrity(
        svc.run_multi_layer_verification(
            TENANT, "plan-wp6-i", action.action_id, evidence=tampered
        )
    )
    missing = _integrity(
        svc.run_multi_layer_verification(
            TENANT, "plan-wp6-i", action.action_id, evidence=None
        )
    )

    # P2: recovery/evidence status - three-way discrimination, never a
    #     rubber stamp: intact VERIFIED, tampered EVIDENCE_TAMPERED,
    #     unavailable INCONCLUSIVE.
    assert intact.status == VerificationOutcome.VERIFIED
    assert intact.passed is True
    assert corrupt.status == VerificationOutcome.EVIDENCE_TAMPERED
    assert corrupt.passed is False
    assert corrupt.details["integrity_ok"] is False
    assert corrupt.details["issues"], "tamper must be explained, not silent"
    assert missing.status == VerificationOutcome.INCONCLUSIVE
    assert missing.passed is False
    assert "no evidence" in str(missing.details.get("reason", ""))

    # P6: the system refuses unsupported guarantees - corrupted or missing
    #     evidence NEVER verifies (uncertainty, not success).
    assert corrupt.status != VerificationOutcome.VERIFIED
    assert missing.status != VerificationOutcome.VERIFIED

    # P5: evidence accurately reflects what occurred - the original sealed
    #     object was not mutated by the tamper attempt (immutable object, hash
    #     still matches its seal).
    assert sealed.evidence_hash == sealed_hash_before
    assert sealed.target_resource == action.resource
    assert compute_evidence_hash_v2(sealed) == sealed.evidence_hash

    # P3: unrelated user data (here: another action's sealed evidence)
    #     remains intact and verifiable while one record is tampered.
    other_intact = _integrity(
        svc.run_multi_layer_verification(
            TENANT,
            "plan-wp6-i-other",
            other_action.action_id,
            evidence=sealed_other,
        )
    )
    assert other_intact.status == VerificationOutcome.VERIFIED

    # P4: retry is safe and deterministic - same inputs, same verdicts.
    corrupt_again = _integrity(
        svc.run_multi_layer_verification(
            TENANT, "plan-wp6-i", action.action_id, evidence=tampered
        )
    )
    assert corrupt_again.status == VerificationOutcome.EVIDENCE_TAMPERED
    intact_again = _integrity(
        svc.run_multi_layer_verification(
            TENANT, "plan-wp6-i", action.action_id, evidence=sealed
        )
    )
    assert intact_again.status == VerificationOutcome.VERIFIED


# ---------------------------------------------------------------------------
# Scenario J
# ---------------------------------------------------------------------------


async def test_scenario_j_backup_restore_drill_recovers_evidence_disposable_env(
    tmp_path: Path,
) -> None:
    """Scenario J (mission, verbatim): "Backup and restore recover Interlock's
    own required metadata and evidence in a disposable environment."

    Evidence class: LIVE local proof - the production backup/restore utility
    in a tmp_path disposable environment (real SQLite snapshot, real SHA-256
    manifest, real evidence-chain verification; reuses the WP-5 drill seed and
    chain helpers). No external infrastructure (not BLOCKED).
    """
    db = tmp_path / "wp6-drill.sqlite3"
    await _seed(db)

    # P3 setup: an unrelated tenant's metadata exists alongside the drill data
    # BEFORE the backup, so preservation can be proven after restore.
    engine = create_engine(f"sqlite:///{db}")
    session = sessionmaker(bind=engine)()
    try:
        now = datetime.now(UTC)
        session.add(
            RecoveryPlanModel(
                plan_id="plan-wp6-unrelated",
                tenant_id="tenant-wp6-unrelated",
                incident_action_id="act-wp6-unrelated",
                created_at=now,
                updated_at=now,
                incident_id="inc-wp6-unrelated",
            )
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    out = tmp_path / "wp6-backup"
    manifest = export_backup(db, out)

    # P2: the backup captured exactly the evidence set it claims to hold.
    assert manifest["evidence_count"] == DRILL_EVIDENCE_ROWS
    assert set(manifest["artifacts"]) == {"snapshot.sqlite3", "evidence_dump.json"}

    # P6: the system refuses unsupported guarantees - a tampered backup copy
    #     fails closed at manifest verification (on a COPY, so the pristine
    #     backup stays usable for the real drill).
    tamper = tmp_path / "wp6-backup-tampered"
    shutil.copytree(out, tamper)
    dump = tamper / "evidence_dump.json"
    text = dump.read_text(encoding="utf-8")
    tampered = text.replace('"evidence"', '"evidencE"')
    assert tampered != text, "tamper must actually change the artifact"
    dump.write_text(tampered, encoding="utf-8")
    with pytest.raises(BackupVerificationError, match="manifest mismatch"):
        restore_backup(tamper, tmp_path / "wp6-never-made.sqlite3")

    # P5 (pre): evidence accurately reflects what occurred before destruction -
    #     the live chain verifies against the sealed v2 hashes.
    total_pre, broken_pre = await _chain_from_db(db)
    assert total_pre == DRILL_EVIDENCE_ROWS
    assert broken_pre == []

    # Destroy the database (disposable environment) and restore from backup.
    db.unlink()
    assert not db.exists()
    report = restore_backup(out, db)

    # P2: the restore report matches reality exactly - snapshot restored and
    #     every captured evidence row re-verified.
    assert report["snapshot_restored"] is True
    assert report["evidence_verified"] == DRILL_EVIDENCE_ROWS
    assert db.exists()

    # P1: resulting resource state - the evidence chain verifies FROM the
    #     restored database via the repository's public API.
    total, broken = await _chain_from_db(db)
    assert total == DRILL_EVIDENCE_ROWS
    assert broken == []

    # P3: unrelated user data remains intact - both the drill's plan row AND
    #     the unrelated tenant's row survived the round-trip.
    engine2 = create_engine(f"sqlite:///{db}")
    s2 = sessionmaker(bind=engine2)()
    try:
        drill_plan = s2.scalar(
            select(RecoveryPlanModel).where(RecoveryPlanModel.plan_id == DRILL_PLAN_ID)
        )
        assert drill_plan is not None
        assert drill_plan.tenant_id == DRILL_TENANT
        other = s2.scalar(
            select(RecoveryPlanModel).where(
                RecoveryPlanModel.plan_id == "plan-wp6-unrelated"
            )
        )
        assert other is not None
        assert other.tenant_id == "tenant-wp6-unrelated"
        assert other.incident_id == "inc-wp6-unrelated"
    finally:
        s2.close()
        engine2.dispose()

    # P4: retry is safe - repeating the same restore yields the identical
    #     verified result (nothing lost, nothing double-applied).
    report2 = restore_backup(out, db)
    assert report2["snapshot_restored"] is True
    assert report2["evidence_verified"] == DRILL_EVIDENCE_ROWS

    # P5 (final): evidence/manifest accurately reflect what occurred - every
    #     manifest artifact hash still matches its artifact byte-for-byte.
    for name, digest in manifest["artifacts"].items():
        assert _sha256(out / name) == digest
