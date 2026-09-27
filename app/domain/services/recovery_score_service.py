from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.causal_state_types import (
    DurableExecutionStep,
    RecoveryConfidence,
)
from app.domain.entities.durable_recovery_types import (
    PlanCoordinationState,
)
from app.domain.entities.surgical_recovery_types import (
    ConflictStatus,
    ExecutionState,
    Reversibility,
)
from app.domain.repositories.causal_state_repositories import (
    DurableExecutionRepository,
    RecoveryReportRepository,
)
from app.domain.repositories.durable_recovery_repository import (
    RecoveryReconciliationRepository,
)
from app.domain.repositories.recovery_evidence_repository import (
    RecoveryEvidenceRepository,
)
from app.domain.services.recovery_confidence_model import RecoveryConfidenceModel


@dataclass(frozen=True, slots=True)
class ExecutionAssessment:
    """Result of assessing execution status for a recovery plan."""

    total_steps: int
    executed_steps: int
    failed_steps: int
    blocked_steps: int
    manual_steps: int
    unknown_outcome_steps: int
    execution_rate: float
    execution_complete: bool
    partial_details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VerificationAssessment:
    """Result of assessing verification status for a recovery plan."""

    verified_steps: int
    unverified_steps: int
    failed_steps: int
    unknown_outcome_steps: int
    manual_required_steps: int
    total_verifiable: int
    verification_rate: float
    all_verified: bool
    verification_details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RecoveryScore:
    """A deterministic, explainable recovery score.

    Distinguishes execution result, verification result, and confidence.
    Never converts UNKNOWN/UNVERIFIED into RECOVERED.
    """

    score: float
    band: str
    execution_assessment: ExecutionAssessment
    verification_assessment: VerificationAssessment
    confidence: RecoveryConfidence | None
    factors: list[str]
    recommendations: list[str]
    limitations: list[str]
    scored_at: datetime
    evidence_integrity_score: float
    state_certainty: float
    recovery_coverage: float
    dependency_certainty: float
    conflict_weight: float
    irreversibility_penalty: float
    external_side_effect_score: float
    verification_coverage: float
    adapter_reliability: float
    unresolved_uncertainty: float
    cannot_claim_recovered: bool
    score_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "band": self.band,
            "execution_assessment": asdict(self.execution_assessment),
            "verification_assessment": asdict(self.verification_assessment),
            "confidence_level": self.confidence.level.value if self.confidence else "none",
            "factors": self.factors,
            "recommendations": self.recommendations,
            "limitations": self.limitations,
            "evidence_integrity_score": self.evidence_integrity_score,
            "state_certainty": self.state_certainty,
            "recovery_coverage": self.recovery_coverage,
            "dependency_certainty": self.dependency_certainty,
            "conflict_weight": self.conflict_weight,
            "irreversibility_penalty": self.irreversibility_penalty,
            "external_side_effect_score": self.external_side_effect_score,
            "verification_coverage": self.verification_coverage,
            "adapter_reliability": self.adapter_reliability,
            "unresolved_uncertainty": self.unresolved_uncertainty,
            "cannot_claim_recovered": self.cannot_claim_recovered,
            "scored_at": self.scored_at.isoformat(),
        }


