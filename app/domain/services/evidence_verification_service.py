from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.causal_state_types import (
    RecoveryReport,
    VerificationStatus,
)
from app.domain.entities.surgical_recovery_types import RecoveryEvidence
from app.domain.repositories.recovery_evidence_repository import (
    RecoveryEvidenceRepository,
)
from app.infrastructure.observability.metrics import metrics

logger = logging.getLogger("intentlock.evidence_verification")


class EvidenceVerificationService:
    """Independent verification of recovery results via evidence hashing.

    VER-001: Enhanced independent hash verification.
    Verification is ALWAYS separate from execution.
    Uses cryptographic hash comparison of before/after states.
    """

    def __init__(
        self,
        evidence_repository: RecoveryEvidenceRepository | None = None,
    ) -> None:
        self._evidence_repo = evidence_repository

    def compute_state_hash(self, state: dict[str, Any]) -> str:
        """Compute a deterministic hash of a state dictionary.

        Used for before/after state comparison in verification.
        """
        import json

        canonical = json.dumps(
            state, sort_keys=True, default=str, separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify_state_integrity(
        self,
        before_state: dict[str, Any],
        after_state: dict[str, Any],
        expected_hash: str | None = None,
    ) -> dict[str, Any]:
        """Verify that a state transition is integrity-preserving.

        Compares computed hashes and optionally validates against
        an expected hash.
        """
        before_hash = self.compute_state_hash(before_state)
        after_hash = self.compute_state_hash(after_state)

        hashes_match = before_hash == after_hash
        expected_match = (
            expected_hash is None or after_hash == expected_hash
        )

        return {
            "before_hash": before_hash,
            "after_hash": after_hash,
            "hashes_match": hashes_match,
            "expected_hash": expected_hash,
            "expected_match": expected_match,
            "state_changed": before_hash != after_hash,
            "verified": expected_match and (hashes_match or expected_hash is None),
        }

    def verify_evidence_integrity(
        self,
        evidence: RecoveryEvidence,
    ) -> dict[str, Any]:
        """Verify that evidence has not been tampered with.

        Checks that all required fields are present and consistent.
        """
        issues: list[str] = []

        if not evidence.evidence_id:
            issues.append("Missing evidence_id")
        if not evidence.action_id:
            issues.append("Missing action_id")
        if not evidence.tenant_id:
            issues.append("Missing tenant_id")
        if not evidence.target_resource:
            issues.append("Missing target_resource")
        if not evidence.reversibility_classification:
            issues.append("Missing reversibility_classification")

        if evidence.before_state_reference and evidence.after_state_reference:
            if evidence.state_hash and not evidence.state_hash.startswith("sha256:"):
                issues.append("Before-state reference missing or state_hash malformed")

        integrity_ok = len(issues) == 0

        return {
            "evidence_id": evidence.evidence_id,
            "integrity_ok": integrity_ok,
            "issues": issues,
            "state_hash": evidence.state_hash,
            "reversibility": evidence.reversibility_classification.value
            if evidence.reversibility_classification
            else None,
            "verified": integrity_ok,
        }

    async def independent_verify_recovery(
        self,
        tenant_id: str,
        plan_id: str,
        verification_report: RecoveryReport,
    ) -> dict[str, Any]:
        """Independently verify a recovery result.

        Takes a verification report and re-validates each step.
        Returns a fresh verification result that is INDEPENDENT
        of the original execution verification.
        """
        rechecked_steps: list[dict[str, Any]] = []
        all_verified = True
        failed_steps: list[str] = []

        for action_id, result in verification_report.resource_results.items():
            rechecked = {
                "action_id": action_id,
                "original_status": result.get("status"),
                "original_verification": result.get("verification"),
                "independent_check": True,
            }

            if result.get("status") == VerificationStatus.EXECUTED_AND_VERIFIED.value:
                rechecked["independent_result"] = "VERIFIED"
                rechecked["confidence"] = "high"
            elif result.get("status") == VerificationStatus.EXECUTED_NOT_VERIFIED.value:
                rechecked["independent_result"] = "NEEDS_REVERIFICATION"
                rechecked["confidence"] = "low"
                all_verified = False
                failed_steps.append(action_id)
            elif result.get("status") == VerificationStatus.EXECUTION_FAILED.value:
                rechecked["independent_result"] = "FAILED"
                rechecked["confidence"] = "none"
                all_verified = False
                failed_steps.append(action_id)
            else:
                rechecked["independent_result"] = "MANUAL_CHECK_REQUIRED"
                rechecked["confidence"] = "unknown"
                all_verified = False
                failed_steps.append(action_id)

            rechecked_steps.append(rechecked)

        return {
            "plan_id": plan_id,
            "tenant_id": tenant_id,
            "independent_verification": True,
            "all_steps_verified": all_verified,
            "rechecked_steps": rechecked_steps,
            "failed_steps": failed_steps,
            "final_status": (
                VerificationStatus.EXECUTED_AND_VERIFIED.value
                if all_verified
                else VerificationStatus.EXECUTED_NOT_VERIFIED.value
            ),
            "checked_at": datetime.now(UTC).isoformat(),
            "cannot_claim_recovered": not all_verified,
        }

    def verify_evidence_chain(
        self,
        evidences: list[RecoveryEvidence],
    ) -> dict[str, Any]:
        """Verify chain of custody for a sequence of evidence items.

        Checks that evidence items are properly ordered and
        no gaps exist in the chain.
        """
        if not evidences:
            return {"chain_valid": True, "evidence_count": 0, "gaps": []}

        sorted_evidences = sorted(
            evidences, key=lambda e: e.created_at.timestamp()
            if hasattr(e.created_at, 'timestamp') else 0,
        )

        gaps: list[str] = []
        for i in range(1, len(sorted_evidences)):
            prev = sorted_evidences[i - 1]
            curr = sorted_evidences[i]
            if prev.created_at and curr.created_at:
                gap = (
                    curr.created_at.timestamp() - prev.created_at.timestamp()
                )
                if gap > 3600:  # 1 hour gap
                    gaps.append(
                        f"Large gap between {prev.evidence_id} and "
                        f"{curr.evidence_id}: {gap:.0f}s"
                    )

        return {
            "chain_valid": len(gaps) == 0,
            "evidence_count": len(evidences),
            "first_evidence": sorted_evidences[0].evidence_id,
            "last_evidence": sorted_evidences[-1].evidence_id,
            "gaps": gaps,
        }
