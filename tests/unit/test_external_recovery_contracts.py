from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from app.domain.entities.surgical_recovery_types import (
    CompensationType,
    Reversibility,
)
from app.domain.services.external_recovery_contracts import (
    ExternalCapabilityContract,
    ExternalCapabilityDomain,
    ExternalCapabilityRegistry,
    ExternalCapabilityStatus,
    ExternalCompensationDefinition,
    ExternalDependency,
    ExternalDependencyStatus,
    ExternalEvidenceEnvelope,
    ExternalRecoveryMode,
    ExternalRiskLevel,
    ExternalVerificationCheck,
    ExternalVerificationResult,
)

def _make_dependency(
    name: str = "dep",
    kind: str = "api",
    required: bool = True,
    status: ExternalDependencyStatus | str = ExternalDependencyStatus.AVAILABLE,
    reason: str = "ok",
    **kwargs: object,
) -> ExternalDependency:
    defaults: dict[str, object] = {
        "credentials_required": True,
        "endpoint_required": True,
        "network_required": True,
        "adapter_required": True,
        "metadata": {"extra": "value"},
    }
    defaults.update(kwargs)
    return ExternalDependency(
        name=name,
        kind=kind,
        required=required,
        status=status,
        reason=reason,
        **defaults,
    )

def _make_contract(
    capability_id: int = 1,
    dependencies: tuple[ExternalDependency, ...] = (),
    **overrides: object,
) -> ExternalCapabilityContract:
    defaults: dict[str, object] = {
        "capability_id": capability_id,
        "name": "cloud-storage",
        "domain": ExternalCapabilityDomain.CLOUD,
        "description": "Cloud storage capability",
        "dependencies": dependencies,
        "reversibility": Reversibility.MANUALLY_RECOVERABLE,
        "compensation_operations": ("revert",),
        "evidence_requirements": ("evidence",),
        "verification_checks": ("check",),
        "risk_level": ExternalRiskLevel.HIGH,
        "status": ExternalCapabilityStatus.BLOCKED,
        "metadata": {"key": "value"},
    }
    defaults.update(overrides)
    return ExternalCapabilityContract(**defaults)

def _make_compensation(
    capability_id: int = 1,
    operation: str = "revert",
    **overrides: object,
) -> ExternalCompensationDefinition:
    defaults: dict[str, object] = {
        "capability_id": capability_id,
        "operation": operation,
        "target_system": "storage",
        "target_resource": "bucket/obj",
        "payload_schema": {"field": "str"},
        "compensation_type": CompensationType.REVERSE_OPERATION,
        "idempotency_required": True,
        "approval_required": True,
        "reversible": Reversibility.MANUALLY_RECOVERABLE,
        "status": ExternalCapabilityStatus.BLOCKED,
        "metadata": {"extra": "value"},
    }
    defaults.update(overrides)
    return ExternalCompensationDefinition(**defaults)

def test_external_capability_domain_values():
    assert ExternalCapabilityDomain.CLOUD.value == "cloud"
    assert ExternalCapabilityDomain.KUBERNETES.value == "kubernetes"
    assert (
        ExternalCapabilityDomain.KUBERNETES_CONTAINERS_WORKLOADS.value
        == "kubernetes"
    )
    assert ExternalCapabilityDomain.API_EXTERNAL.value == "api_external"
    assert ExternalCapabilityDomain.API.value == "api_external"
    assert ExternalCapabilityDomain.NETWORK.value == "network"
    assert (
        ExternalCapabilityDomain.IDENTITY_AUTHORITY.value
        == "identity_authority"
    )
    assert (
        ExternalCapabilityDomain.AGENT_SESSION_MEMORY.value
        == "agent_session_memory"
    )
    assert ExternalCapabilityDomain.TOOLS_MCP_A2A.value == "tools_mcp_a2a"
    assert (
        ExternalCapabilityDomain.EVENTS_STREAMS.value == "events_streams"
    )
    assert (
        ExternalCapabilityDomain.OBJECT_DATA_VECTOR.value
        == "object_data_vector"
    )
    assert (
        ExternalCapabilityDomain.BROWSER_COMPUTER_USE.value
        == "browser_computer_use"
    )
    assert (
        ExternalCapabilityDomain.FINANCIAL_HIGH_IMPACT.value
        == "financial_high_impact"
    )

def test_external_capability_domain_aliases_collide():
    assert (
        ExternalCapabilityDomain.KUBERNETES
        == ExternalCapabilityDomain.KUBERNETES_CONTAINERS_WORKLOADS
    )
    assert (
        ExternalCapabilityDomain.API == ExternalCapabilityDomain.API_EXTERNAL
    )

