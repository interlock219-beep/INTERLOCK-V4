"""Interlock V5 — environment recovery adapter tests.

Covers the adapter contract, evidence capture (with redaction), restore of
set/unset variables, drift/conflict semantics required by the distributed
orchestrator, idempotency, tenant isolation, variable-name injection guards,
and deny-by-default allowed prefixes.
"""

from __future__ import annotations

import hashlib

import pytest

from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import (
    CompensationAction,
    ConflictStatus,
    DriftStatus,
    ExecutionState,
    RecoveryAdapterType,
    Reversibility,
)
from app.domain.services.recovery_adapter_registry import RecoveryAdapterRegistry
from app.infrastructure.recovery.environment_recovery_adapter import (
    EnvironmentRecoveryAdapter,
)


def _action(**overrides) -> ProtectedAction:
    base = {
        "action_id": "act-env-1",
        "tenant_id": "tenant-1",
        "actor_user_id": None,
        "agent_id": "agent-1",
        "authority_grant_id": None,
        "tool": "environment",
        "resource": "env:V5_TEST_VAR",
        "action_type": "set_env",
    }
    base.update(overrides)
    return ProtectedAction(**base)


def _rebuild(comp: CompensationAction, payload: dict) -> CompensationAction:
    return CompensationAction(
        action_id=comp.action_id,
        incident_action_id=comp.incident_action_id,
        compensation_type=comp.compensation_type,
        compensation_payload=payload,
        idempotency_key=comp.idempotency_key,
        target_system=comp.target_system,
        target_resource=comp.target_resource,
        execution_order=comp.execution_order,
        reversibility=comp.reversibility,
        drift_status=comp.drift_status,
        conflict_status=comp.conflict_status,
        verification_requirements=comp.verification_requirements,
        dependency_edges=comp.dependency_edges,
    )


async def test_contract_valid_and_declaration_truthful():
    validation = RecoveryAdapterRegistry.validate_contract(EnvironmentRecoveryAdapter())
    assert validation.ok is True

    declaration = await EnvironmentRecoveryAdapter().declare_capabilities()
    assert declaration.adapter_name == "environment_recovery"
    assert declaration.can_compensate is True
    assert declaration.can_detect_drift is True
    assert declaration.supports_idempotency is True
    # Truthful: this adapter does no versioning or safe merge.
    assert declaration.supports_versioning is False
    assert declaration.supports_safe_merge is False


async def test_can_recover_resource_scoping():
    adapter = EnvironmentRecoveryAdapter(environ={})
    assert await adapter.can_recover(_action()) == "automatically_reversible"

    non_env = _action(
        tool="database",
        resource="db:public.users",
        action_type="query",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    assert await adapter.can_recover(non_env) == "unsupported"

    irreversible = _action(reversibility=Reversibility.IRREVERSIBLE)
    assert await adapter.can_recover(irreversible) == "irreversible"


async def test_capture_and_restore_set_value():
    environ: dict[str, str] = {"V5_TEST_VAR": "after-action"}
    adapter = EnvironmentRecoveryAdapter(environ=environ)
    action = _action(before_state_ref="env:V5_TEST_VAR:pre")

    evidence = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "old-secret"}
    )
    assert evidence.recovery_adapter_type == RecoveryAdapterType.ENVIRONMENT
    assert evidence.target_system == "process_environment"
    assert evidence.compensation_payload["before_value"] == "old-secret"
    assert evidence.compensation_payload["before_value_present"] is True
    # The state reference is a hash reference, never the raw value.
    assert "old-secret" not in evidence.before_state_reference
    assert evidence.evidence_hash
    assert evidence.reversibility_classification == Reversibility.AUTOMATICALLY_REVERSIBLE

    impact = await adapter.simulate(action, evidence)
    assert impact.would_succeed is True
    # Simulation's expected after-state carries hashes only.
    assert "old-secret" not in str(impact.expected_after_state)

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is True
    assert result.execution_state == ExecutionState.SUCCEEDED
    assert environ["V5_TEST_VAR"] == "old-secret"
    # Externally visible details are hash-only.
    assert "old-secret" not in str(result.details)

    verification = await adapter.verify(comp)
    assert verification.verified is True


