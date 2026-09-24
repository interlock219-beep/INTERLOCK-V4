from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.domain.entities.causal_state_types import ConfidenceLevel


class VerificationOutcome(StrEnum):
    """Independent verification outcome distinct from execution status.

    CRITICAL: RECOVERY_EXECUTED != RECOVERY_VERIFIED.
    Execution and verification are separate concerns.
    """

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    VERIFICATION_FAILED = "verification_failed"
    MANUAL_CHECK_REQUIRED = "manual_check_required"
    EVIDENCE_TAMPERED = "evidence_tampered"
    EVIDENCE_MISSING = "evidence_missing"
    EVIDENCE_CONFLICTING = "evidence_conflicting"
    INCONCLUSIVE = "inconclusive"
    UNKNOWN = "unknown"


class VerificationCheckType(StrEnum):
    """Types of independent verification checks."""

    EXACT = "exact"
    BYTE = "byte"
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    INTEGRITY = "integrity"
    DEPENDENCY = "dependency"
    PERMISSION = "permission"
    IDENTITY = "identity"
    DATABASE = "database"
    APPLICATION = "application"
    BUSINESS = "business"
    CROSS_SYSTEM = "cross_system"
    COMPLETENESS = "completeness"
    HUMAN_CHANGE = "human_change"


class IndependentVerifierRole(StrEnum):
    """Role/identity of the independent verifier."""

    AUTOMATED_VERIFIER = "automated_verifier"
    EXTERNAL_AUDITOR = "external_auditor"
    SECONDARY_SYSTEM = "secondary_system"
    HUMAN_REVIEWER = "human_reviewer"
    CROSS_TEAM_VERIFIER = "cross_team_verifier"


@dataclass(frozen=True, slots=True)
class IndependentVerifier:
    """Identity of the independent verifier.

    Verification MUST be performed by an entity distinct from the executor.
    """

    verifier_id: str
    role: IndependentVerifierRole
    tenant_id: str
    credentials: dict[str, Any] = field(default_factory=dict)
    delegation_chain: list[str] = field(default_factory=list)
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    """A single independent verification check."""

    check_id: str
    check_type: VerificationCheckType
    description: str
    expected: Any
    actual: Any
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    evidence_references: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IndependentVerificationResult:
    """Result of an independent verification.

    Separate from execution result. Verification is a distinct phase.
    """

    verification_id: str
    plan_id: str
    tenant_id: str
    verifier: IndependentVerifier
    action_id: str
    outcome: VerificationOutcome
    checks: list[VerificationCheck] = field(default_factory=list)
    execution_verified: bool = False
    verification_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def all_checks_passed(self) -> bool:
        return all(check.passed for check in self.checks) if self.checks else False

    @property
    def failed_checks(self) -> list[VerificationCheck]:
        return [check for check in self.checks if not check.passed]

    @property
    def check_count(self) -> int:
        return len(self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for check in self.checks if check.passed)