class RecoveryScoreService:
    """Deterministic, explainable recovery scoring service.

    Integrates with the existing recovery architecture to produce a composite
    score that distinguishes:

    * **Execution result** - whether steps were executed and succeeded
    * **Verification result** - whether outcomes were independently verified
    * **Confidence** - whether recovery can be safely claimed

    The service NEVER converts UNKNOWN/UNVERIFIED into RECOVERED.  If any
    step has an unknown external outcome, unknown reversibility, or fails
    verification, the score reflects that and ``cannot_claim_recovered``
    will be ``True``.

    Scoring factors (each 0.0-1.0 unless noted):
    - evidence completeness
    - state certainty
    - recovery coverage
    - dependency certainty
    - conflict weight (penalty)
    - irreversibility penalty
    - external side-effect accounting
    - verification coverage
    - adapter reliability
    - unresolved uncertainty (penalty)
    """

    HIGH_THRESHOLD = 0.9
    MEDIUM_THRESHOLD = 0.7
    LOW_THRESHOLD = 0.5

    def __init__(
        self,
        evidence_repository: RecoveryEvidenceRepository | None = None,
        execution_repository: DurableExecutionRepository | None = None,
        report_repository: RecoveryReportRepository | None = None,
        reconciliation_repository: RecoveryReconciliationRepository | None = None,
        confidence_model: RecoveryConfidenceModel | None = None,
    ) -> None:
        self._evidence_repo = evidence_repository
        self._execution_repo = execution_repository
        self._report_repo = report_repository
        self._reconciliation_repo = reconciliation_repository
        self._confidence_model = confidence_model

    async def score_plan_recovery(
        self,
        tenant_id: str,
        plan_id: str,
        actions: list[Any] | None = None,
    ) -> RecoveryScore:
        """Compute a recovery score for a durable recovery plan.

        Pulls execution state from the durable execution repository,
        evidence from the evidence repository, and independent
        verification from the report repository.
        """
        actions = actions or []
        factors: list[str] = []
        recommendations: list[str] = []
        limitations: list[str] = []

        execution_assessment = await self._assess_execution(tenant_id, plan_id)
        verification_assessment = await self._assess_verification(
            tenant_id, plan_id, execution_assessment
        )
        evidence_score = await self._assess_evidence_integrity(tenant_id, plan_id, actions)
        state_certainty = await self._assess_state_certainty(tenant_id, plan_id, actions)
        recovery_coverage = await self._assess_recovery_coverage(tenant_id, plan_id, actions)
        dependency_certainty = await self._assess_dependency_certainty(tenant_id, plan_id, actions)
        conflict_weight = await self._assess_conflicts(tenant_id, plan_id, actions)
        irreversibility_penalty = await self._assess_irreversibility(tenant_id, plan_id, actions)
        external_side_effect_score = await self._assess_external_side_effects(
            tenant_id, plan_id, actions
        )
        verification_coverage = verification_assessment.verification_rate
        adapter_reliability = await self._assess_adapter_reliability(tenant_id, plan_id, actions)
        unresolved_uncertainty = await self._assess_unresolved_uncertainty(
            tenant_id, plan_id, actions
        )

        confidence = None
        if self._confidence_model is not None and actions:
            try:
                confidence = await self._confidence_model.assess_confidence(
                    tenant_id, plan_id, actions
                )
            except Exception:
                limitations.append("Confidence model failed to assess plan")
                confidence = None

        sub_scores = {
            "evidence_completeness": evidence_score,
            "state_certainty": state_certainty,
            "recovery_coverage": recovery_coverage,
            "dependency_certainty": dependency_certainty,
            "conflict_weight": 1.0 - conflict_weight,
            "irreversibility": 1.0 - irreversibility_penalty,
            "external_side_effects": external_side_effect_score,
            "verification_coverage": verification_coverage,
            "adapter_reliability": adapter_reliability,
            "unresolved_uncertainty_penalty": 1.0 - unresolved_uncertainty,
        }

        weighted_score = self._compute_weighted_score(
            sub_scores, execution_assessment, verification_assessment
        )

        cannot_claim_recovered = self._should_block_recovery_claim(
            execution_assessment,
            verification_assessment,
            unresolved_uncertainty,
            irreversibility_penalty,
        )

        if cannot_claim_recovered:
            limitations.append(
                "Recovery cannot be claimed: verification or uncertainty criteria not met"
            )
        if evidence_score < 0.5:
            limitations.append(f"Evidence completeness low ({evidence_score:.2f})")
            recommendations.append("Capture before-state references for all actions")
        if state_certainty < 0.5:
            limitations.append(f"State certainty low ({state_certainty:.2f})")
            recommendations.append("Capture current state for all resources")
        if recovery_coverage < 0.5:
            limitations.append(f"Recovery coverage low ({recovery_coverage:.2f})")
            recommendations.append("Register adapters for all target systems")
        if dependency_certainty < 0.5:
            limitations.append(f"Dependency certainty low ({dependency_certainty:.2f})")
            recommendations.append("Complete dependency evidence for all actions")
        if conflict_weight > 0.3:
            limitations.append(f"Conflicts detected (weight={conflict_weight:.2f})")
            recommendations.append("Resolve conflicts before recovery")
        if irreversibility_penalty > 0.3:
            limitations.append(
                f"Irreversible actions present (penalty={irreversibility_penalty:.2f})"
            )
            recommendations.append("Manual recovery required for irreversible actions")
        if external_side_effect_score < 0.5:
            limitations.append("External side effects not fully accounted")
            recommendations.append("Classify and verify all external side effects")
        if verification_coverage < 0.5:
            limitations.append(f"Verification coverage low ({verification_coverage:.2f})")
            recommendations.append("Enable verification for all adapters")
        if adapter_reliability < 0.5:
            limitations.append(f"Adapter reliability low ({adapter_reliability:.2f})")
            recommendations.append("Audit adapter health and reliability")
        if unresolved_uncertainty > 0.3:
            limitations.append(f"Unresolved uncertainty high ({unresolved_uncertainty:.2f})")
            recommendations.append("Resolve unknown external outcomes")

        band = self._determine_band(weighted_score, cannot_claim_recovered)

        if band in ("HIGH", "MEDIUM") and not recommendations:
            if band == "HIGH":
                recommendations.append("All evidence factors support safe recovery")
            else:
                recommendations.append("Review flagged factors before proceeding")

        factors.append(f"weighted_score={weighted_score:.4f}")
        factors.append(f"band={band}")
        factors.append(f"execution_rate={execution_assessment.execution_rate:.4f}")
        factors.append(f"verification_rate={verification_coverage:.4f}")
        factors.append(f"evidence_completeness={evidence_score:.4f}")
        factors.append(f"state_certainty={state_certainty:.4f}")
        factors.append(f"recovery_coverage={recovery_coverage:.4f}")
        factors.append(f"dependency_certainty={dependency_certainty:.4f}")
        factors.append(f"conflict_weight={conflict_weight:.4f}")
        factors.append(f"irreversibility_penalty={irreversibility_penalty:.4f}")
        factors.append(f"external_side_effect_score={external_side_effect_score:.4f}")
        factors.append(f"adapter_reliability={adapter_reliability:.4f}")
        factors.append(f"unresolved_uncertainty={unresolved_uncertainty:.4f}")

        score_id = hashlib.sha256(
            f"{tenant_id}:{plan_id}:{weighted_score:.6f}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        return RecoveryScore(
            score=weighted_score,
            band=band,
            execution_assessment=execution_assessment,
            verification_assessment=verification_assessment,
            confidence=confidence,
            factors=factors,
            recommendations=recommendations,
            limitations=limitations,
            scored_at=datetime.now(UTC),
            evidence_integrity_score=evidence_score,
            state_certainty=state_certainty,
            recovery_coverage=recovery_coverage,
            dependency_certainty=dependency_certainty,
            conflict_weight=conflict_weight,
            irreversibility_penalty=irreversibility_penalty,
            external_side_effect_score=external_side_effect_score,
            verification_coverage=verification_coverage,
            adapter_reliability=adapter_reliability,
            unresolved_uncertainty=unresolved_uncertainty,
            cannot_claim_recovered=cannot_claim_recovered,
            score_metadata={
                "score_id": score_id,
                "sub_scores": sub_scores,
                "plan_id": plan_id,
                "tenant_id": tenant_id,
            },
        )

    async def _assess_execution(self, tenant_id: str, plan_id: str) -> ExecutionAssessment:
        """Assess execution status from durable execution steps."""
        if self._execution_repo is None:
            return ExecutionAssessment(
                total_steps=0,
                executed_steps=0,
                failed_steps=0,
                blocked_steps=0,
                manual_steps=0,
                unknown_outcome_steps=0,
                execution_rate=0.0,
                execution_complete=False,
                partial_details={"reason": "no execution repository"},
            )

        steps, total = await self._execution_repo.list_by_plan(tenant_id, plan_id, limit=500)

        if total == 0:
            return ExecutionAssessment(
                total_steps=0,
                executed_steps=0,
                failed_steps=0,
                blocked_steps=0,
                manual_steps=0,
                unknown_outcome_steps=0,
                execution_rate=0.0,
                execution_complete=False,
                partial_details={"reason": "no steps found"},
            )

        executed = 0
        failed = 0
        blocked = 0
        manual = 0
        unknown = 0

        for step in steps:
            state = step.execution_state
            if state == ExecutionState.SUCCEEDED.value:
                executed += 1
            elif state == ExecutionState.FAILED.value:
                failed += 1
            elif state in (
                ExecutionState.BLOCKED_BY_DRIFT.value,
                ExecutionState.BLOCKED_BY_CONFLICT.value,
            ):
                blocked += 1
            elif state == ExecutionState.REQUIRES_MANUAL_ACTION.value:
                manual += 1
            elif state == ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value:
                unknown += 1

        execution_rate = executed / total if total > 0 else 0.0
        execution_complete = executed == total and failed == 0 and unknown == 0

        return ExecutionAssessment(
            total_steps=total,
            executed_steps=executed,
            failed_steps=failed,
            blocked_steps=blocked,
            manual_steps=manual,
            unknown_outcome_steps=unknown,
            execution_rate=execution_rate,
            execution_complete=execution_complete,
            partial_details={
                "failed_steps": failed,
                "blocked_steps": blocked,
                "manual_steps": manual,
                "unknown_steps": unknown,
            },
        )

    async def _assess_verification(
        self,
        tenant_id: str,
        plan_id: str,
        execution_assessment: ExecutionAssessment,
    ) -> VerificationAssessment:
        """Assess verification status from execution steps and reports."""
        if self._execution_repo is None:
            return VerificationAssessment(
                verified_steps=0,
                unverified_steps=0,
                failed_steps=0,
                unknown_outcome_steps=0,
                manual_required_steps=0,
                total_verifiable=0,
                verification_rate=0.0,
                all_verified=False,
                verification_details={"reason": "no execution repository"},
            )

        steps, total = await self._execution_repo.list_by_plan(tenant_id, plan_id, limit=500)

        verified = 0
        unverified = 0
        failed = 0
        unknown = 0
        manual = 0

        for step in steps:
            state = step.execution_state
            if state == ExecutionState.SUCCEEDED.value:
                if step.verification_passed:
                    verified += 1
                else:
                    unverified += 1
            elif state == ExecutionState.FAILED.value:
                failed += 1
            elif state == ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value:
                unknown += 1
            elif state == ExecutionState.REQUIRES_MANUAL_ACTION.value or state in (
                ExecutionState.BLOCKED_BY_DRIFT.value,
                ExecutionState.BLOCKED_BY_CONFLICT.value,
            ):
                manual += 1

        if execution_assessment.total_steps > 0:
            total_verifiable = execution_assessment.executed_steps
            verification_rate = verified / total_verifiable if total_verifiable > 0 else 0.0
        else:
            total_verifiable = 0
            verification_rate = 0.0

        all_verified = (
            verified == total and unverified == 0 and failed == 0 and unknown == 0 and total > 0
        )

        return VerificationAssessment(
            verified_steps=verified,
            unverified_steps=unverified,
            failed_steps=failed,
            unknown_outcome_steps=unknown,
            manual_required_steps=manual,
            total_verifiable=total_verifiable,
            verification_rate=verification_rate,
            all_verified=all_verified,
            verification_details={
                "verified": verified,
                "unverified": unverified,
                "failed": failed,
                "unknown": unknown,
                "manual": manual,
            },
        )

    async def _assess_evidence_integrity(
        self, tenant_id: str, plan_id: str, actions: list[Any]
    ) -> float:
        """Assess the completeness of evidence for all actions."""
        if self._evidence_repo is None or not actions:
            return 0.0 if actions else 1.0

        evidence_count = 0
        before_state_count = 0
        total = len(actions)

        for action in actions:
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            if evidence is not None:
                evidence_count += 1
                if evidence.before_state_reference:
                    before_state_count += 1

        if total == 0:
            return 1.0

        return evidence_count / total

    async def _assess_state_certainty(
        self, tenant_id: str, plan_id: str, actions: list[Any]
    ) -> float:
        """Assess certainty of state (before/after/current references)."""
        if self._evidence_repo is None or not actions:
            return 0.0 if actions else 1.0

        total = len(actions)
        certain = 0

        for action in actions:
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            if evidence is not None:
                has_before = bool(evidence.before_state_reference)
                has_after = bool(evidence.after_state_reference)
                has_version = bool(evidence.state_version) and bool(evidence.resource_version)
                if has_before and (has_after or has_version):
                    certain += 1

        return certain / total if total > 0 else 0.0

    async def _assess_recovery_coverage(
        self, tenant_id: str, plan_id: str, actions: list[Any]
    ) -> float:
        """Assess how many actions have adapter support for recovery."""
        if self._evidence_repo is None or not actions:
            return 0.0 if actions else 1.0

        total = len(actions)
        covered = 0

        for action in actions:
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            if evidence is not None and evidence.recovery_adapter_type.value != "unsupported":
                covered += 1

        return covered / total if total > 0 else 0.0

    async def _assess_dependency_certainty(
        self, tenant_id: str, plan_id: str, actions: list[Any]
    ) -> float:
        """Assess how many actions have complete dependency evidence."""
        if self._evidence_repo is None or not actions:
            return 0.0 if actions else 1.0

        total = len(actions)
        certain = 0

        for action in actions:
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            if evidence is not None:
                if evidence.dependency_edges:
                    certain += 1
                elif evidence.recovery_adapter_type.value == "unsupported":
                    pass
                elif len(actions) == 1:
                    certain += 1

        return certain / total if total > 0 else 0.0

    async def _assess_conflicts(self, tenant_id: str, plan_id: str, actions: list[Any]) -> float:
        """Assess conflict weight (0 = no conflicts, 1 = all conflicted)."""
        if self._evidence_repo is None or not actions:
            return 0.0

        total = len(actions)
        conflicted = 0

        for action in actions:
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            if evidence is not None:
                conflict_status = getattr(evidence, "conflict_status", None)
                if conflict_status and conflict_status != ConflictStatus.NO_CONFLICT:
                    conflicted += 1

        return conflicted / total if total > 0 else 0.0

    async def _assess_irreversibility(
        self, tenant_id: str, plan_id: str, actions: list[Any]
    ) -> float:
        """Assess irreversibility penalty (0 = no irreversible, 1 = all irreversible)."""
        if not actions:
            return 0.0

        total = len(actions)
        irreversible = 0
        unknown = 0

        for action in actions:
            rev = (
                Reversibility.normalize(action.reversibility)
                if hasattr(action, "reversibility")
                else Reversibility.UNKNOWN
            )
            if rev == Reversibility.IRREVERSIBLE:
                irreversible += 1
            elif rev == Reversibility.UNKNOWN:
                unknown += 1

        if irreversible > 0:
            return 0.5 + (0.5 * irreversible / total)
        if unknown > 0:
            return 0.3 + (0.2 * unknown / total)
        return 0.0

    async def _assess_external_side_effects(
        self, tenant_id: str, plan_id: str, actions: list[Any]
    ) -> float:
        """Assess external side-effect accounting (0 = not accounted, 1 = fully accounted)."""
        if self._execution_repo is None or not actions:
            return 0.0 if actions else 1.0

        total = len(actions)
        if total == 0:
            return 1.0

        steps, _ = await self._execution_repo.list_by_plan(tenant_id, plan_id, limit=500)
        steps_with_outcomes = 0
        for step in steps:
            if step.compensation_payload.get("external_outcome") is not None:
                steps_with_outcomes += 1

        return steps_with_outcomes / total

    async def _assess_adapter_reliability(
        self, tenant_id: str, plan_id: str, actions: list[Any]
    ) -> float:
        """Assess adapter reliability based on capability declarations."""
        if not actions:
            return 1.0

        total = len(actions)
        reliable = 0

        for action in actions:
            evidence = None
            if self._evidence_repo is not None:
                evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)

            if evidence is not None:
                from app.domain.entities.surgical_recovery_types import AdapterCapability

                capability = evidence.adapter_capability
                if capability in (
                    AdapterCapability.PRODUCTION_VALIDATED,
                    AdapterCapability.SIMULATION_CAPABLE,
                ):
                    reliable += 1
            else:
                if hasattr(action, "reversibility"):
                    rev = Reversibility.normalize(action.reversibility)
                    if rev != Reversibility.UNKNOWN:
                        reliable += 1

        return reliable / total if total > 0 else 0.0

    async def _assess_unresolved_uncertainty(
        self, tenant_id: str, plan_id: str, actions: list[Any]
    ) -> float:
        """Assess unresolved uncertainty (0 = no uncertainty, 1 = all uncertain)."""
        if not actions:
            return 0.0

        total = len(actions)
        unknown_reversibility = 0
        unknown_outcome_steps = 0

        for action in actions:
            rev = (
                Reversibility.normalize(action.reversibility)
                if hasattr(action, "reversibility")
                else Reversibility.UNKNOWN
            )
            if rev == Reversibility.UNKNOWN:
                unknown_reversibility += 1

        if self._execution_repo is not None:
            steps, _ = await self._execution_repo.list_by_plan(tenant_id, plan_id, limit=500)
            for step in steps:
                if step.execution_state == ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value:
                    unknown_outcome_steps += 1

        uncertain = unknown_reversibility + unknown_outcome_steps
        return min(1.0, uncertain / total) if total > 0 else 0.0

    def _compute_weighted_score(
        self,
        sub_scores: dict[str, float],
        execution_assessment: ExecutionAssessment,
        verification_assessment: VerificationAssessment,
    ) -> float:
        """Compute the composite weighted score."""
        weights = {
            "evidence_completeness": 0.15,
            "state_certainty": 0.10,
            "recovery_coverage": 0.15,
            "dependency_certainty": 0.10,
            "conflict_weight": 0.05,
            "irreversibility": 0.10,
            "external_side_effects": 0.10,
            "verification_coverage": 0.15,
            "adapter_reliability": 0.10,
            "unresolved_uncertainty_penalty": 0.15,
        }

        weighted = sum(sub_scores[k] * weights[k] for k in weights)

        exec_bonus = 0.0
        if execution_assessment.execution_complete:
            exec_bonus = 0.05
        elif execution_assessment.execution_rate > 0:
            exec_bonus = 0.02 * execution_assessment.execution_rate

        verify_bonus = 0.0
        if verification_assessment.all_verified:
            verify_bonus = 0.05
        elif verification_assessment.verification_rate > 0:
            verify_bonus = 0.02 * verification_assessment.verification_rate

        score = min(1.0, weighted + exec_bonus + verify_bonus)
        return round(score, 4)

    def _should_block_recovery_claim(
        self,
        execution_assessment: ExecutionAssessment,
        verification_assessment: VerificationAssessment,
        unresolved_uncertainty: float,
        irreversibility_penalty: float,
    ) -> bool:
        """Determine if recovery cannot be safely claimed."""
        if execution_assessment.unknown_outcome_steps > 0:
            return True
        if not verification_assessment.all_verified:
            return True
        if unresolved_uncertainty > 0.0:
            return True
        if execution_assessment.failed_steps > 0:
            return True
        return execution_assessment.blocked_steps > 0

    def _determine_band(self, score: float, cannot_claim_recovered: bool) -> str:
        """Determine the confidence band label."""
        if cannot_claim_recovered:
            if score >= self.HIGH_THRESHOLD:
                return "HIGH"
            if score >= self.MEDIUM_THRESHOLD:
                return "MEDIUM"
            if score >= self.LOW_THRESHOLD:
                return "LOW"
            return "INSUFFICIENT"

        if score >= self.HIGH_THRESHOLD:
            return "HIGH"
        if score >= self.MEDIUM_THRESHOLD:
            return "MEDIUM"
        if score >= self.LOW_THRESHOLD:
            return "LOW"
        return "INSUFFICIENT"

    async def score_recovery_report(
        self,
        tenant_id: str,
        report_id: str,
        actions: list[Any] | None = None,
    ) -> RecoveryScore:
        """Score a recovery based on an existing RecoveryReport."""
        actions = actions or []
        plan_id = ""

        if self._report_repo is not None:
            report = await self._report_repo.get_by_report_id(tenant_id, report_id)
            if report is not None:
                plan_id = report.plan_id

        return await self.score_plan_recovery(tenant_id, plan_id, actions)

    async def quick_score(
        self,
        tenant_id: str,
        plan_id: str,
        executed_steps: int,
        failed_steps: int,
        verified_steps: int,
        unknown_steps: int,
        evidence_count: int,
        total_actions: int,
        irreversible_count: int = 0,
        conflict_count: int = 0,
        adapter_reliability: float = 1.0,
        external_side_effects_accounted: int = 0,
        external_side_effects_total: int = 0,
    ) -> RecoveryScore:
        """Compute a recovery score from explicit parameters.

        This is useful for callers that have already aggregated the
        relevant metrics and want a deterministic score without
        pulling from repositories.
        """
        all_executed = executed_steps == total_actions and failed_steps == 0
        execution_rate = executed_steps / total_actions if total_actions > 0 else 0.0

        if total_actions > 0:
            verification_rate = verified_steps / executed_steps if executed_steps > 0 else 0.0
        else:
            verification_rate = 1.0

        all_verified = (
            verified_steps == executed_steps
            and verified_steps == total_actions
            and unknown_steps == 0
            and failed_steps == 0
            and total_actions > 0
        )

        evidence_completeness = evidence_count / total_actions if total_actions > 0 else 0.0
        irreversibility_penalty = (
            (irreversible_count / total_actions) if total_actions > 0 else 0.0
        ) * 0.5

        if total_actions > 0:
            external_side_effect_score = (
                external_side_effects_accounted / external_side_effects_total
                if external_side_effects_total > 0
                else 1.0
            )
        else:
            external_side_effect_score = 1.0

        conflict_weight = conflict_count / total_actions if total_actions > 0 else 0.0

        unresolved_uncertainty = (
            (unknown_steps + irreversible_count) / total_actions if total_actions > 0 else 0.0
        )

        state_certainty = evidence_completeness
        recovery_coverage = evidence_completeness

        execution_assessment = ExecutionAssessment(
            total_steps=total_actions,
            executed_steps=executed_steps,
            failed_steps=failed_steps,
            blocked_steps=0,
            manual_steps=0,
            unknown_outcome_steps=unknown_steps,
            execution_rate=execution_rate,
            execution_complete=all_executed and unknown_steps == 0,
            partial_details={
                "executed_steps": executed_steps,
                "failed_steps": failed_steps,
                "unknown_steps": unknown_steps,
            },
        )

        verification_assessment = VerificationAssessment(
            verified_steps=verified_steps,
            unverified_steps=max(0, executed_steps - verified_steps),
            failed_steps=failed_steps,
            unknown_outcome_steps=unknown_steps,
            manual_required_steps=0,
            total_verifiable=executed_steps,
            verification_rate=verification_rate,
            all_verified=all_verified,
            verification_details={
                "verified_steps": verified_steps,
                "executed_steps": executed_steps,
            },
        )

        sub_scores = {
            "evidence_completeness": evidence_completeness,
            "state_certainty": state_certainty,
            "recovery_coverage": recovery_coverage,
            "dependency_certainty": 0.5,
            "conflict_weight": 1.0 - conflict_weight,
            "irreversibility": 1.0 - irreversibility_penalty,
            "external_side_effects": external_side_effect_score,
            "verification_coverage": verification_rate,
            "adapter_reliability": adapter_reliability,
            "unresolved_uncertainty_penalty": 1.0 - unresolved_uncertainty,
        }

        weighted_score = self._compute_weighted_score(
            sub_scores, execution_assessment, verification_assessment
        )

        cannot_claim = self._should_block_recovery_claim(
            execution_assessment,
            verification_assessment,
            unresolved_uncertainty,
            irreversibility_penalty,
        )

        band = self._determine_band(weighted_score, cannot_claim)

        factors = [f"score={weighted_score:.4f}", f"band={band}"]
        recommendations: list[str] = []
        limitations: list[str] = []

        if cannot_claim:
            limitations.append(
                "Recovery cannot be claimed: verification or uncertainty criteria not met"
            )

        if evidence_completeness < 0.5:
            limitations.append(f"Evidence completeness low ({evidence_completeness:.2f})")
            recommendations.append("Capture before-state references for all actions")

        if not all_verified:
            limitations.append("Not all executed steps verified")
            recommendations.append("Verify all recovery steps independently")

        if unknown_steps > 0:
            limitations.append(f"{unknown_steps} steps have unknown external outcome")
            recommendations.append("Resolve unknown external outcomes")

        if irreversibility_penalty and irreversible_count > 0:
            limitations.append(f"{irreversible_count} irreversible actions present")
            recommendations.append("Manual recovery required for irreversible actions")

        return RecoveryScore(
            score=weighted_score,
            band=band,
            execution_assessment=execution_assessment,
            verification_assessment=verification_assessment,
            confidence=None,
            factors=factors,
            recommendations=recommendations,
            limitations=limitations,
            scored_at=datetime.now(UTC),
            evidence_integrity_score=evidence_completeness,
            state_certainty=state_certainty,
            recovery_coverage=recovery_coverage,
            dependency_certainty=0.5,
            conflict_weight=conflict_weight,
            irreversibility_penalty=irreversibility_penalty,
            external_side_effect_score=external_side_effect_score,
            verification_coverage=verification_rate,
            adapter_reliability=adapter_reliability,
            unresolved_uncertainty=unresolved_uncertainty,
            cannot_claim_recovered=cannot_claim,
            score_metadata={
                "score_id": hashlib.sha256(
                    f"{tenant_id}:{plan_id}:{weighted_score:.6f}".encode()
                ).hexdigest()[:16],
                "method": "quick_score",
                "plan_id": plan_id,
                "tenant_id": tenant_id,
            },
        )

    async def score_plan(
        self,
        tenant_id: str,
        plan_id: str,
        steps: list[DurableExecutionStep] | None = None,
        coordination_state: PlanCoordinationState | None = None,
    ) -> RecoveryScore:
        """Score a recovery plan from in-memory step data.

        This is useful for callers that already have the step data
        and don't want to go through the repository.
        """
        if steps is None:
            steps = []

        executed_steps = sum(
            1 for s in steps if s.execution_state == ExecutionState.SUCCEEDED.value
        )
        failed_steps = sum(1 for s in steps if s.execution_state == ExecutionState.FAILED.value)
        unknown_steps = sum(
            1 for s in steps if s.execution_state == ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value
        )
        total_actions = len(steps)

        verified_steps = sum(1 for s in steps if s.verification_passed)

        return await self.quick_score(
            tenant_id=tenant_id,
            plan_id=plan_id,
            executed_steps=executed_steps,
            failed_steps=failed_steps,
            verified_steps=verified_steps,
            unknown_steps=unknown_steps,
            evidence_count=executed_steps,
            total_actions=total_actions,
        )


__all__ = [
    "ExecutionAssessment",
    "RecoveryScore",
    "RecoveryScoreService",
    "VerificationAssessment",
]