def test_external_dependency_status_values():
    assert ExternalDependencyStatus.AVAILABLE.value == "available"
    assert ExternalDependencyStatus.BLOCKED.value == "blocked"
    assert ExternalDependencyStatus.UNKNOWN.value == "unknown"
    assert ExternalDependencyStatus.DEGRADED.value == "degraded"

def test_external_capability_status_values():
    assert ExternalCapabilityStatus.BLOCKED.value == "blocked"
    assert ExternalCapabilityStatus.LOCAL_SAFE.value == "local_safe"
    assert (
        ExternalCapabilityStatus.SIMULATION_ONLY.value == "simulation_only"
    )
    assert (
        ExternalCapabilityStatus.PRODUCTION_VALIDATED.value
        == "production_validated"
    )
    assert (
        ExternalCapabilityStatus.REFERENCE_ONLY.value == "reference_only"
    )

# ---------------------------------------------------------------------------
# ExternalDependency
# ---------------------------------------------------------------------------


def test_external_dependency_post_init_normalizes_status_from_string():
    dependency = ExternalDependency(
        name="dep", kind="api", status="available"
    )
    assert dependency.status is ExternalDependencyStatus.AVAILABLE


def test_external_dependency_post_init_keeps_enum_status():
    dependency = ExternalDependency(
        name="dep", kind="api", status=ExternalDependencyStatus.DEGRADED
    )
    assert dependency.status is ExternalDependencyStatus.DEGRADED


def test_external_dependency_is_available_true():
    dependency = _make_dependency(status=ExternalDependencyStatus.AVAILABLE)
    assert dependency.is_available is True


def test_external_dependency_is_available_false_when_blocked():
    dependency = _make_dependency(status=ExternalDependencyStatus.BLOCKED)
    assert dependency.is_available is False


def test_external_dependency_is_available_false_when_unknown():
    dependency = _make_dependency(status=ExternalDependencyStatus.UNKNOWN)
    assert dependency.is_available is False


def test_external_dependency_is_blocked_true():
    dependency = _make_dependency(status=ExternalDependencyStatus.BLOCKED)
    assert dependency.is_blocked is True


def test_external_dependency_is_blocked_false_when_available():
    dependency = _make_dependency(status=ExternalDependencyStatus.AVAILABLE)
    assert dependency.is_blocked is False


def test_external_dependency_is_blocked_false_when_degraded():
    dependency = _make_dependency(status=ExternalDependencyStatus.DEGRADED)
    assert dependency.is_blocked is False


def test_external_dependency_to_dict_returns_all_fields():
    dependency = ExternalDependency(
        name="dep",
        kind="api",
        required=True,
        status="degraded",
        reason="slow",
        credentials_required=False,
        endpoint_required=True,
        network_required=False,
        adapter_required=True,
        metadata={"a": 1},
    )
    result = dependency.to_dict()
    assert result == {
        "name": "dep",
        "kind": "api",
        "required": True,
        "status": "degraded",
        "reason": "slow",
        "credentials_required": False,
        "endpoint_required": True,
        "network_required": False,
        "adapter_required": True,
        "metadata": {"a": 1},
    }


def test_external_dependency_to_dict_metadata_is_a_copy():
    dependency = _make_dependency(metadata={"a": 1})
    result = dependency.to_dict()
    result["metadata"]["a"] = 999
    assert dependency.metadata == {"a": 1}

# ---------------------------------------------------------------------------
# ExternalCompensationDefinition
# ---------------------------------------------------------------------------


def test_external_compensation_post_init_normalizes_reversibility_legacy():
    comp = _make_compensation(reversible="reversible")
    assert comp.reversible is Reversibility.AUTOMATICALLY_REVERSIBLE


def test_external_compensation_post_init_normalizes_reversibility_approval():
    comp = _make_compensation(reversible="reversible_with_approval")
    assert comp.reversible is Reversibility.CONDITIONALLY_REVERSIBLE


def test_external_compensation_post_init_normalizes_status_from_string():
    comp = _make_compensation(status="local_safe")
    assert comp.status is ExternalCapabilityStatus.LOCAL_SAFE


def test_external_compensation_post_init_keeps_enum_reversibility():
    comp = _make_compensation(reversible=Reversibility.IRREVERSIBLE)
    assert comp.reversible is Reversibility.IRREVERSIBLE