@dataclass(frozen=True, slots=True)
class IndependentVerificationReport:
    """Aggregate report of independent verifications for a recovery plan."""

    report_id: str
    tenant_id: str
    plan_id: str
    incident_id: str
    verifier: IndependentVerifier
    results: list[IndependentVerificationResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    overall_outcome: VerificationOutcome = VerificationOutcome.UNKNOWN
    limitations: list[str] = field(default_factory=list)

    @property
    def all_verified(self) -> bool:
        return all(r.outcome == VerificationOutcome.VERIFIED for r in self.results)

    @property
    def any_unverified(self) -> bool:
        return any(r.outcome == VerificationOutcome.UNVERIFIED for r in self.results)

    @property
    def any_failed(self) -> bool:
        return any(
            r.outcome in (VerificationOutcome.VERIFICATION_FAILED, VerificationOutcome.EVIDENCE_TAMPERED)
            for r in self.results
        )


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    """Assessment of evidence quality for verification."""

    evidence_id: str
    is_tampered: bool = False
    is_missing: bool = False
    is_conflicting: bool = False
    is_inconclusive: bool = False
    tamper_indicators: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    conflict_details: list[str] = field(default_factory=list)
    inconclusive_reasons: list[str] = field(default_factory=list)

    @property
    def outcome(self) -> VerificationOutcome:
        if self.is_tampered:
            return VerificationOutcome.EVIDENCE_TAMPERED
        if self.is_missing:
            return VerificationOutcome.EVIDENCE_MISSING
        if self.is_conflicting:
            return VerificationOutcome.EVIDENCE_CONFLICTING
        if self.is_inconclusive:
            return VerificationOutcome.INCONCLUSIVE
        return VerificationOutcome.UNKNOWN
class VerificationLayer(StrEnum):
    """Multi-layer verification layers.

    VER-070: Multi-layer verification spans exact state, byte/content,
    structural, semantic, integrity, dependency, permissions, identity,
    DB constraints, app invariants, business invariants, cross-system,
    recovery completeness, and human-change preservation.
    """

    EXACT_STATE = "exact_state"
    BYTE_CONTENT = "byte_content"
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    INTEGRITY = "integrity"
    DEPENDENCY = "dependency"
    PERMISSIONS = "permissions"
    IDENTITY = "identity"
    DB_CONSTRAINTS = "db_constraints"
    APP_INVARIANTS = "app_invariants"
    BUSINESS_INVARIANTS = "business_invariants"
    CROSS_SYSTEM = "cross_system"
    RECOVERY_COMPLETENESS = "recovery_completeness"
    HUMAN_CHANGE_PRESERVATION = "human_change_preservation"


@dataclass(frozen=True, slots=True)
class VerificationLayerResult:
    """Result of a single multi-layer verification check."""

    layer: VerificationLayer
    passed: bool
    status: VerificationOutcome
    details: dict[str, Any] = field(default_factory=dict)
    evidence_references: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_definitive(self) -> bool:
        """A definitive layer result blocks further recovery claims."""
        return self.status in (
            VerificationOutcome.VERIFICATION_FAILED,
            VerificationOutcome.EVIDENCE_TAMPERED,
            VerificationOutcome.EVIDENCE_MISSING,
        )

    @property
    def is_inconclusive(self) -> bool:
        return self.status in (
            VerificationOutcome.INCONCLUSIVE,
            VerificationOutcome.MANUAL_CHECK_REQUIRED,
            VerificationOutcome.UNKNOWN,
        )


@dataclass(frozen=True, slots=True)
class VerificationCoverage:
    """Measurement of verification coverage across layers and actions."""

    total_checks: int
    passed_checks: int
    failed_checks: int
    inconclusive_checks: int
    coverage_rate: float
    layers_measured: list[VerificationLayer]
    layers_missing: list[VerificationLayer]
    action_coverage: dict[str, float]
    layer_coverage: dict[str, float]
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def all_layers_measured(self) -> bool:
        return len(self.layers_missing) == 0

    @property
    def fully_covered(self) -> bool:
        return self.coverage_rate == 1.0 and self.inconclusive_checks == 0


@dataclass(frozen=True, slots=True)
class ResidualRisk:
    """Residual risk after verification (VER-072)."""

    risk_score: float
    risk_level: str
    risk_factors: list[str]
    mitigations: list[str]
    blocking_factors: list[str]
    assessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def acceptable(self) -> bool:
        return self.risk_level == "low" and not self.blocking_factors

    @property
    def blocks_recovery_claim(self) -> bool:
        return bool(self.blocking_factors)


@dataclass(frozen=True, slots=True)
class VerificationConfidence:
    """Verification-confidence calculation (VER-072).

    Combines coverage, evidence quality, and residual risk into an
    explainable confidence assessment.
    """

    confidence_id: str
    tenant_id: str
    plan_id: str
    confidence_level: ConfidenceLevel
    coverage_rate: float
    evidence_quality: float
    residual_risk: float
    definitive_failures: int
    inconclusive_layers: int
    factors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    assessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def can_claim_recovered(self) -> bool:
        return self.confidence_level in (
            ConfidenceLevel.HIGH_CONFIDENCE,
            ConfidenceLevel.MEDIUM_CONFIDENCE,
        ) and self.definitive_failures == 0

    @property
    def requires_human_review(self) -> bool:
        return self.confidence_level in (
            ConfidenceLevel.LOW_CONFIDENCE,
            ConfidenceLevel.INSUFFICIENT_EVIDENCE,
        ) or self.inconclusive_layers > 0

__all__ = [
    "ConfidenceLevel",
    "EvidenceAssessment",
    "IndependentVerifier",
    "IndependentVerifierRole",
    "IndependentVerificationReport",
    "IndependentVerificationResult",
    "ResidualRisk",
    "VerificationCheck",
    "VerificationCheckType",
    "VerificationConfidence",
    "VerificationCoverage",
    "VerificationLayer",
    "VerificationLayerResult",
    "VerificationOutcome",
]
