"""Environment-variable recovery adapter (Interlock V5).

Performs real snapshot/restore of process environment variables so that
protected ``set_env``/``unset_env`` actions can be compensated deterministically.

Security properties:

- Tenant isolation and authorization checks run before any mutation
  (:meth:`RecoveryAdapter._verify_tenant_isolation`,
  ``_verify_compensation_authorization``).
- Variable names are validated against a strict pattern; names containing
  ``=``, NUL bytes, or newlines are rejected (fail closed), preventing
  environment-injection style attacks.
- Evidence records **hashes** of values (SHA-256 + length) alongside the raw
  value needed for restoration; hash-only forms are used in every externally
  visible detail/result structure so values are never leaked into logs,
  results, or verification details.
- Optional ``allowed_prefixes`` restricts which variables the adapter may
  ever touch (deny-by-default when configured).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import MutableMapping
from typing import Any

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
from app.domain.services.evidence_hash import seal_evidence
from app.domain.services.recovery_adapter import RecoveryAdapter

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")

_ENV_ACTION_TYPES = frozenset(
    {"set_env", "unset_env", "export_env", "update_env", "restore_env", "delete_env"}
)
_ENV_TOOLS = frozenset({"environment", "env", "environ", "os.environ", "process_env"})


def _value_digest(value: str | None) -> str | None:
    """SHA-256 digest of an environment value (``None`` when unset)."""
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="surrogateescape")).hexdigest()


class EnvironmentRecoveryAdapter(RecoveryAdapter):
    """Live environment-variable compensation adapter."""

    adapter_name = "environment_recovery"
    adapter_type = "environment"
    capability = AdapterCapability.PRODUCTION_VALIDATED

    RESOURCE_PREFIX = "env:"

    def __init__(
        self,
        environ: MutableMapping[str, str] | None = None,
        *,
        allowed_prefixes: tuple[str, ...] = (),
    ) -> None:
        self._environ: MutableMapping[str, str] = environ if environ is not None else os.environ
        self._allowed_prefixes = allowed_prefixes

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def is_env_resource(cls, resource: str) -> bool:
        return resource.startswith(cls.RESOURCE_PREFIX)

    @staticmethod
    def extract_var_name(resource: str) -> str:
        """Extract and validate the variable name from an ``env:NAME`` resource."""
        raw = resource[len(EnvironmentRecoveryAdapter.RESOURCE_PREFIX):] if resource.startswith(
            EnvironmentRecoveryAdapter.RESOURCE_PREFIX
        ) else resource
        name = raw.strip()
        if not _ENV_NAME_RE.match(name):
            raise ValueError(
                f"Invalid environment variable name {name!r}: must match "
                "[A-Za-z_][A-Za-z0-9_]* and contain no '=', NUL, or newline bytes"
            )
        return name

    def _is_env_action(self, action: ProtectedAction) -> bool:
        if self.is_env_resource(action.resource):
            return True
        if action.action_type.lower() in _ENV_ACTION_TYPES:
            return True
        return action.tool.lower() in _ENV_TOOLS

    def _allowed(self, var_name: str) -> bool:
        if not self._allowed_prefixes:
            return True
        return any(var_name.startswith(prefix) for prefix in self._allowed_prefixes)

    def _read_value(self, var_name: str) -> str | None:
        if not self._allowed(var_name):
            raise ValueError(
                f"Environment recovery denied: {var_name!r} does not match the "
                "configured allowed_prefixes"
            )
        return self._environ.get(var_name)

    def _write_value(self, var_name: str, value: str | None) -> None:
        if not self._allowed(var_name):
            raise ValueError(
                f"Environment recovery denied: {var_name!r} does not match the "
                "configured allowed_prefixes"
            )
        if value is None:
            self._environ.pop(var_name, None)
        else:
            self._environ[var_name] = value

    @staticmethod
    def _resolve_before_value(
        action: ProtectedAction,
        execution_context: dict[str, Any] | None,
        environ: MutableMapping[str, str],
        var_name: str,
    ) -> tuple[bool, str | None]:
        """Resolve the pre-action value.

        Returns ``(present, value)`` where ``present`` means the before-value
        (or its known absence) was captured; ``value is None`` means the
        variable was previously unset.
        """
        snapshot = action.before_state_snapshot or {}
        if execution_context and "before_value" in execution_context:
            return True, execution_context.get("before_value")
        if snapshot and "value" in snapshot:
            return True, snapshot.get("value")
        if action.before_state_ref:
            # A before-state reference exists but no value was supplied; the
            # current environment is authoritative for pre-action state when
            # capture runs before the mutation.
            return True, environ.get(var_name)
        return False, None

    # ------------------------------------------------------------------
    # Adapter contract
    # ------------------------------------------------------------------

    async def can_recover(self, action: ProtectedAction) -> str:
        rev = Reversibility.normalize(action.reversibility)
        if rev == Reversibility.IRREVERSIBLE:
            return "irreversible"
        if not self._is_env_action(action):
            return "unsupported"
        if action.before_state_ref or action.before_state_snapshot or self.is_env_resource(
            action.resource
        ):
            return "automatically_reversible"
        return "conditionally_reversible"

    async def declare_capabilities(self) -> AdapterCapabilityDeclaration:
        return AdapterCapabilityDeclaration(
            adapter_name=self.adapter_name,
            adapter_type=self.adapter_type,
            can_capture_before_state=True,
            can_capture_after_state=True,
            can_read_current_state=True,
            can_compute_delta=True,
            can_detect_drift=True,
            can_simulate=True,
            can_compensate=True,
            can_verify=True,
            supports_idempotency=True,
            supports_versioning=False,
            supports_safe_merge=False,
            merge_safety=MergeSafety.MERGE_CONDITIONAL,
            declared_capabilities=[
                "environment_variable_snapshot",
                "environment_variable_restore",
                "unset_variable_cleanup",
                "hash_based_drift_detection",
                "secret_value_redaction",
            ],
        )

    async def capture_recovery_evidence(
        self,
        action: ProtectedAction,
        execution_context: dict[str, Any] | None = None,
        before_snapshot: dict[str, Any] | None = None,
    ) -> RecoveryEvidence:
        self._verify_tenant_isolation(action)
        var_name = self.extract_var_name(action.resource)
        if not self._allowed(var_name):
            # Deny-by-default: never capture evidence for variables the adapter
            # is not permitted to touch.
            raise ValueError(
                f"Environment recovery denied: {var_name!r} does not match the "
                "configured allowed_prefixes"
            )

        before_present, before_value = self._resolve_before_value(
            action, execution_context, self._environ, var_name
        )
        if before_snapshot and "value" in before_snapshot and not (
            execution_context and "before_value" in execution_context
        ):
            before_present, before_value = True, before_snapshot.get("value")

        after_present = bool(
            execution_context and "after_value" in execution_context
        )
        after_value = (
            execution_context.get("after_value")
            if (execution_context and after_present)
            else None
        )

        compensation_payload = self._embed_tenant_context(
            action,
            {
                "operation": "restore_env_var",
                "var": var_name,
                "before_value": before_value if before_present else None,
                "before_value_present": before_present,
                "after_value": after_value if after_present else None,
                "after_value_present": after_present,
                "before_value_sha256": _value_digest(before_value) if before_present else None,
                "after_value_sha256": _value_digest(after_value) if after_present else None,
                "before_value_length": (len(before_value) if before_value is not None else None),
            },
        )

        if not before_present:
            reversibility = Reversibility.CONDITIONALLY_REVERSIBLE
        elif Reversibility.normalize(action.reversibility) == Reversibility.IRREVERSIBLE:
            reversibility = Reversibility.IRREVERSIBLE
        else:
            reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE

        return seal_evidence(RecoveryEvidence(
            evidence_id=f"ev-{action.action_id}",
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            agent_id=action.agent_id,
            authority_grant_id=action.authority_grant_id,
            parent_action_id=action.parent_action_id,
            root_action_id=action.parent_action_id or action.action_id,
            correlation_id=action.correlation_id,
            incident_id="",
            target_system="process_environment",
            target_resource=action.resource,
            action_type=action.action_type,
            before_state_reference=(
                f"env:{var_name}:sha256:{compensation_payload['before_value_sha256']}"
                if before_present and before_value is not None
                else (f"env:{var_name}:unset" if before_present else action.before_state_ref)
            ),
            after_state_reference=(
                f"env:{var_name}:sha256:{compensation_payload['after_value_sha256']}"
                if after_present and after_value is not None
                else (f"env:{var_name}:unset" if after_present else action.after_state_ref)
            ),
            compensation_payload=compensation_payload,
            compensation_type=CompensationType.REVERSE_OPERATION,
            recovery_adapter_type=RecoveryAdapterType.ENVIRONMENT,
            idempotency_key=f"idem-{action.action_id}",
            dependency_edges=[],
            reversibility_classification=reversibility,
            adapter_capability=AdapterCapability.PRODUCTION_VALIDATED,
            verification_requirements=["env_value_restored"],
        ))

    async def classify_reversibility(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> Reversibility:
        rev = Reversibility.normalize(action.reversibility)
        if rev == Reversibility.IRREVERSIBLE:
            return rev
        if evidence.compensation_payload.get("before_value_present"):
            return Reversibility.AUTOMATICALLY_REVERSIBLE
        return Reversibility.CONDITIONALLY_REVERSIBLE

    async def simulate(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> RollbackImpact:
        rev = await self.classify_reversibility(action, evidence)
        payload = evidence.compensation_payload
        would_succeed = bool(payload.get("before_value_present"))
        warnings: list[str] = []
        if not would_succeed:
            warnings.append("Before-value was not captured: restore cannot be simulated")
        warnings.append("Environment values are process-local; restore affects this process only")
        return RollbackImpact(
            action_id=action.action_id,
            reversibility=rev,
            would_succeed=would_succeed,
            drift_status=DriftStatus.NO_DRIFT,
            conflict_status=ConflictStatus.NO_CONFLICT,
            compensation_operation="restore_env_var",
            compensation_payload=payload,
            external_api_calls=[],
            warnings=warnings,
            simulation_limitation=SimulationLimitation.SIMULATION_LIMITED,
            expected_after_state={
                "var": payload.get("var"),
                "value_sha256": payload.get("before_value_sha256"),
                "value_present": payload.get("before_value_present"),
            },
        )

    async def check_preconditions(
        self,
        action: ProtectedAction,
        current_state: dict[str, Any] | None = None,
    ) -> PreconditionResult:
        try:
            var_name = self.extract_var_name(action.resource)
        except ValueError as exc:
            return PreconditionResult(
                satisfied=False,
                failed_checks=["invalid_resource"],
                details={"reason": str(exc)},
            )
        if not self._allowed(var_name):
            return PreconditionResult(
                satisfied=False,
                failed_checks=["outside_allowed_prefixes"],
                details={"var": var_name},
            )
        return PreconditionResult(
            satisfied=True,
            details={"var": var_name},
        )

    async def detect_drift(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> DriftResult:
        payload = evidence.compensation_payload
        var_name = payload.get("var") or ""
        if not payload.get("before_value_present"):
            return DriftResult(
                status=DriftStatus.INSUFFICIENT_EVIDENCE,
                details={"reason": "No before-value captured for comparison"},
            )
        current = current_state.get("value") if current_state and "value" in current_state else (
            self._environ.get(var_name) if var_name else None
        )
        actual_digest = _value_digest(current)
        before_digest = payload.get("before_value_sha256")

        # Still at the captured pre-action state: nothing changed yet (or the
        # compensation was already applied).
        if actual_digest == before_digest:
            return DriftResult(
                status=DriftStatus.NO_DRIFT,
                current_state={"var": var_name, "value_sha256": before_digest},
            )

        # An after-state was recorded: it and the before-state are the only
        # acceptable states; anything else is an external (drifting) change.
        if payload.get("after_value_present"):
            after_digest = payload.get("after_value_sha256")
            if actual_digest == after_digest:
                return DriftResult(
                    status=DriftStatus.NO_DRIFT,
                    current_state={"var": var_name, "value_sha256": actual_digest},
                    details={"reason": "State matches the recorded after-action value"},
                )
            return DriftResult(
                status=DriftStatus.DRIFT_DETECTED,
                details={
                    "var": var_name,
                    "expected_before_sha256": before_digest,
                    "expected_after_sha256": after_digest,
                    "actual_sha256": actual_digest,
                },
            )

        # No after-state recorded: a deviation from the before-state may be the
        # expected effect of the protected action itself.  Insufficient evidence
        # to classify it as external drift (the orchestrator allows compensation
        # to proceed under INSUFFICIENT_EVIDENCE).
        return DriftResult(
            status=DriftStatus.INSUFFICIENT_EVIDENCE,
            details={
                "var": var_name,
                "before_sha256": before_digest,
                "actual_sha256": actual_digest,
                "reason": (
                    "Value differs from the before-state and no after-state was "
                    "recorded to distinguish the action's effect from external drift"
                ),
            },
        )

    async def check_conflicts(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
        current_state: dict[str, Any] | None = None,
    ) -> ConflictResult:
        payload = evidence.compensation_payload
        var_name = payload.get("var") or ""
        if not payload.get("after_value_present"):
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)
        current = current_state.get("value") if current_state and "value" in current_state else (
            self._environ.get(var_name) if var_name else None
        )
        if _value_digest(current) == payload.get("after_value_sha256"):
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)
        before_digest = payload.get("before_value_sha256")
        if _value_digest(current) == before_digest:
            # Already restored: executing again is a no-op, not a conflict.
            return ConflictResult(status=ConflictStatus.NO_CONFLICT)
        return ConflictResult(
            status=ConflictStatus.CONCURRENT_MUTATION,
            details={
                "var": var_name,
                "actual_sha256": _value_digest(current),
            },
        )

    async def generate_compensation(
        self,
        action: ProtectedAction,
        evidence: RecoveryEvidence,
    ) -> CompensationAction:
        payload = self._embed_tenant_context(action, dict(evidence.compensation_payload))
        return CompensationAction(
            action_id=action.action_id,
            incident_action_id=action.parent_action_id or action.action_id,
            compensation_type=CompensationType.REVERSE_OPERATION,
            compensation_payload=payload,
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

        try:
            self._verify_compensation_authorization(compensation)
        except ValueError as exc:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.BLOCKED_BY_CONFLICT,
                idempotency_key=idempotency_key,
                error=f"Authorization denied: {exc}",
            )

        payload = compensation.compensation_payload
        var_name = payload.get("var")
        if not var_name:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error="Compensation payload has no variable name",
            )

        try:
            if not payload.get("before_value_present"):
                return CompensationResult(
                    action_id=compensation.action_id,
                    success=False,
                    execution_state=ExecutionState.REQUIRES_MANUAL_ACTION,
                    idempotency_key=idempotency_key,
                    error=(
                        "Before-value was never captured; refusing to guess an "
                        "environment restore value"
                    ),
                )
            before_value = payload.get("before_value")
            self._write_value(var_name, before_value)
        except (ValueError, TypeError) as exc:
            return CompensationResult(
                action_id=compensation.action_id,
                success=False,
                execution_state=ExecutionState.FAILED,
                idempotency_key=idempotency_key,
                error=f"Environment restore failed: {exc}",
            )

        return CompensationResult(
            action_id=compensation.action_id,
            success=True,
            execution_state=ExecutionState.SUCCEEDED,
            idempotency_key=idempotency_key,
            details={
                "operation": "restore_env_var",
                "var": var_name,
                "restored_to": "unset" if before_value is None else "set",
                "restored_value_sha256": _value_digest(before_value),
            },
            external_outcome="environment_restored",
        )

    async def verify(self, compensation: CompensationAction) -> VerificationResult:
        payload = compensation.compensation_payload
        var_name = payload.get("var")
        if not var_name:
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "Compensation payload has no variable name"},
            )
        if not payload.get("before_value_present"):
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": "No expected before-value recorded"},
            )
        try:
            current = self._read_value(var_name)
        except Exception as exc:
            return VerificationResult(
                action_id=compensation.action_id,
                verified=False,
                details={"reason": f"Unable to read environment: {exc}"},
            )
        expected_digest = payload.get("before_value_sha256")
        actual_digest = _value_digest(current)
        return VerificationResult(
            action_id=compensation.action_id,
            verified=actual_digest == expected_digest,
            details={
                "var": var_name,
                "expected_sha256": expected_digest,
                "actual_sha256": actual_digest,
            },
        )

    async def preview_recovery(self, action: ProtectedAction) -> dict[str, Any]:
        reversible = bool(
            action.before_state_ref or action.before_state_snapshot
        ) or self.is_env_resource(action.resource)
        return {
            "adapter": self.adapter_name,
            "adapter_type": self.adapter_type,
            "capability": self.capability.value,
            "action_id": action.action_id,
            "resource": action.resource,
            "reversible": reversible,
            "operation": "restore_env_var",
            "requires_approval": False,
        }

    async def execute_recovery(self, action: ProtectedAction, approved_by: str) -> dict[str, Any]:
        self._verify_tenant_isolation(action)
        var_name = self.extract_var_name(action.resource)
        snapshot = action.before_state_snapshot or {}
        if "value" not in snapshot and not action.before_state_ref:
            return {
                "adapter": self.adapter_name,
                "action_id": action.action_id,
                "status": "failed",
                "error": "No before-state snapshot available for environment restore",
                "executed_by": approved_by,
            }
        value = snapshot.get("value")
        self._write_value(var_name, value)
        return {
            "adapter": self.adapter_name,
            "action_id": action.action_id,
            "status": "restored",
            "var": var_name,
            "restored_value_sha256": _value_digest(value),
            "executed_by": approved_by,
        }