def test_external_compensation_post_init_keeps_enum_status():
    comp = _make_compensation(
        status=ExternalCapabilityStatus.PRODUCTION_VALIDATED
    )
    assert comp.status is ExternalCapabilityStatus.PRODUCTION_VALIDATED


def test_external_compensation_is_blocked_true():
    comp = _make_compensation(status=ExternalCapabilityStatus.BLOCKED)
    assert comp.is_blocked is True


def test_external_compensation_is_blocked_false_when_local_safe():
    comp = _make_compensation(status=ExternalCapabilityStatus.LOCAL_SAFE)
    assert comp.is_blocked is False


def test_external_compensation_to_dict_returns_all_fields():
    comp = ExternalCompensationDefinition(
        capability_id=42,
        operation="undo",
        target_system="storage",
        target_resource="bucket/obj",
        payload_schema={"field": "str"},
        compensation_type=CompensationType.COMPENSATING_EVENT,
        idempotency_required=False,
        approval_required=True,
        reversible="reversible",
        status="production_validated",
        metadata={"k": "v"},
    )
    result = comp.to_dict()
    assert result == {
        "capability_id": 42,
        "operation": "undo",
        "target_system": "storage",
        "target_resource": "bucket/obj",
        "payload_schema": {"field": "str"},
        "compensation_type": "compensating_event",
        "idempotency_required": False,
        "approval_required": True,
        "reversible": "automatically_reversible",
        "status": "production_validated",
        "metadata": {"k": "v"},
    }


def test_external_compensation_to_dict_copies_payload_schema_and_metadata():
    comp = _make_compensation(
        payload_schema={"a": 1}, metadata={"b": 2}
    )
    result = comp.to_dict()
    result["payload_schema"]["a"] = 999
    result["metadata"]["b"] = 999
    assert comp.payload_schema == {"a": 1}
    assert comp.metadata == {"b": 2}

# ---------------------------------------------------------------------------
# ExternalCapabilityContract
# ---------------------------------------------------------------------------


def test_contract_id_property_returns_capability_id():
    contract = _make_contract(capability_id=123)
    assert contract.id == 123


def test_contract_post_init_normalizes_domain_from_string():
    contract = _make_contract(domain="cloud")
    assert contract.domain is ExternalCapabilityDomain.CLOUD


def test_contract_post_init_normalizes_reversibility_legacy():
    contract = _make_contract(reversibility="reversible")
    assert contract.reversibility is Reversibility.AUTOMATICALLY_REVERSIBLE


def test_contract_post_init_normalizes_risk_level_from_string():
    contract = _make_contract(risk_level="low")
    assert contract.risk_level is ExternalRiskLevel.LOW


def test_contract_post_init_normalizes_status_from_string():
    contract = _make_contract(status="local_safe")
    assert contract.status is ExternalCapabilityStatus.LOCAL_SAFE


def test_contract_post_init_normalizes_dependencies_to_tuple():
    contract = _make_contract(
        dependencies=[_make_dependency(), _make_dependency(name="d2")]
    )
    assert isinstance(contract.dependencies, tuple)
    assert len(contract.dependencies) == 2


def test_contract_is_blocked_true():
    contract = _make_contract(status=ExternalCapabilityStatus.BLOCKED)
    assert contract.is_blocked is True


def test_contract_is_blocked_false_when_local_safe():
    contract = _make_contract(status=ExternalCapabilityStatus.LOCAL_SAFE)
    assert contract.is_blocked is False


def test_contract_is_local_safe_true_for_local_safe():
    contract = _make_contract(status=ExternalCapabilityStatus.LOCAL_SAFE)
    assert contract.is_local_safe is True


def test_contract_is_local_safe_true_for_simulation_only():
    contract = _make_contract(
        status=ExternalCapabilityStatus.SIMULATION_ONLY
    )
    assert contract.is_local_safe is True


def test_contract_is_local_safe_true_for_reference_only():
    contract = _make_contract(
        status=ExternalCapabilityStatus.REFERENCE_ONLY
    )
    assert contract.is_local_safe is True


def test_contract_is_local_safe_false_for_blocked():
    contract = _make_contract(status=ExternalCapabilityStatus.BLOCKED)
    assert contract.is_local_safe is False


def test_contract_is_local_safe_false_for_production_validated():
    contract = _make_contract(
        status=ExternalCapabilityStatus.PRODUCTION_VALIDATED
    )
    assert contract.is_local_safe is False


def test_contract_missing_dependencies_includes_required_blocked():
    dep = _make_dependency(status=ExternalDependencyStatus.BLOCKED)
    contract = _make_contract(dependencies=(dep,))
    missing = contract.missing_dependencies
    assert dep in missing
    assert len(missing) == 1