async def test_capture_and_restore_unset_value():
    environ: dict[str, str] = {"V5_TEST_VAR": "present"}
    adapter = EnvironmentRecoveryAdapter(environ=environ)
    action = _action(action_type="set_env", before_state_ref="env:V5_TEST_VAR:unset-before")

    evidence = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": None}
    )
    assert evidence.compensation_payload["before_value_present"] is True
    assert evidence.compensation_payload["before_value"] is None

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is True
    assert "V5_TEST_VAR" not in environ
    assert result.details["restored_to"] == "unset"

    verification = await adapter.verify(comp)
    assert verification.verified is True


async def test_no_before_evidence_fails_closed_to_manual():
    environ: dict[str, str] = {"V5_TEST_VAR": "changed"}
    adapter = EnvironmentRecoveryAdapter(environ=environ)
    action = _action()  # no before ref, no snapshot, no execution context

    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.compensation_payload["before_value_present"] is False
    assert evidence.reversibility_classification == Reversibility.CONDITIONALLY_REVERSIBLE

    impact = await adapter.simulate(action, evidence)
    assert impact.would_succeed is False

    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is False
    assert result.execution_state == ExecutionState.REQUIRES_MANUAL_ACTION
    assert "never captured" in (result.error or "")

    verification = await adapter.verify(comp)
    assert verification.verified is False


async def test_idempotency_key_mismatch_blocks():
    adapter = EnvironmentRecoveryAdapter(environ={"V5_TEST_VAR": "x"})
    action = _action(before_state_ref="pre")
    evidence = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "old"}
    )
    comp = await adapter.generate_compensation(action, evidence)

    result = await adapter.execute_compensation(comp, "some-other-key")
    assert result.success is False
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
    assert "Idempotency key mismatch" in (result.error or "")


async def test_missing_tenant_context_blocks_execution():
    adapter = EnvironmentRecoveryAdapter(environ={"V5_TEST_VAR": "x"})
    action = _action(before_state_ref="pre")
    evidence = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "old"}
    )
    comp = await adapter.generate_compensation(action, evidence)

    payload = dict(comp.compensation_payload)
    payload.pop("_tenant_id", None)
    unauthorized = _rebuild(comp, payload)

    result = await adapter.execute_compensation(unauthorized, unauthorized.idempotency_key)
    assert result.success is False
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
    assert "Authorization denied" in (result.error or "")


async def test_tenant_isolation_rejects_placeholder_tenant():
    adapter = EnvironmentRecoveryAdapter(environ={"V5_TEST_VAR": "x"})
    action = _action(tenant_id="null")
    with pytest.raises(ValueError, match="Tenant isolation"):
        await adapter.capture_recovery_evidence(
            action, execution_context={"before_value": "old"}
        )


async def test_variable_name_injection_rejected():
    adapter = EnvironmentRecoveryAdapter(environ={})
    with pytest.raises(ValueError, match="Invalid environment variable name"):
        EnvironmentRecoveryAdapter.extract_var_name("env:BAD=NAME")
    with pytest.raises(ValueError, match="Invalid environment variable name"):
        EnvironmentRecoveryAdapter.extract_var_name("env:BAD\nNAME")

    action = _action(resource="env:BAD=NAME")
    with pytest.raises(ValueError):
        await adapter.capture_recovery_evidence(action)

    precondition = await adapter.check_preconditions(action)
    assert precondition.satisfied is False
    assert "invalid_resource" in precondition.failed_checks


async def test_allowed_prefixes_deny_by_default():
    environ: dict[str, str] = {"SECRET_TOKEN": "s", "APP_MODE": "a"}
    adapter = EnvironmentRecoveryAdapter(environ=environ, allowed_prefixes=("APP_",))

    ok = _action(resource="env:APP_MODE")
    precondition = await adapter.check_preconditions(ok)
    assert precondition.satisfied is True
    evidence = await adapter.capture_recovery_evidence(
        ok, execution_context={"before_value": "a"}
    )
    assert evidence.compensation_payload["var"] == "APP_MODE"

    denied = _action(resource="env:SECRET_TOKEN")
    precondition = await adapter.check_preconditions(denied)
    assert precondition.satisfied is False
    assert "outside_allowed_prefixes" in precondition.failed_checks
    with pytest.raises(ValueError, match="allowed_prefixes"):
        await adapter.capture_recovery_evidence(
            denied, execution_context={"before_value": "s"}
        )


