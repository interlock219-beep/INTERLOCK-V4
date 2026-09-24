from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Iterable

from app.domain.entities.surgical_recovery_types import (
    CompensationType,
    Reversibility,
)


class ExternalCapabilityDomain(StrEnum):
    CLOUD = "cloud"
    KUBERNETES = "kubernetes"
    KUBERNETES_CONTAINERS_WORKLOADS = "kubernetes"
    API_EXTERNAL = "api_external"
    API = "api_external"
    NETWORK = "network"
    IDENTITY_AUTHORITY = "identity_authority"
    AGENT_SESSION_MEMORY = "agent_session_memory"
    TOOLS_MCP_A2A = "tools_mcp_a2a"
    EVENTS_STREAMS = "events_streams"
    OBJECT_DATA_VECTOR = "object_data_vector"
    BROWSER_COMPUTER_USE = "browser_computer_use"
    FINANCIAL_HIGH_IMPACT = "financial_high_impact"


class ExternalDependencyStatus(StrEnum):
    AVAILABLE = "available"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"


class ExternalCapabilityStatus(StrEnum):
    BLOCKED = "blocked"
    LOCAL_SAFE = "local_safe"
    SIMULATION_ONLY = "simulation_only"
    PRODUCTION_VALIDATED = "production_validated"
    REFERENCE_ONLY = "reference_only"


class ExternalRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExternalRecoveryMode(StrEnum):
    DRY_RUN = "dry_run"
    SIMULATION = "simulation"
    COMPENSATION = "compensation"
    VERIFICATION = "verification"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ExternalDependency:
    name: str
    kind: str
    required: bool = True
    status: ExternalDependencyStatus = ExternalDependencyStatus.BLOCKED
    reason: str = "External dependency is not configured"
    credentials_required: bool = True
    endpoint_required: bool = True
    network_required: bool = True
    adapter_required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ExternalDependencyStatus(self.status))

    @property
    def is_available(self) -> bool:
        return self.status == ExternalDependencyStatus.AVAILABLE

    @property
    def is_blocked(self) -> bool:
        return self.status == ExternalDependencyStatus.BLOCKED

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "status": self.status.value,
            "reason": self.reason,
            "credentials_required": self.credentials_required,
            "endpoint_required": self.endpoint_required,
            "network_required": self.network_required,
            "adapter_required": self.adapter_required,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExternalCompensationDefinition:
    capability_id: int
    operation: str
    target_system: str
    target_resource: str
    payload_schema: dict[str, Any] = field(default_factory=dict)
    compensation_type: CompensationType = CompensationType.CUSTOM
    idempotency_required: bool = True
    approval_required: bool = True
    reversible: Reversibility = Reversibility.UNKNOWN
    status: ExternalCapabilityStatus = ExternalCapabilityStatus.BLOCKED
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reversible", Reversibility.normalize(self.reversible))
        object.__setattr__(self, "status", ExternalCapabilityStatus(self.status))

    @property
    def is_blocked(self) -> bool:
        return self.status == ExternalCapabilityStatus.BLOCKED

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "operation": self.operation,
            "target_system": self.target_system,
            "target_resource": self.target_resource,
            "payload_schema": dict(self.payload_schema),
            "compensation_type": self.compensation_type.value,
            "idempotency_required": self.idempotency_required,
            "approval_required": self.approval_required,
            "reversible": self.reversible.value,
            "status": self.status.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExternalCapabilityContract:
    capability_id: int
    name: str
    domain: ExternalCapabilityDomain
    description: str
    dependencies: tuple[ExternalDependency, ...] = ()
    reversibility: Reversibility = Reversibility.UNKNOWN
    compensation_operations: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    verification_checks: tuple[str, ...] = ()
    risk_level: ExternalRiskLevel = ExternalRiskLevel.HIGH
    status: ExternalCapabilityStatus = ExternalCapabilityStatus.BLOCKED
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", ExternalCapabilityDomain(self.domain))
        object.__setattr__(self, "reversibility", Reversibility.normalize(self.reversibility))
        object.__setattr__(self, "risk_level", ExternalRiskLevel(self.risk_level))
        object.__setattr__(self, "status", ExternalCapabilityStatus(self.status))
        object.__setattr__(self, "dependencies", tuple(self.dependencies))

    @property
    def id(self) -> int:
        return self.capability_id

    @property
    def is_blocked(self) -> bool:
        return self.status == ExternalCapabilityStatus.BLOCKED

    @property
    def is_local_safe(self) -> bool:
        return self.status in (
            ExternalCapabilityStatus.LOCAL_SAFE,
            ExternalCapabilityStatus.SIMULATION_ONLY,
            ExternalCapabilityStatus.REFERENCE_ONLY,
        )

    @property
    def missing_dependencies(self) -> tuple[ExternalDependency, ...]:
        return tuple(
            dependency
            for dependency in self.dependencies
            if dependency.required and dependency.status != ExternalDependencyStatus.AVAILABLE
        )

    @property
    def dependency_status(self) -> dict[str, str]:
        return {
            dependency.name: dependency.status.value
            for dependency in self.dependencies
        }

    @property
    def execution_allowed(self) -> bool:
        return (
            self.status == ExternalCapabilityStatus.PRODUCTION_VALIDATED
            and not self.missing_dependencies
        )

    def with_status(
        self,
        status: ExternalCapabilityStatus | str,
        *,
        reason: str | None = None,
    ) -> ExternalCapabilityContract:
        normalized = ExternalCapabilityStatus(status)
        dependencies = self.dependencies
        if reason is not None:
            dependencies = tuple(
                ExternalDependency(
                    name=dependency.name,
                    kind=dependency.kind,
                    required=dependency.required,
                    status=dependency.status,
                    reason=reason if dependency.is_blocked else dependency.reason,
                    credentials_required=dependency.credentials_required,
                    endpoint_required=dependency.endpoint_required,
                    network_required=dependency.network_required,
                    adapter_required=dependency.adapter_required,
                    metadata=dict(dependency.metadata),
                )
                for dependency in dependencies
            )
        metadata = dict(self.metadata)
        metadata["status_reason"] = reason or metadata.get("status_reason", "")
        return ExternalCapabilityContract(
            capability_id=self.capability_id,
            name=self.name,
            domain=self.domain,
            description=self.description,
            dependencies=dependencies,
            reversibility=self.reversibility,
            compensation_operations=self.compensation_operations,
            evidence_requirements=self.evidence_requirements,
            verification_checks=self.verification_checks,
            risk_level=self.risk_level,
            status=normalized,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "id": self.capability_id,
            "name": self.name,
            "domain": self.domain.value,
            "description": self.description,
            "dependencies": [dependency.to_dict() for dependency in self.dependencies],
            "dependency_status": self.dependency_status,
            "missing_dependencies": [
                dependency.name for dependency in self.missing_dependencies
            ],
            "reversibility": self.reversibility.value,
            "compensation_operations": list(self.compensation_operations),
            "evidence_requirements": list(self.evidence_requirements),
            "verification_checks": list(self.verification_checks),
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "execution_allowed": self.execution_allowed,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExternalEvidenceEnvelope:
    evidence_id: str
    capability_id: int
    tenant_id: str
    action_id: str
    target_system: str
    target_resource: str
    before_state_reference: str | None = None
    after_state_reference: str | None = None
    request_payload_reference: str | None = None
    response_payload_reference: str | None = None
    dependency_status: dict[str, str] = field(default_factory=dict)
    evidence_hash: str = ""
    sealed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def canonical_payload(
        capability_id: int,
        tenant_id: str,
        action_id: str,
        target_system: str,
        target_resource: str,
        before_state_reference: str | None,
        after_state_reference: str | None,
        request_payload_reference: str | None,
        response_payload_reference: str | None,
        dependency_status: dict[str, str],
        metadata: dict[str, Any],
    ) -> str:
        payload = {
            "capability_id": capability_id,
            "tenant_id": tenant_id,
            "action_id": action_id,
            "target_system": target_system,
            "target_resource": target_resource,
            "before_state_reference": before_state_reference,
            "after_state_reference": after_state_reference,
            "request_payload_reference": request_payload_reference,
            "response_payload_reference": response_payload_reference,
            "dependency_status": dict(sorted(dependency_status.items())),
            "metadata": metadata,
        }
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @classmethod
    def compute_hash(cls, **payload: Any) -> str:
        canonical = cls.canonical_payload(**payload)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def seal(self) -> ExternalEvidenceEnvelope:
        evidence_hash = self.compute_hash(
            capability_id=self.capability_id,
            tenant_id=self.tenant_id,
            action_id=self.action_id,
            target_system=self.target_system,
            target_resource=self.target_resource,
            before_state_reference=self.before_state_reference,
            after_state_reference=self.after_state_reference,
            request_payload_reference=self.request_payload_reference,
            response_payload_reference=self.response_payload_reference,
            dependency_status=self.dependency_status,
            metadata=self.metadata,
        )
        return ExternalEvidenceEnvelope(
            evidence_id=self.evidence_id,
            capability_id=self.capability_id,
            tenant_id=self.tenant_id,
            action_id=self.action_id,
            target_system=self.target_system,
            target_resource=self.target_resource,
            before_state_reference=self.before_state_reference,
            after_state_reference=self.after_state_reference,
            request_payload_reference=self.request_payload_reference,
            response_payload_reference=self.response_payload_reference,
            dependency_status=dict(self.dependency_status),
            evidence_hash=evidence_hash,
            sealed_at=self.sealed_at,
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "capability_id": self.capability_id,
            "tenant_id": self.tenant_id,
            "action_id": self.action_id,
            "target_system": self.target_system,
            "target_resource": self.target_resource,
            "before_state_reference": self.before_state_reference,
            "after_state_reference": self.after_state_reference,
            "request_payload_reference": self.request_payload_reference,
            "response_payload_reference": self.response_payload_reference,
            "dependency_status": dict(self.dependency_status),
            "evidence_hash": self.evidence_hash,
            "sealed_at": self.sealed_at.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExternalVerificationCheck:
    check_id: str
    check_type: str
    description: str
    expected: Any
    actual: Any
    passed: bool
    evidence_references: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "check_type": self.check_type,
            "description": self.description,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "evidence_references": list(self.evidence_references),
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class ExternalVerificationResult:
    verification_id: str
    capability_id: int
    tenant_id: str
    action_id: str
    checks: tuple[ExternalVerificationCheck, ...] = ()
    verified: bool = False
    status: str = "unverified"
    limitations: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def all_checks_passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "capability_id": self.capability_id,
            "tenant_id": self.tenant_id,
            "action_id": self.action_id,
            "checks": [check.to_dict() for check in self.checks],
            "verified": self.verified,
            "status": self.status,
            "limitations": list(self.limitations),
            "metadata": dict(self.metadata),
        }


class ExternalCapabilityRegistry:
    def __init__(self) -> None:
        self._contracts: dict[int, ExternalCapabilityContract] = {}
        self._compensations: dict[tuple[int, str], ExternalCompensationDefinition] = {}

    def register(self, contract: ExternalCapabilityContract) -> None:
        if contract.capability_id in self._contracts:
            raise ValueError(f"Duplicate external capability: {contract.capability_id}")
        self._contracts[contract.capability_id] = contract

    def register_compensation(
        self,
        compensation: ExternalCompensationDefinition,
    ) -> None:
        key = (compensation.capability_id, compensation.operation)
        if key in self._compensations:
            raise ValueError(
                f"Duplicate compensation operation: {compensation.capability_id}:{compensation.operation}"
            )
        self._compensations[key] = compensation

    def get(self, capability_id: int) -> ExternalCapabilityContract | None:
        return self._contracts.get(capability_id)

    def require(self, capability_id: int) -> ExternalCapabilityContract:
        contract = self.get(capability_id)
        if contract is None:
            raise KeyError(f"Unknown external capability: {capability_id}")
        return contract

    def compensations_for(self, capability_id: int) -> tuple[ExternalCompensationDefinition, ...]:
        return tuple(
            compensation
            for (registered_id, _), compensation in self._compensations.items()
            if registered_id == capability_id
        )

    def find_compensation(
        self,
        capability_id: int,
        operation: str,
    ) -> ExternalCompensationDefinition | None:
        return self._compensations.get((capability_id, operation))

    def contracts(self) -> tuple[ExternalCapabilityContract, ...]:
        return tuple(self._contracts.values())

    def __len__(self) -> int:
        return len(self._contracts)

    def __iter__(self) -> Iterable[ExternalCapabilityContract]:
        return iter(self._contracts.values())


ExternalCapabilityCatalogEntry = ExternalCapabilityContract