def test_contract_missing_dependencies_excludes_available_required():
    dep = _make_dependency(status=ExternalDependencyStatus.AVAILABLE)
    contract = _make_contract(dependencies=(dep,))
    assert contract.missing_dependencies == ()


def test_contract_missing_dependencies_excludes_optional_blocked():
    dep = _make_dependency(
        required=False, status=ExternalDependencyStatus.BLOCKED
    )
    contract = _make_contract(dependencies=(dep,))
    assert contract.missing_dependencies == ()


def test_contract_missing_dependencies_excludes_unknown_optional():
    dep = _make_dependency(
        required=False, status=ExternalDependencyStatus.UNKNOWN
    )
    contract = _make_contract(dependencies=(dep,))
    assert contract.missing_dependencies == ()


def test_contract_missing_dependencies_mixed():
    blocked_required = _make_dependency(
        name="blocked_req", status=ExternalDependencyStatus.BLOCKED
    )
    available_optional = _make_dependency(
        name="avail_opt",
        required=False,
        status=ExternalDependencyStatus.AVAILABLE,
    )
    unknown_optional = _make_dependency(
        name="unknown_opt",
        required=False,
        status=ExternalDependencyStatus.UNKNOWN,
    )
    contract = _make_contract(
        dependencies=(
            blocked_required,
            available_optional,
            unknown_optional,
        )
    )
    missing = contract.missing_dependencies
    assert missing == (blocked_required,)


def test_contract_dependency_status_returns_mapping():
    dep1 = _make_dependency(name="dep1")
    dep2 = _make_dependency(
        name="dep2", status=ExternalDependencyStatus.DEGRADED
    )
    contract = _make_contract(dependencies=(dep1, dep2))
    assert contract.dependency_status == {
        "dep1": "available",
        "dep2": "degraded",
    }


def test_contract_dependency_status_empty_when_no_dependencies():
    contract = _make_contract(dependencies=())
    assert contract.dependency_status == {}


def test_contract_execution_allowed_false_when_not_validated():
    contract = _make_contract(
        status=ExternalCapabilityStatus.LOCAL_SAFE,
        dependencies=(),
    )
    assert contract.execution_allowed is False


def test_contract_execution_allowed_false_when_validated_but_missing_deps():
    dep = _make_dependency(status=ExternalDependencyStatus.BLOCKED)
    contract = _make_contract(
        status=ExternalCapabilityStatus.PRODUCTION_VALIDATED,
        dependencies=(dep,),
    )
    assert contract.execution_allowed is False


def test_contract_execution_allowed_true_when_validated_and_healthy():
    dep = _make_dependency(status=ExternalDependencyStatus.AVAILABLE)
    contract = _make_contract(
        status=ExternalCapabilityStatus.PRODUCTION_VALIDATED,
        dependencies=(dep,),
    )
    assert contract.execution_allowed is True


def test_contract_with_status_without_reason_keeps_dependencies():
    dep = _make_dependency(
        name="dep", status=ExternalDependencyStatus.AVAILABLE
    )
    contract = _make_contract(
        status=ExternalCapabilityStatus.LOCAL_SAFE, dependencies=(dep,)
    )
    updated = contract.with_status(ExternalCapabilityStatus.REFERENCE_ONLY)
    assert updated.status is ExternalCapabilityStatus.REFERENCE_ONLY
    assert updated.dependencies == (dep,)
    assert updated.metadata.get("status_reason") == ""


def test_contract_with_status_accepts_string():
    contract = _make_contract(status=ExternalCapabilityStatus.BLOCKED)
    updated = contract.with_status("local_safe")
    assert updated.status is ExternalCapabilityStatus.LOCAL_SAFE


def test_contract_with_status_with_reason_updates_blocked_deps():
    blocked_dep = _make_dependency(
        name="dep", status=ExternalDependencyStatus.BLOCKED, reason="old"
    )
    healthy_dep = _make_dependency(
        name="dep2",
        status=ExternalDependencyStatus.AVAILABLE,
        reason="ok",
    )
    contract = _make_contract(
        status=ExternalCapabilityStatus.BLOCKED,
        dependencies=(blocked_dep, healthy_dep),
    )
    updated = contract.with_status(
        ExternalCapabilityStatus.PRODUCTION_VALIDATED, reason="new reason"
    )
    updated_blocked = updated.dependencies[0]
    updated_healthy = updated.dependencies[1]
    assert updated.status is ExternalCapabilityStatus.PRODUCTION_VALIDATED
    assert updated_blocked.reason == "new reason"
    assert updated_healthy.reason == "ok"
    assert updated.metadata["status_reason"] == "new reason"