async def test_drift_semantics_match_orchestrator_contract():
    adapter = EnvironmentRecoveryAdapter(environ={"V5_TEST_VAR": "live"})

    # Evidence with before + after recorded.
    action = _action(before_state_ref="pre")
    with_after = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "old", "after_value": "new"}
    )
    # Evidence with before only (no after-state recorded).
    without_after = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "old"}
    )

    # At before-state: no drift.
    result = await adapter.detect_drift(
        action, with_after, current_state={"value": "old"}
    )
    assert result.status == DriftStatus.NO_DRIFT

    # At recorded after-state (post-action): no drift — compensation proceeds.
    result = await adapter.detect_drift(
        action, with_after, current_state={"value": "new"}
    )
    assert result.status == DriftStatus.NO_DRIFT

    # A third state with after recorded: external drift.
    result = await adapter.detect_drift(
        action, with_after, current_state={"value": "tampered"}
    )
    assert result.status == DriftStatus.DRIFT_DETECTED

    # No after recorded, state differs from before: insufficient evidence
    # (cannot distinguish the action's own effect from external drift).
    result = await adapter.detect_drift(
        action, without_after, current_state={"value": "changed"}
    )
    assert result.status == DriftStatus.INSUFFICIENT_EVIDENCE

    # No after recorded, state equals before: no drift.
    result = await adapter.detect_drift(
        action, without_after, current_state={"value": "old"}
    )
    assert result.status == DriftStatus.NO_DRIFT

    # No before evidence at all: insufficient evidence.
    no_before = await adapter.capture_recovery_evidence(_action())
    result = await adapter.detect_drift(_action(), no_before)
    assert result.status == DriftStatus.INSUFFICIENT_EVIDENCE


async def test_conflict_semantics_match_orchestrator_contract():
    adapter = EnvironmentRecoveryAdapter(environ={"V5_TEST_VAR": "live"})
    action = _action(before_state_ref="pre")

    without_after = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "old"}
    )
    with_after = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "old", "after_value": "new"}
    )

    # Without a recorded after-state there is nothing to conflict against.
    result = await adapter.check_conflicts(
        action, without_after, current_state={"value": "anything"}
    )
    assert result.status == ConflictStatus.NO_CONFLICT

    # With after recorded: matching after or before is fine.
    result = await adapter.check_conflicts(
        action, with_after, current_state={"value": "new"}
    )
    assert result.status == ConflictStatus.NO_CONFLICT
    result = await adapter.check_conflicts(
        action, with_after, current_state={"value": "old"}
    )
    assert result.status == ConflictStatus.NO_CONFLICT

    # A third state is a concurrent mutation.
    result = await adapter.check_conflicts(
        action, with_after, current_state={"value": "other-writer"}
    )
    assert result.status == ConflictStatus.CONCURRENT_MUTATION


async def test_irreversible_compensation_blocked():
    adapter = EnvironmentRecoveryAdapter(environ={"V5_TEST_VAR": "x"})
    action = _action(reversibility=Reversibility.IRREVERSIBLE, before_state_ref="pre")
    evidence = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "old"}
    )
    assert evidence.reversibility_classification == Reversibility.IRREVERSIBLE

    comp = await adapter.generate_compensation(action, evidence)
    assert comp.reversibility == Reversibility.IRREVERSIBLE
    result = await adapter.execute_compensation(comp, evidence.idempotency_key)
    assert result.success is False
    assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
    assert "irreversible" in (result.error or "")


async def test_legacy_preview_and_execute_recovery():
    environ: dict[str, str] = {"V5_TEST_VAR": "post"}
    adapter = EnvironmentRecoveryAdapter(environ=environ)

    action = _action(before_state_ref="pre", before_state_snapshot={"value": "pre-value"})
    preview = await adapter.preview_recovery(action)
    assert preview["adapter"] == "environment_recovery"
    assert preview["reversible"] is True

    result = await adapter.execute_recovery(action, approved_by="user-1")
    assert result["status"] == "restored"
    assert environ["V5_TEST_VAR"] == "pre-value"
    assert "pre-value" not in str(result.get("restored_value_sha256"))
    expected = hashlib.sha256(b"pre-value").hexdigest()
    assert result["restored_value_sha256"] == expected

    # Without any before-state the legacy path fails instead of guessing.
    no_snapshot = _action()
    result = await adapter.execute_recovery(no_snapshot, approved_by="user-1")
    assert result["status"] == "failed"


async def test_evidence_hash_changes_with_captured_state():
    adapter = EnvironmentRecoveryAdapter(environ={})
    action = _action(before_state_ref="pre")

    first = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "one"}
    )
    second = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "two"}
    )
    assert first.evidence_hash != second.evidence_hash
    assert "one" not in first.evidence_hash
