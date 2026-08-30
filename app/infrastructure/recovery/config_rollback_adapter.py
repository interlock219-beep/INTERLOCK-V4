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


class ConfigRollbackAdapter(RecoveryAdapter):
    adapter_name = "config_rollback"
    adapter_type = "config_rollback"
    capability = AdapterCapability.SIMULATION_CAPABLE

    def __init__(self, config_store: Any | None = None) -> None:
        self._config_store = config_store

    async def can_recover(self, action: ProtectedAction) -> str:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return "irreversible"
        if action.before_state_ref:
            return "conditionally_reversible"
        return "unknown"

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        return AdapterCapabilityDeclaration(
            adapter_name="config_rollback",
            adapter_type="config_rollback",
            can_capture_before_state=True,
            can_capture_after_state=True,
            can_read_current_state=False,
            can_compute_delta=False,
            can_detect_drift=False,
            can_simulate=True,
            can_compensate=True,
            can_verify=True,
            supports_idempotency=True,
            supports_versioning=True,
            supports_safe_merge=False,
            merge_safety=MergeSafety.MERGE_UNSUPPORTED,
            declared_capabilities=[
                "config_revert",
                "snapshot_based",
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
        before_ref = action.before_state_ref or f"config:{action.action_id}:before"
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
            target_system="config_store",
            target_resource=action.resource,
            action_type=action.action_type,
            before_state_reference=before_ref,
            after_state_reference=action.after_state_ref or f"config:{action.action_id}:after",
            compensation_payload={"operation": "revert_config", "target": action.resource},
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.CONFIG_ROLLBACK,
            idempotency_key=f"idem-{action.action_id}",
            dependency_edges=[],
            reversibility_classification=Reversibility.normalize(action.reversibility),
            state_version=action.policy_version,
            evidence_hash=evidence_hash,
            adapter_capability=AdapterCapability.SIMULATION_CAPABLE,
            verification_requirements=["config_snapshot_available"],
        )

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return rev
        if evidence.before_state_reference:
            return RevEnum.CONDITIONALLY_REVERSIBLE
        return RevEnum.CONDITIONALLY_REVERSIBLE

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        rev = await self.classify_reversibility(action, evidence)
        would_succeed = rev != RevEnum.IRREVERSIBLE and evidence.before_state_reference is not None
        warnings: list[str] = []
        sim_limit = SimulationLimitation.SIMULATION_LIMITED
        if evidence.before_state_reference is None:
            warnings.append("No before-state reference: manual intervention required")
        return RollbackImpact(
            action_id=action.action_id,
            reversibility=rev,
            would_succeed=would_succeed,
            drift_status=DriftStatus.NO_DRIFT,
            conflict_status=ConflictStatus.NO_CONFLICT,
            compensation_operation="revert_config",
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
        if action.before_state_ref is None:
            return PreconditionResult(
                satisfied=False,
                failed_checks=["missing_before_state_ref"],
                details={"reason": "No before-state reference available"},
            )
        return PreconditionResult(satisfied=True)

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        if current_state is None:
            return DriftResult(
                status=DriftStatus.NO_DRIFT,
                details={"reason": "No current state provided, assuming no drift"},
            )
        return DriftResult(status=DriftStatus.NO_DRIFT, current_state=current_state)

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
        if current_state is None:
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)
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
            compensation_payload={"operation": "revert_config", "target": action.resource},
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
        return CompensationResult(
            action_id=compensation.action_id,
            success=False,
            execution_state=ExecutionState.REQUIRES_MANUAL_ACTION,
            idempotency_key=idempotency_key,
            details={"operation": compensation.compensation_payload.get("operation", "unknown")},
            external_outcome="reference_adapter_not_implemented",
            error=(
                "ConfigRollbackAdapter is a reference implementation and does not perform actual "
                "config restoration. Deploy a production adapter for real recovery."
            ),
        )

    async def verify(
        self,
        compensation: CompensationAction,
    ) -> VerificationResult:
        return VerificationResult(
            action_id=compensation.action_id,
            verified=False,
            details={"reason": "Reference adapter does not perform actual verification"},
        )

    async def preview_recovery(self, action: ProtectedAction) -> dict[str, Any]:
        return {
            "adapter": "config_rollback",
            "adapter_type": "config_rollback",
            "capability": "simulation_capable",
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
            "adapter": "config_rollback",
            "action_id": action.action_id,
            "status": "rolled_back",
            "mock": True,
            "before_state_ref": action.before_state_ref,
            "executed_by": approved_by,
        }