def test_contract_with_status_preserves_other_fields():
    contract = _make_contract(
        capability_id=7,
        name="name",
        domain="api_external",
        description="desc",
        reversibility="reversible",
        compensation_operations=("op1",),
        evidence_requirements=("e1",),
        verification_checks=("v1",),
        risk_level="medium",
    )
    updated = contract.with_status(ExternalCapabilityStatus.LOCAL_SAFE)
    assert updated.id == 7
    assert updated.name == "name"
    assert updated.domain is ExternalCapabilityDomain.API
    assert updated.description == "desc"
    assert updated.reversibility is Reversibility.AUTOMATICALLY_REVERSIBLE
    assert updated.compensation_operations == ("op1",)
    assert updated.evidence_requirements == ("e1",)
    assert updated.verification_checks == ("v1",)
    assert updated.risk_level is ExternalRiskLevel.MEDIUM


def test_contract_with_status_with_reason_on_already_safe_dep_keeps_reason():
    dep = _make_dependency(
        name="dep", status=ExternalDependencyStatus.AVAILABLE, reason="orig"
    )
    contract = _make_contract(
        status=ExternalCapabilityStatus.BLOCKED, dependencies=(dep,)
    )
    updated = contract.with_status(
        ExternalCapabilityStatus.LOCAL_SAFE, reason="shared"
    )
    assert updated.dependencies[0].reason == "orig"
    assert updated.metadata["status_reason"] == "shared"


def test_contract_to_dict_returns_all_fields():
    dep = _make_dependency(
        name="dep", status=ExternalDependencyStatus.AVAILABLE
    )
    contract = _make_contract(
        capability_id=5,
        name="cloud-storage",
        domain=ExternalCapabilityDomain.CLOUD,
        description="Cloud storage",
        dependencies=(dep,),
        reversibility=Reversibility.MANUALLY_RECOVERABLE,
        compensation_operations=("revert",),
        evidence_requirements=("evidence",),
        verification_checks=("check",),
        risk_level=ExternalRiskLevel.HIGH,
        status=ExternalCapabilityStatus.PRODUCTION_VALIDATED,
        metadata={"key": "value"},
    )
    result = contract.to_dict()
    assert result["capability_id"] == 5
    assert result["id"] == 5
    assert result["name"] == "cloud-storage"
    assert result["domain"] == "cloud"
    assert result["description"] == "Cloud storage"
    assert result["dependencies"] == [dep.to_dict()]
    assert result["dependency_status"] == {"dep": "available"}
    assert result["missing_dependencies"] == []
    assert result["reversibility"] == "manually_recoverable"
    assert result["compensation_operations"] == ["revert"]
    assert result["evidence_requirements"] == ["evidence"]
    assert result["verification_checks"] == ["check"]
    assert result["risk_level"] == "high"
    assert result["status"] == "production_validated"
    assert result["execution_allowed"] is True
    assert result["metadata"] == {"key": "value"}


def test_contract_to_dict_includes_missing_dependency_name():
    blocked = _make_dependency(
        name="blocked_dep", status=ExternalDependencyStatus.BLOCKED
    )
    contract = _make_contract(
        dependencies=(blocked,),
        status=ExternalCapabilityStatus.PRODUCTION_VALIDATED,
    )
    result = contract.to_dict()
    assert result["missing_dependencies"] == ["blocked_dep"]
    assert result["execution_allowed"] is False

# ---------------------------------------------------------------------------
# ExternalEvidenceEnvelope
# ---------------------------------------------------------------------------


def test_evidence_canonical_payload_is_sorted_json_string():
    payload = ExternalEvidenceEnvelope.canonical_payload(
        capability_id=1,
        tenant_id="t",
        action_id="a",
        target_system="sys",
        target_resource="res",
        before_state_reference=None,
        after_state_reference=None,
        request_payload_reference=None,
        response_payload_reference=None,
        dependency_status={"b": "available", "a": "blocked"},
        metadata={"z": 1, "a": 2},
    )
    assert isinstance(payload, str)
    data = json.loads(payload)
    assert data["capability_id"] == 1
    assert data["tenant_id"] == "t"
    assert data["action_id"] == "a"
    assert data["target_system"] == "sys"
    assert data["target_resource"] == "res"
    assert data["before_state_reference"] is None
    assert data["after_state_reference"] is None
    assert data["request_payload_reference"] is None
    assert data["response_payload_reference"] is None
    assert data["dependency_status"] == {"a": "blocked", "b": "available"}
    assert data["metadata"] == {"z": 1, "a": 2}


