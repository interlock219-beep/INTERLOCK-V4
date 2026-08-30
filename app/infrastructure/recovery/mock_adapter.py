from typing import Any

from app.domain.entities.causal_state_types import (
    AdapterCapabilityDeclaration,
    MergeSafety,
)
from app.domain.entities.protected_action import ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationAction,
    CompensationResult,
    CompensationType,
    ConflictResult,
    ConflictStatus,
    DriftResult,
    DriftStatus,
    ExecutionState,
    PreconditionResult,
    RecoveryAdapterType,
    RecoveryEvidence,
    RollbackImpact,
    SimulationLimitation,
    VerificationResult,
)
from app.domain.entities.surgical_recovery_types import (
    Reversibility as RevEnum,
)
from app.domain.services.recovery_adapter import RecoveryAdapter


class MockRecoveryAdapter(RecoveryAdapter):
    """Mock adapter that simulates recovery without touching external systems."""

    adapter_name = "mock"
    adapter_type = "mock"
    capability = AdapterCapability.MOCK

    def __init__(self, scenario: str | None = None) -> None:
        self._scenario = scenario

    async def can_recover(self, action: ProtectedAction) -> str:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return "irreversible"
        if rev == RevEnum.MANUALLY_RECOVERABLE:
            return "requires_approval"
        if action.before_state_ref:
            return "reversible"
        return "unknown"

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        return AdapterCapabilityDeclaration(
            adapter_name="mock",
            adapter_type="mock",
            can_capture_before_state=True,
            can_capture_after_state=True,
            can_read_current_state=True,
            can_compute_delta=True,
            can_detect_drift=True,
            can_simulate=True,
            can_compensate=True,
            can_verify=True,
            supports_idempotency=True,
            supports_versioning=True,
            supports_safe_merge=True,
            merge_safety=MergeSafety.MERGE_SAFE,
            declared_capabilities=[
                "full_simulation",
                "scenario_driven",
                "deterministic",
            ],
        )

    async def capture_recovery_evidence(
        self,
        action: ProtectedAction,
        execution_context: dict[str, Any] | None = None,
    ) -> RecoveryEvidence:
        import hashlib
        import json

        payload_str = json.dumps(action.tool_arguments, sort_keys=True, default=str)
        evidence_hash = hashlib.sha256(
            f"{action.action_id}:{payload_str}".encode()
        ).hexdigest()
        before_ref = action.before_state_ref or f"mock:{action.action_id}:before"
        return RecoveryEvidence(
            evidence_id=f"ev-{action.action_id}",
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            agent_id=action.agent_id,
            authority_grant_id=action.authority_grant_id,
            parent_action_id=action.parent_action_id,
            root_action_id=action.parent_action_id or action.action_id,
            correlation_id=action.correlation_id,
            incident_id="",
            target_system="mock",
            target_resource=action.resource,
            action_type=action.action_type,
            before_state_reference=before_ref,
            after_state_reference=action.after_state_ref or f"mock:{action.action_id}:after",
            compensation_payload={"operation": "mock_revert", "target": action.resource},
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.MOCK,
            idempotency_key=f"idem-{action.action_id}",
            dependency_edges=[],
            reversibility_classification=Reversibility.normalize(action.reversibility),
            state_version=action.policy_version,
            evidence_hash=evidence_hash,
            adapter_capability=AdapterCapability.MOCK,
            verification_requirements=["mock_verification"],
        )

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return rev
        if self._scenario == "unknown_reversibility":
            return RevEnum.UNKNOWN
        if evidence.before_state_reference:
            return RevEnum.AUTOMATICALLY_REVERSIBLE
        return RevEnum.CONDITIONALLY_REVERSIBLE

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        rev = await self.classify_reversibility(action, evidence)
        would_succeed = rev != RevEnum.IRREVERSIBLE
        if self._scenario == "force_fail":
            would_succeed = False
        warnings: list[str] = []
        if rev == RevEnum.UNKNOWN:
            warnings.append("Reversibility is UNKNOWN — fail closed")
        if not evidence.before_state_reference:
            warnings.append("No before-state reference: mock restoration may not be safe")
        drift = await self.detect_drift(action, evidence)
        conflict = await self.check_conflicts(action, evidence)
        if drift.status != DriftStatus.NO_DRIFT:
            would_succeed = False
            warnings.append(f"Drift detected: {drift.status.value}")
        if conflict.status != ConflictStatus.NO_CONFLICT:
            would_succeed = False
            warnings.append(f"Conflict detected: {conflict.status.value}")
        sim_limit = SimulationLimitation.SIMULATION_COMPLETE
        if not would_succeed:
            sim_limit = SimulationLimitation.SIMULATION_LIMITED
        return RollbackImpact(
            action_id=action.action_id,
            reversibility=rev,
            would_succeed=would_succeed,
            drift_status=drift.status,
            conflict_status=conflict.status,
            compensation_operation="mock_revert",
            compensation_payload=evidence.compensation_payload,
            external_api_calls=[],
            warnings=warnings,
            simulation_limitation=sim_limit,
            expected_after_state={"restored_to": evidence.before_state_reference},
        )

    async def check_preconditions(
        self,
        action: ProtectedAction,
        current_state: dict[str, Any] | None = None,
    ) -> PreconditionResult:
        return PreconditionResult(satisfied=True)

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        if self._scenario == "drift_detected":
            return DriftResult(
                status=DriftStatus.DRIFT_DETECTED,
                details={"reason": "Mock: drift detected by scenario"},
            )
        if self._scenario == "version_mismatch":
            return DriftResult(
                status=DriftStatus.VERSION_MISMATCH,
                details={"reason": "Mock: version mismatch by scenario"},
            )
        return DriftResult(status=DriftStatus.NO_DRIFT, current_state=current_state)

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
        if self._scenario == "conflict_detected":
            return ConflictResult(
                status=ConflictStatus.CONFLICT_DETECTED,
                details={"reason": "Mock: conflict detected by scenario"},
            )
        if self._scenario == "version_mismatch":
            return ConflictResult(
                status=ConflictStatus.VERSION_MISMATCH,
                details={"reason": "Mock: version mismatch by scenario"},
            )
        return ConflictResult(status=ConflictStatus.NO_CONFLICT)

    async def generate_compensation(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> CompensationAction:
        return CompensationAction(
            action_id=action.action_id,
            incident_action_id=action.parent_action_id or action.action_id,
            compensation_type=CompensationType.REVERSE_OPERATION,
            compensation_payload={"operation": "mock_revert", "target": action.resource},
            idempotency_key=evidence.idempotency_key,
            target_system=evidence.target_system,
            target_resource=evidence.target_resource,
            execution_order=0,
            reversibility=evidence.reversibility_classification,
            drift_status=DriftStatus.NO_DRIFT,
            conflict_status=ConflictStatus.NO_CONFLICT,
            verification_requirements=evidence.verification_requirements,
            dependency_edges=evidence.dependency_edges,
        )

    async def execute_compensation(
        self,
        compensation: CompensationAction,
        idempotency_key: str,
    ) -> CompensationResult:
        if compensation.idempotency_key != idempotency_key:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.BLOCKED_BY_CONFLICT,
                idempotency_key=idempotency_key,
                error="Idempotency key mismatch",
            )
        if self._scenario == "execute_fail":
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error="Mock execution failed by scenario",
            )
        if self._scenario == "drift_detected":
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.BLOCKED_BY_DRIFT,
                idempotency_key=idempotency_key,
                error="Mock: drift detected, cannot execute compensation",
            )
        if self._scenario == "conflict_detected":
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.BLOCKED_BY_CONFLICT,
                idempotency_key=idempotency_key,
                error="Mock: conflict detected, cannot execute compensation",
            )
        if self._scenario == "success":
            return CompensationResult(
                action_id=compensation.action_id,
                success=True,
                execution_state=ExecutionState.SUCCEEDED,
                idempotency_key=idempotency_key,
                details={"operation": "mock_revert"},
                external_outcome="mock_succeeded",
            )
        return CompensationResult(
            action_id=compensation.action_id,
            success=False,
            execution_state=ExecutionState.REQUIRES_MANUAL_ACTION,
            idempotency_key=idempotency_key,
            details={"operation": "mock_revert"},
            external_outcome="mock_not_implemented",
            error=(
                "MockRecoveryAdapter does not perform actual recovery. "
                "Use a production adapter for real recovery operations."
            ),
        )

    async def verify(
        self,
        compensation: CompensationAction,
    ) -> VerificationResult:
        return VerificationResult(
            action_id=compensation.action_id,
            verified=False,
            details={"reason": "Mock adapter does not perform actual verification"},
        )

    async def preview_recovery(self, action: ProtectedAction) -> dict[str, Any]:
        return {
            "adapter": "mock",
            "adapter_type": "mock",
            "capability": "mock",
            "action_id": action.action_id,
            "before_state_ref": action.before_state_ref,
            "reversible": action.before_state_ref is not None,
            "mock": True,
            "requires_approval": Reversibility.is_conditional(action.reversibility),
        }

    async def execute_recovery(
        self, action: ProtectedAction, approved_by: str
    ) -> dict[str, Any]:
        return {
            "adapter": "mock",
            "action_id": action.action_id,
            "status": "restored",
            "mock": True,
            "before_state_ref": action.before_state_ref,
            "executed_by": approved_by,
        }
