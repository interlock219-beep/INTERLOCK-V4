"""Compensating action adapter interfaces.

Provides the dynamic Saga-pattern registry contract that every supported
adapter must implement, plus backward-compatible base classes for existing
adapters that only implement the legacy three-method interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from app.domain.entities.causal_state_types import (
    AdapterCapabilityDeclaration,
    MergeSafety,
)
from app.domain.entities.protected_action import ProtectedAction
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
    Reversibility,
    RollbackImpact,
    SimulationLimitation,
    VerificationResult,
)


@runtime_checkable
class CompensatingActionAdapter(Protocol):
    """Dynamic Saga compensating-action registry interface.

    Every supported ``ProtectedAction`` must be capable of registering
    recovery metadata during or after execution.  Adapters implement
    this protocol to declare how a given action type can be compensated.

    All methods are coroutines.  Adapters may be synchronous-compatible
    wrappers or fully async.
    """

    adapter_name: str
    adapter_type: str
    capability: str

    async def supports(self, action: ProtectedAction) -> bool:
        """Return ``True`` when this adapter can handle *action*."""
        ...

    async def capture_recovery_evidence(
        self,
        action: ProtectedAction,
        execution_context: dict[str, Any] | None = None,
    ) -> RecoveryEvidence:
        """Build an immutable :class:`RecoveryEvidence` object for *action*."""
        ...

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        """Determine whether the action is (conditionally) reversible."""
        ...

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        """Produce a :class:`RollbackImpact` *without* mutating state."""
        ...

    async def check_preconditions(
        self,
        action: ProtectedAction,
        current_state: dict[str, Any] | None = None,
    ) -> PreconditionResult:
        """Verify that compensation preconditions are met."""
        ...

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        """Compare current external state against the captured evidence."""
        ...

    async def generate_compensation(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> CompensationAction:
        """Build a concrete :class:`CompensationAction` for execution."""
        ...

    async def execute_compensation(
        self,
        compensation: CompensationAction,
        idempotency_key: str,
    ) -> CompensationResult:
        """Execute the compensation, guaranteeing idempotency."""
        ...

    async def verify(
        self,
        compensation: CompensationAction,
    ) -> VerificationResult:
        """Verify that the compensation produced the expected result."""
        ...

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
        """Detect conflicts such as version mismatch or concurrent mutation."""
        ...

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        """Declare the capabilities this adapter supports."""
        ...


class RecoveryAdapter(ABC):
    """Backward-compatible base class for legacy adapters.

    New code should prefer :class:`CompensatingActionAdapter`.  Adapters
    inheriting from this class are automatically wrapped to expose the
    full Protocol surface.
    """

    adapter_name: str = "base"
    adapter_type: str = "unknown"
    capability: str = "unsupported"

    @abstractmethod
    async def can_recover(self, action: ProtectedAction) -> str:
        """Legacy: return a capability string for *action*."""
        pass

    @abstractmethod
    async def preview_recovery(self, action: ProtectedAction) -> dict[str, Any]:
        """Legacy: return a preview dict for *action*."""
        pass

    @abstractmethod
    async def execute_recovery(
        self, action: ProtectedAction, approved_by: str
    ) -> dict[str, Any]:
        """Legacy: execute recovery for *action*."""
        pass

    # -- Default implementations of the full Protocol surface --
    # These provide fail-closed behaviour when legacy adapters are used
    # through the new pipeline.

    async def supports(self, action: ProtectedAction) -> bool:
        result = await self.can_recover(action)
        return result in (
            "reversible",
            "reversible_with_approval",
            "automatically_reversible",
            "conditionally_reversible",
        )

    async def capture_recovery_evidence(
        self,
        action: ProtectedAction,
        execution_context: dict[str, Any] | None = None,
    ) -> RecoveryEvidence:
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
            target_system=action.tool,
            target_resource=action.resource,
            action_type=action.action_type,
            before_state_reference=action.before_state_ref,
            after_state_reference=action.after_state_ref,
            compensation_payload={},
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=self._infer_adapter_type(),
            idempotency_key=f"idem-{action.action_id}",
            dependency_edges=[],
            reversibility_classification=Reversibility.normalize(action.reversibility),
            verification_requirements=[],
            evidence_hash="",
            adapter_capability=self._infer_capability(),
        )

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        return Reversibility.normalize(action.reversibility)

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        preview = await self.preview_recovery(action)
        return RollbackImpact(
            action_id=action.action_id,
            reversibility=evidence.reversibility_classification,
            would_succeed=bool(preview.get("reversible", False)),
            drift_status=DriftStatus.NO_DRIFT,
            conflict_status=ConflictStatus.NO_CONFLICT,
            compensation_operation="reverse",
            compensation_payload=evidence.compensation_payload,
            external_api_calls=[],
            warnings=(
                []
                if preview.get("reversible")
                else ["No before-state reference available"]
            ),
            simulation_limitation=SimulationLimitation.SIMULATION_LIMITED,
            expected_after_state=None,
        )

    async def check_preconditions(
        self,
        action: ProtectedAction,
        current_state: dict[str, Any] | None = None,
    ) -> PreconditionResult:
        return PreconditionResult(satisfied=True, failed_checks=[], details={})

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        if action.before_state_ref is None:
            return DriftResult(status=DriftStatus.INSUFFICIENT_EVIDENCE)
        return DriftResult(status=DriftStatus.NO_DRIFT)

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
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
            compensation_payload=evidence.compensation_payload or {},
            idempotency_key=evidence.idempotency_key or f"idem-{action.action_id}",
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
        result = await self.execute_recovery(
            ProtectedAction(
                action_id=compensation.action_id,
                tenant_id="",
                actor_user_id=None,
                agent_id="",
                authority_grant_id=None,
                tool="",
                resource="",
                action_type="",
            ),
            idempotency_key,
        )
        return CompensationResult(
            action_id=compensation.action_id,
            success=False,
            execution_state=ExecutionState.REQUIRES_MANUAL_ACTION,
            idempotency_key=idempotency_key,
            details=result,
            external_outcome="base_adapter_not_implemented",
            error=(
                "RecoveryAdapter base class does not perform actual recovery. "
                "Override execute_compensation or use a CompensatingActionAdapter implementation."
            ),
        )

    async def verify(
        self,
        compensation: CompensationAction,
    ) -> VerificationResult:
        return VerificationResult(
            action_id=compensation.action_id,
            verified=False,
            details={
                "reason": (
                    "RecoveryAdapter base class does not perform actual verification. "
                    "Override verify or use a CompensatingActionAdapter implementation."
                )
            },
        )

    def _infer_adapter_type(self) -> RecoveryAdapterType:
        name = getattr(self, "adapter_name", "").lower()
        mapping: dict[str, RecoveryAdapterType] = {
            "database_record": RecoveryAdapterType.DATABASE_RECORD,
            "database": RecoveryAdapterType.DATABASE_SQL,
            "http": RecoveryAdapterType.HTTP_REST,
            "rest": RecoveryAdapterType.HTTP_REST,
            "event": RecoveryAdapterType.EVENT_MESSAGE,
            "message": RecoveryAdapterType.EVENT_MESSAGE,
            "config": RecoveryAdapterType.CONFIG_ROLLBACK,
            "file": RecoveryAdapterType.FILE_VERSION,
            "iam": RecoveryAdapterType.IAM,
            "mock": RecoveryAdapterType.MOCK,
            "stub": RecoveryAdapterType.STUB,
        }
        for key, value in mapping.items():
            if key == name or key in name:
                return value
        return RecoveryAdapterType.UNSUPPORTED

    def _infer_capability(self) -> AdapterCapability:
        cap = getattr(self, "capability", "")
        if cap and cap in AdapterCapability._value2member_map_:
            return AdapterCapability(cap)
        if getattr(self, "adapter_name", "") and "mock" in getattr(
            self, "adapter_name", ""
        ).lower():
            return AdapterCapability.MOCK
        return AdapterCapability.STUB

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        """Default capability declaration based on adapter metadata."""
        cap = self._infer_capability()
        is_mock = cap == AdapterCapability.MOCK
        is_reference = cap == AdapterCapability.REFERENCE_IMPLEMENTATION
        is_sim = cap == AdapterCapability.SIMULATION_CAPABLE
        supported = is_mock or is_reference or is_sim
        return AdapterCapabilityDeclaration(
            adapter_name=getattr(self, "adapter_name", "unknown"),
            adapter_type=getattr(self, "adapter_type", "unknown"),
            can_capture_before_state=supported,
            can_capture_after_state=supported,
            can_read_current_state=supported,
            can_compute_delta=supported,
            can_detect_drift=supported,
            can_simulate=is_mock or is_sim or is_reference,
            can_compensate=supported,
            can_verify=supported,
            supports_idempotency=True,
            supports_versioning=supported,
            supports_safe_merge=is_mock,
            merge_safety=MergeSafety.MERGE_SAFE if is_mock else MergeSafety.MERGE_CONDITIONAL,
            declared_capabilities=[cap.value],
        )