def test_evidence_compute_hash_returns_sha256_hexdigest():
    canonical = ExternalEvidenceEnvelope.canonical_payload(
        capability_id=1,
        tenant_id="t",
        action_id="a",
        target_system="sys",
        target_resource="res",
        before_state_reference=None,
        after_state_reference=None,
        request_payload_reference=None,
        response_payload_reference=None,
        dependency_status={},
        metadata={},
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    computed = ExternalEvidenceEnvelope.compute_hash(
        capability_id=1,
        tenant_id="t",
        action_id="a",
        target_system="sys",
        target_resource="res",
        before_state_reference=None,
        after_state_reference=None,
        request_payload_reference=None,
        response_payload_reference=None,
        dependency_status={},
        metadata={},
    )
    assert computed == expected
    assert len(computed) == 64


def test_evidence_compute_hash_deterministic():
    kwargs = {
        "capability_id": 1,
        "tenant_id": "t",
        "action_id": "a",
        "target_system": "sys",
        "target_resource": "res",
        "before_state_reference": None,
        "after_state_reference": None,
        "request_payload_reference": None,
        "response_payload_reference": None,
        "dependency_status": {"b": "x", "a": "y"},
        "metadata": {"k": "v"},
    }
    assert (
        ExternalEvidenceEnvelope.compute_hash(**kwargs)
        == ExternalEvidenceEnvelope.compute_hash(**kwargs)
    )


def test_evidence_compute_hash_differs_for_dependency_order():
    base = {
        "capability_id": 1,
        "tenant_id": "t",
        "action_id": "a",
        "target_system": "sys",
        "target_resource": "res",
        "before_state_reference": None,
        "after_state_reference": None,
        "request_payload_reference": None,
        "response_payload_reference": None,
        "metadata": {},
    }
    hash_one = ExternalEvidenceEnvelope.compute_hash(
        dependency_status={"a": "x", "b": "y"}, **base
    )
    hash_two = ExternalEvidenceEnvelope.compute_hash(
        dependency_status={"b": "y", "a": "x"}, **base
    )
    assert hash_one == hash_two


def test_evidence_compute_hash_differs_for_different_values():
    base = {
        "capability_id": 1,
        "tenant_id": "t",
        "action_id": "a",
        "target_system": "sys",
        "target_resource": "res",
        "before_state_reference": None,
        "after_state_reference": None,
        "request_payload_reference": None,
        "response_payload_reference": None,
        "metadata": {},
    }
    hash_one = ExternalEvidenceEnvelope.compute_hash(
        dependency_status={"a": "x"}, **base
    )
    hash_two = ExternalEvidenceEnvelope.compute_hash(
        dependency_status={"a": "y"}, **base
    )
    assert hash_one != hash_two


def test_evidence_seal_returns_new_envelope_with_hash():
    envelope = ExternalEvidenceEnvelope(
        evidence_id="ev-1",
        capability_id=1,
        tenant_id="t",
        action_id="a",
        target_system="sys",
        target_resource="res",
        before_state_reference="before",
        after_state_reference="after",
        request_payload_reference="req",
        response_payload_reference="resp",
        dependency_status={"dep": "available"},
        evidence_hash="",
        metadata={"k": "v"},
    )
    sealed = envelope.seal()
    assert sealed is not envelope
    expected_hash = ExternalEvidenceEnvelope.compute_hash(
        capability_id=1,
        tenant_id="t",
        action_id="a",
        target_system="sys",
        target_resource="res",
        before_state_reference="before",
        after_state_reference="after",
        request_payload_reference="req",
        response_payload_reference="resp",
        dependency_status={"dep": "available"},
        metadata={"k": "v"},
    )
    assert sealed.evidence_hash == expected_hash
    assert envelope.evidence_hash == ""
    assert sealed.sealed_at == envelope.sealed_at


def test_evidence_seal_preserves_all_fields():
    envelope = ExternalEvidenceEnvelope(
        evidence_id="ev-1",
        capability_id=1,
        tenant_id="t",
        action_id="a",
        target_system="sys",
        target_resource="res",
        evidence_hash="",
    )
    sealed = envelope.seal()
    assert sealed.evidence_id == "ev-1"
    assert sealed.capability_id == 1
    assert sealed.tenant_id == "t"
    assert sealed.action_id == "a"
    assert sealed.target_system == "sys"
    assert sealed.target_resource == "res"
    assert sealed.before_state_reference is None
    assert sealed.after_state_reference is None
    assert sealed.request_payload_reference is None
    assert sealed.response_payload_reference is None
    assert sealed.dependency_status == {}
    assert sealed.metadata == {}


def test_evidence_to_dict_returns_all_fields():
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    envelope = ExternalEvidenceEnvelope(
        evidence_id="ev-1",
        capability_id=1,
        tenant_id="t",
        action_id="a",
        target_system="sys",
        target_resource="res",
        evidence_hash="abc123",
        sealed_at=fixed_time,
        metadata={"k": "v"},
    )
    result = envelope.to_dict()
    assert result["evidence_id"] == "ev-1"
    assert result["capability_id"] == 1
    assert result["tenant_id"] == "t"
    assert result["action_id"] == "a"
    assert result["target_system"] == "sys"
    assert result["target_resource"] == "res"
    assert result["before_state_reference"] is None
    assert result["after_state_reference"] is None
    assert result["request_payload_reference"] is None
    assert result["response_payload_reference"] is None
    assert result["dependency_status"] == {}
    assert result["evidence_hash"] == "abc123"
    assert result["sealed_at"] == fixed_time.isoformat()
    assert result["metadata"] == {"k": "v"}


def test_evidence_to_dict_copies_dependency_status_and_metadata():
    envelope = ExternalEvidenceEnvelope(
        evidence_id="ev-1",
        capability_id=1,
        tenant_id="t",
        action_id="a",
        target_system="sys",
        target_resource="res",
        dependency_status={"a": 1},
        metadata={"b": 2},
    )
    result = envelope.to_dict()
    result["dependency_status"]["a"] = 999
    result["metadata"]["b"] = 999
    assert envelope.dependency_status == {"a": 1}
    assert envelope.metadata == {"b": 2}

# ---------------------------------------------------------------------------
# ExternalVerificationCheck
# ---------------------------------------------------------------------------


def test_verification_check_to_dict_returns_all_fields():
    check = ExternalVerificationCheck(
        check_id="c1",
        check_type="type_a",
        description="A check",
        expected={"value": 1},
        actual={"value": 1},
        passed=True,
        evidence_references=("ref1", "ref2"),
        details={"detail": "info"},
    )
    result = check.to_dict()
    assert result == {
        "check_id": "c1",
        "check_type": "type_a",
        "description": "A check",
        "expected": {"value": 1},
        "actual": {"value": 1},
        "passed": True,
        "evidence_references": ["ref1", "ref2"],
        "details": {"detail": "info"},
    }


def test_verification_check_to_dict_copies_details():
    check = ExternalVerificationCheck(
        check_id="c1",
        check_type="t",
        description="d",
        expected=None,
        actual=None,
        passed=False,
        details={"k": 1},
    )
    result = check.to_dict()
    result["details"]["k"] = 999
    assert check.details == {"k": 1}

# ---------------------------------------------------------------------------
# ExternalVerificationResult
# ---------------------------------------------------------------------------


def test_verification_result_all_checks_passed_true():
    checks = (
        ExternalVerificationCheck(
            check_id="c1",
            check_type="t",
            description="d",
            expected=None,
            actual=None,
            passed=True,
        ),
        ExternalVerificationCheck(
            check_id="c2",
            check_type="t",
            description="d",
            expected=None,
            actual=None,
            passed=True,
        ),
    )
    result = ExternalVerificationResult(
        verification_id="v1",
        capability_id=1,
        tenant_id="t",
        action_id="a",
        checks=checks,
        verified=True,
        status="verified",
        limitations=(),
        metadata={},
    )
    assert result.all_checks_passed is True


def test_verification_result_all_checks_passed_false_when_one_fails():
    checks = (
        ExternalVerificationCheck(
            check_id="c1",
            check_type="t",
            description="d",
            expected=None,
            actual=None,
            passed=True,
        ),
        ExternalVerificationCheck(
            check_id="c2",
            check_type="t",
            description="d",
            expected=None,
            actual=None,
            passed=False,
        ),
    )
    result = ExternalVerificationResult(
        verification_id="v1",
        capability_id=1,
        tenant_id="t",
        action_id="a",
        checks=checks,
    )
    assert result.all_checks_passed is False


def test_verification_result_all_checks_passed_false_when_no_checks():
    result = ExternalVerificationResult(
        verification_id="v1",
        capability_id=1,
        tenant_id="t",
        action_id="a",
        checks=(),
    )
    assert result.all_checks_passed is False


def test_verification_result_to_dict_returns_all_fields():
    checks = (
        ExternalVerificationCheck(
            check_id="c1",
            check_type="t",
            description="d",
            expected=1,
            actual=1,
            passed=True,
            evidence_references=("r1",),
            details={"k": "v"},
        ),
    )
    result = ExternalVerificationResult(
        verification_id="v1",
        capability_id=42,
        tenant_id="tenant",
        action_id="action",
        checks=checks,
        verified=True,
        status="verified",
        limitations=("lim1",),
        metadata={"m": 1},
    )
    result_dict = result.to_dict()
    assert result_dict == {
        "verification_id": "v1",
        "capability_id": 42,
        "tenant_id": "tenant",
        "action_id": "action",
        "checks": [checks[0].to_dict()],
        "verified": True,
        "status": "verified",
        "limitations": ["lim1"],
        "metadata": {"m": 1},
    }

# ---------------------------------------------------------------------------
# ExternalCapabilityRegistry
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ExternalCapabilityRegistry:
    return ExternalCapabilityRegistry()


@pytest.fixture
def contract() -> ExternalCapabilityContract:
    return _make_contract(
        capability_id=1,
        name="cloud",
        domain=ExternalCapabilityDomain.CLOUD,
        status=ExternalCapabilityStatus.LOCAL_SAFE,
    )


@pytest.fixture
def compensation() -> ExternalCompensationDefinition:
    return _make_compensation(
        capability_id=1,
        operation="revert",
    )


def test_registry_register_adds_contract(registry, contract):
    registry.register(contract)
    assert registry.get(1) is contract
    assert len(registry) == 1


def test_registry_register_duplicate_raises(registry, contract):
    registry.register(contract)
    with pytest.raises(ValueError, match="Duplicate external capability"):
        registry.register(contract)


def test_registry_register_compensation_adds(registry, compensation):
    registry.register_compensation(compensation)
    assert registry.find_compensation(1, "revert") is compensation


def test_registry_register_compensation_duplicate_raises(
    registry, compensation
):
    registry.register_compensation(compensation)
    with pytest.raises(ValueError, match="Duplicate compensation operation"):
        registry.register_compensation(compensation)


def test_registry_get_returns_none_when_absent(registry):
    assert registry.get(999) is None


def test_registry_require_returns_contract_when_present(registry, contract):
    registry.register(contract)
    assert registry.require(1) is contract


def test_registry_require_raises_keyerror_when_absent(registry):
    with pytest.raises(KeyError, match="Unknown external capability"):
        registry.require(999)


def test_registry_compensations_for_returns_matching(
    registry, compensation
):
    registry.register_compensation(compensation)
    comp2 = _make_compensation(capability_id=1, operation="other")
    registry.register_compensation(comp2)
    result = registry.compensations_for(1)
    assert len(result) == 2
    assert compensation in result
    assert comp2 in result


def test_registry_compensations_for_empty_when_none(
    registry, compensation
):
    registry.register_compensation(compensation)
    assert registry.compensations_for(999) == ()


def test_registry_find_compensation_returns_match(registry, compensation):
    registry.register_compensation(compensation)
    assert registry.find_compensation(1, "revert") is compensation


def test_registry_find_compensation_returns_none_when_absent(registry):
    assert registry.find_compensation(1, "missing") is None


def test_registry_contracts_returns_all_registered(registry, contract):
    registry.register(contract)
    other = _make_contract(
        capability_id=2,
        name="network",
        domain=ExternalCapabilityDomain.NETWORK,
    )
    registry.register(other)
    result = registry.contracts()
    assert len(result) == 2
    assert contract in result
    assert other in result


def test_registry_len_matches_registered_contracts(registry, contract):
    assert len(registry) == 0
    registry.register(contract)
    assert len(registry) == 1
    other = _make_contract(
        capability_id=2, name="x", domain=ExternalCapabilityDomain.NETWORK
    )
    registry.register(other)
    assert len(registry) == 2


def test_registry_iter_yields_all_contracts(registry, contract):
    registry.register(contract)
    other = _make_contract(
        capability_id=2, name="x", domain=ExternalCapabilityDomain.NETWORK
    )
    registry.register(other)
    assert len(list(iter(registry))) == 2
    assert contract in list(iter(registry))
    assert other in list(iter(registry))


def test_registry_iter_is_empty_when_no_contracts(registry):
    assert list(iter(registry)) == []
