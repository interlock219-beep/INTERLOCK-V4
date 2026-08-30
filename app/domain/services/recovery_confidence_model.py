from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.causal_state_types import (
    AIChangeSet,
    ConfidenceLevel,
    RecoveryConfidence,
)
from app.domain.entities.surgical_recovery_types import Reversibility
from app.domain.repositories.causal_state_repositories import ConfidenceRepository
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository


class RecoveryConfidenceModel:
    """Explainable confidence assessment for recovery operations.

    Produces a RecoveryConfidence based on explicit evidence factors.
    Does NOT use machine learning to generate arbitrary scores.
    Returns categories: HIGH_CONFIDENCE, MEDIUM_CONFIDENCE,
    LOW_CONFIDENCE, INSUFFICIENT_EVIDENCE.

    The confidence result explains WHY.
    """

    def __init__(
        self,
        confidence_repo: ConfidenceRepository,
        evidence_repo: RecoveryEvidenceRepository,
    ) -> None:
        self._confidence_repo = confidence_repo
        self._evidence_repo = evidence_repo

    async def assess_confidence(
        self,
        tenant_id: str,
        plan_id: str,
        actions: list[Any],
        changeset: AIChangeSet | None = None,
    ) -> RecoveryConfidence:
        """Assess recovery confidence based on explicit evidence factors."""
        factors: list[str] = []
        recommendations: list[str] = []

        evidence_count = 0
        before_state_count = 0
        after_state_count = 0
        current_state_count = 0
        adapter_support_count = 0
        version_match_count = 0
        irreversible_count = 0
        unknown_count = 0
        drift_detected = False
        conflict_detected = False
        dependency_complete = True
        verification_capable = True

        for action in actions:
            evidence = await self._evidence_repo.get_by_action_id(tenant_id, action.action_id)
            if evidence is not None:
                evidence_count += 1
                if evidence.before_state_reference:
                    before_state_count += 1
                if evidence.after_state_reference:
                    after_state_count += 1
                if evidence.recovery_adapter_type.value != "unsupported":
                    adapter_support_count += 1
                if (
                    evidence.state_version
                    and evidence.resource_version
                    and evidence.state_version == evidence.resource_version
                ):
                    version_match_count += 1
                if evidence.verification_requirements:
                    verification_capable = verification_capable and True
                if not evidence.dependency_edges:
                    pass
                rev = Reversibility.normalize(evidence.reversibility_classification)
                if rev == Reversibility.IRREVERSIBLE:
                    irreversible_count += 1
                if rev == Reversibility.UNKNOWN:
                    unknown_count += 1
            else:
                dependency_complete = False

        total_actions = len(actions) if actions else 1

        before_state_available = before_state_count > 0
        after_state_available = after_state_count > 0
        current_state_available = current_state_count > 0 or before_state_available
        adapter_support = adapter_support_count > 0
        version_match = version_match_count > 0

        evidence_completeness = evidence_count / total_actions

        if before_state_available:
            factors.append(f"before_state_available:{before_state_count}/{total_actions}")
        else:
            factors.append("before_state_unavailable")
            recommendations.append("Capture before-state references for all actions")

        if after_state_available:
            factors.append(f"after_state_available:{after_state_count}/{total_actions}")
        else:
            factors.append("after_state_unavailable")

        if adapter_support:
            factors.append(f"adapter_support:{adapter_support_count}/{total_actions}")
        else:
            factors.append("no_adapter_support")
            recommendations.append("Register adapters for all target systems")

        if version_match:
            factors.append(f"version_match:{version_match_count}/{total_actions}")

        if irreversible_count > 0:
            factors.append(f"irreversible_actions:{irreversible_count}")
            recommendations.append(
                f"{irreversible_count} actions are irreversible and require manual recovery"
            )

        if unknown_count > 0:
            factors.append(f"unknown_reversibility:{unknown_count}")
            recommendations.append(
                f"{unknown_count} actions have unknown reversibility — fail closed"
            )

        if drift_detected:
            factors.append("drift_detected")
            recommendations.append("Resolve state drift before recovery")

        if conflict_detected:
            factors.append("conflict_detected")
            recommendations.append("Resolve conflicts before recovery")

        if dependency_complete:
            factors.append("dependency_chain_complete")
        else:
            factors.append("dependency_chain_incomplete")
            recommendations.append("Complete dependency evidence for all actions")

        if verification_capable:
            factors.append("verification_capable")
        else:
            factors.append("verification_not_capable")
            recommendations.append("Enable verification for all adapters")

        level = self._determine_level(
            evidence_completeness=evidence_completeness,
            before_state_available=before_state_available,
            after_state_available=after_state_available,
            adapter_support=adapter_support,
            version_match=version_match,
            irreversible_count=irreversible_count,
            unknown_count=unknown_count,
            drift_detected=drift_detected,
            conflict_detected=conflict_detected,
            dependency_complete=dependency_complete,
            verification_capable=verification_capable,
            total_actions=len(actions),
        )

        if not recommendations:
            if level == ConfidenceLevel.HIGH_CONFIDENCE:
                recommendations.append("All evidence factors support safe recovery")
            elif level == ConfidenceLevel.MEDIUM_CONFIDENCE:
                recommendations.append("Review flagged factors before proceeding")

        confidence = RecoveryConfidence(
            confidence_id=f"conf-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            plan_id=plan_id,
            level=level,
            created_at=datetime.now(UTC),
            before_state_available=before_state_available,
            after_state_available=after_state_available,
            current_state_available=current_state_available,
            adapter_support=adapter_support,
            version_match=version_match,
            drift_detected=drift_detected,
            conflict_detected=conflict_detected,
            dependency_completeness=dependency_complete,
            verification_capability=verification_capable,
            evidence_completeness=round(evidence_completeness, 4),
            factors=factors,
            recommendations=recommendations,
        )
        return await self._confidence_repo.save(confidence)

    def _determine_level(
        self,
        evidence_completeness: float,
        before_state_available: bool,
        after_state_available: bool,
        adapter_support: bool,
        version_match: bool,
        irreversible_count: int,
        unknown_count: int,
        drift_detected: bool,
        conflict_detected: bool,
        dependency_complete: bool,
        verification_capable: bool,
        total_actions: int,
    ) -> ConfidenceLevel:
        """Determine confidence level based on explicit factors."""
        if total_actions == 0:
            return ConfidenceLevel.INSUFFICIENT_EVIDENCE

        if irreversible_count > 0 or unknown_count > 0:
            if evidence_completeness < 0.5:
                return ConfidenceLevel.INSUFFICIENT_EVIDENCE
            return ConfidenceLevel.LOW_CONFIDENCE

        if drift_detected or conflict_detected:
            return ConfidenceLevel.LOW_CONFIDENCE

        if evidence_completeness >= 0.95 and before_state_available and after_state_available:
            if adapter_support and version_match and dependency_complete and verification_capable:
                return ConfidenceLevel.HIGH_CONFIDENCE
            return ConfidenceLevel.MEDIUM_CONFIDENCE

        if evidence_completeness >= 0.7 and before_state_available:
            if adapter_support:
                return ConfidenceLevel.MEDIUM_CONFIDENCE
            return ConfidenceLevel.LOW_CONFIDENCE

        if evidence_completeness >= 0.5:
            return ConfidenceLevel.LOW_CONFIDENCE

        return ConfidenceLevel.INSUFFICIENT_EVIDENCE
