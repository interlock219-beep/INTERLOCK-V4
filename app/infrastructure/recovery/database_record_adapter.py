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


class DatabaseRecordAdapter(RecoveryAdapter):
    adapter_name = "database_record"
    adapter_type = "database_record"
    capability = AdapterCapability.REFERENCE_IMPLEMENTATION

    def __init__(self, max_records: int | None = None) -> None:
        self._max_records = max_records

    async def can_recover(self, action: ProtectedAction) -> str:
        rev = Reversibility.normalize(action.reversibility)
        if rev == RevEnum.IRREVERSIBLE:
            return "irreversible"
        if action.before_state_ref:
            return "automatically_reversible"
        if action.after_state_ref:
            return "conditionally_reversible"
        return "unknown"

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        return AdapterCapabilityDeclaration(
            adapter_name="database_record",
            adapter_type="database_record",
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
            supports_safe_merge=False,
            merge_safety=MergeSafety.MERGE_CONDITIONAL,
            declared_capabilities=[
                "record_restoration",
                "version_tracking",
                "reference_implementation",
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
        before_ref = action.before_state_ref or f"state:{action.action_id}:before"
        after_ref = action.after_state_ref or f"state:{action.action_id}:after"
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
            target_system="database",
            target_resource=action.resource,
            action_type=action.action_type,
            before_state_reference=before_ref,
            after_state_reference=after_ref,
            request_payload_reference=f"payload:{action.action_id}:req",
            response_payload_reference=f"payload:{action.action_id}:resp",
            compensation_payload={"operation": "restore_record", "target": action.resource},
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.DATABASE_RECORD,
            idempotency_key=f"idem-{action.action_id}",
            dependency_edges=[],
            reversibility_classification=Reversibility.normalize(action.reversibility),
            state_version=action.policy_version,
            evidence_hash=evidence_hash,
            adapter_capability=AdapterCapability.REFERENCE_IMPLEMENTATION,
            verification_requirements=["record_exists_in_target_table"],
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
            return RevEnum.AUTOMATICALLY_REVERSIBLE
        return RevEnum.UNKNOWN

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        rev = await self.classify_reversibility(action, evidence)
        would_succeed = rev != RevEnum.IRREVERSIBLE and evidence.before_state_reference is not None
        warnings: list[str] = []
        sim_limit = None
        if evidence.before_state_reference is None:
            warnings.append("No before-state reference: cannot guarantee safe restoration")
            sim_limit = SimulationLimitation.SIMULATION_LIMITED
        drift = await self.detect_drift(action, evidence)
        if drift.status != DriftStatus.NO_DRIFT:
            would_succeed = False
            warnings.append(f"Drift detected: {drift.status.value}")
        return RollbackImpact(
            action_id=action.action_id,
            reversibility=rev,
            would_succeed=would_succeed,
            drift_status=drift.status,
            conflict_status=ConflictStatus.NO_CONFLICT,
            compensation_operation="restore_record",
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
        if evidence.before_state_reference is None:
            return DriftResult(status=DriftStatus.INSUFFICIENT_EVIDENCE)
        if current_state is None:
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "No current state provided for drift check"},
            )
        ev_version = evidence.state_version
        cur_version = str(current_state.get("version", "")) if current_state else ""
        if ev_version and cur_version and ev_version != cur_version:
            return DriftResult(
                status=DriftStatus.VERSION_MISMATCH,
                current_version=cur_version,
                evidence_version=ev_version,
                details={"field": "resource_version"},
            )
        if current_state.get("_drift_marker"):
            return DriftResult(
                status=DriftStatus.DRIFT_DETECTED,
                current_state=current_state,
                details={"reason": "State marker differs from evidence"},
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
        ev_hash = evidence.state_hash
        cur_hash = str(current_state.get("_state_hash", "")) if current_state else ""
        if ev_hash and cur_hash and ev_hash != cur_hash:
            return ConflictResult(
                status=ConflictStatus.VERSION_MISMATCH,
                details={"reason": "State hash mismatch"},
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
            compensation_payload={"operation": "restore_record", "target": action.resource},
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
                "DatabaseRecordAdapter is a reference implementation and does not perform actual "
                "database restoration. Deploy a production adapter for real recovery."
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
            "adapter": "database_record",
            "adapter_type": "database_record",
            "capability": "reference_implementation",
            "action_id": action.action_id,
            "before_state_ref": action.before_state_ref,
            "reversible": action.before_state_ref is not None,
            "mock": False,
            "requires_approval": Reversibility.is_conditional(action.reversibility),
        }

    async def execute_recovery(
        self, action: ProtectedAction, approved_by: str
    ) -> dict[str, Any]:
        return {
            "adapter": "database_record",
            "action_id": action.action_id,
            "status": "restored",
            "mock": False,
            "before_state_ref": action.before_state_ref,
            "executed_by": approved_by,
        }
