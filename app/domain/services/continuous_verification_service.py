from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.causal_state_types import (
    RecoveryReport,
    VerificationStatus,
)
from app.domain.entities.protected_action import ProtectedAction
from app.domain.repositories.causal_state_repositories import (
    DurableExecutionRepository,
    RecoveryReportRepository,
)
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.services.recovery_adapter import RecoveryAdapter


class ContinuousVerificationService:
    """Continuous verification beyond HTTP 200.

    Recovery does not end when an API returns HTTP 200.
    Every adapter should support verification.

    Verification may include:
    * state comparison
    * version comparison
    * resource existence
    * semantic invariant checks
    * API read-back
    * transaction status
    * event confirmation

    Recovery results must distinguish:
    * EXECUTED_AND_VERIFIED
    * EXECUTED_NOT_VERIFIED
    * EXECUTION_FAILED
    * UNKNOWN_EXTERNAL_OUTCOME
    * MANUAL_VERIFICATION_REQUIRED
    """

    def __init__(
        self,
        evidence_repository: RecoveryEvidenceRepository,
        execution_repository: DurableExecutionRepository,
        report_repository: RecoveryReportRepository,
        adapters: list[RecoveryAdapter] | None = None,
    ) -> None:
        self._evidence_repo = evidence_repository
        self._execution_repo = execution_repository
        self._report_repo = report_repository
        self._adapters = adapters or []

    async def verify_recovery(
        self,
        tenant_id: str,
        plan_id: str,
        incident_id: str = "",
    ) -> RecoveryReport:
        """Verify the full recovery and produce a final report."""
        steps, total = await self._execution_repo.list_by_plan(tenant_id, plan_id, limit=500)

        ai_changes_recovered: list[str] = []
        ai_changes_failed: list[str] = []
        unrelated_preserved: list[str] = []
        manual_required: list[str] = []
        resource_results: dict[str, Any] = {}
        limitations: list[str] = []
        all_verified = True
        any_executed = False

        for step in steps:
            action_id = step.action_id
            result: dict[str, Any] = {
                "action_id": action_id,
                "execution_state": step.execution_state,
            }

            if step.execution_state == "succeeded":
                any_executed = True
                if step.verification_passed:
                    ai_changes_recovered.append(action_id)
                    result["verification"] = "verified"
                    result["status"] = VerificationStatus.EXECUTED_AND_VERIFIED.value
                else:
                    verified = await self._verify_single_action(tenant_id, action_id)
                    if verified:
                        ai_changes_recovered.append(action_id)
                        result["verification"] = "verified_post_hoc"
                        result["status"] = VerificationStatus.EXECUTED_AND_VERIFIED.value
                    else:
                        all_verified = False
                        result["verification"] = "not_verified"
                        result["status"] = VerificationStatus.EXECUTED_NOT_VERIFIED.value
                        limitations.append(
                            f"Action {action_id}: executed but verification inconclusive"
                        )
            elif step.execution_state == "failed":
                ai_changes_failed.append(action_id)
                result["status"] = VerificationStatus.EXECUTION_FAILED.value
                all_verified = False
                limitations.append(f"Action {action_id}: execution failed")
            elif step.execution_state in (
                "blocked_by_drift", "blocked_by_conflict"
            ):
                manual_required.append(action_id)
                result["status"] = VerificationStatus.MANUAL_VERIFICATION_REQUIRED.value
                all_verified = False
                limitations.append(
                    f"Action {action_id}: blocked by {step.execution_state}"
                )
            elif step.execution_state == "requires_manual_action":
                manual_required.append(action_id)
                result["status"] = VerificationStatus.MANUAL_VERIFICATION_REQUIRED.value
                all_verified = False
                limitations.append(f"Action {action_id}: requires manual action")
            elif step.execution_state == "unknown_external_outcome":
                manual_required.append(action_id)
                result["status"] = VerificationStatus.UNKNOWN_EXTERNAL_OUTCOME.value
                all_verified = False
                limitations.append(f"action {action_id}: unknown external outcome")
            else:
                result["status"] = VerificationStatus.MANUAL_VERIFICATION_REQUIRED.value
                all_verified = False

            resource_results[action_id] = result

        verification_status = self._determine_overall_status(
            any_executed=any_executed,
            all_verified=all_verified,
            failed_count=len(ai_changes_failed),
            manual_count=len(manual_required),
            total_steps=total,
        )

        report = RecoveryReport(
            report_id=f"report-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            plan_id=plan_id,
            incident_id=incident_id,
            created_at=datetime.now(UTC),
            ai_changes_recovered=ai_changes_recovered,
            ai_changes_failed=ai_changes_failed,
            unrelated_changes_preserved=unrelated_preserved,
            manual_recovery_required=manual_required,
            verification_status=verification_status,
            resource_results=resource_results,
            summary=self._build_summary(
                recovered=ai_changes_recovered,
                failed=ai_changes_failed,
                manual=manual_required,
                verification_status=verification_status,
            ),
            limitations=limitations,
        )
        return await self._report_repo.save(report)

    async def verify_single_action(
        self, tenant_id: str, action_id: str
    ) -> dict[str, Any]:
        """Verify a single action's recovery outcome."""
        evidence = await self._evidence_repo.get_by_action_id(tenant_id, action_id)
        if evidence is None:
            return {
                "action_id": action_id,
                "verified": False,
                "status": VerificationStatus.MANUAL_VERIFICATION_REQUIRED.value,
                "reason": "No evidence available",
            }

        verified = await self._verify_single_action(tenant_id, action_id)
        return {
            "action_id": action_id,
            "verified": verified,
            "status": (
                VerificationStatus.EXECUTED_AND_VERIFIED.value
                if verified
                else VerificationStatus.EXECUTED_NOT_VERIFIED.value
            ),
        }

    async def _verify_single_action(self, tenant_id: str, action_id: str) -> bool:
        """Run verification adapters for a single action."""
        evidence = await self._evidence_repo.get_by_action_id(tenant_id, action_id)
        if evidence is None:
            return False

        action = ProtectedAction(
            action_id=action_id,
            tenant_id=tenant_id,
            actor_user_id=None,
            agent_id=evidence.agent_id,
            authority_grant_id=evidence.authority_grant_id,
            tool=evidence.target_system,
            resource=evidence.target_resource,
            action_type=evidence.action_type,
        )

        for adapter in self._adapters:
            try:
                if not hasattr(adapter, "verify"):
                    continue
                compensation = await adapter.generate_compensation(action, evidence)
                result = await adapter.verify(compensation)
                return result.verified
            except (AttributeError, TypeError):
                continue
            except Exception:
                return False

        return False

    @staticmethod
    def _determine_overall_status(
        any_executed: bool,
        all_verified: bool,
        failed_count: int,
        manual_count: int,
        total_steps: int,
    ) -> VerificationStatus:
        if total_steps == 0:
            return VerificationStatus.MANUAL_VERIFICATION_REQUIRED
        if any_executed and all_verified and failed_count == 0:
            return VerificationStatus.EXECUTED_AND_VERIFIED
        if any_executed and not all_verified and failed_count == 0:
            return VerificationStatus.EXECUTED_NOT_VERIFIED
        if failed_count > 0 and manual_count == 0:
            return VerificationStatus.EXECUTION_FAILED
        if manual_count > 0:
            return VerificationStatus.MANUAL_VERIFICATION_REQUIRED
        return VerificationStatus.UNKNOWN_EXTERNAL_OUTCOME

    @staticmethod
    def _build_summary(
        recovered: list[str],
        failed: list[str],
        manual: list[str],
        verification_status: VerificationStatus,
    ) -> str:
        parts: list[str] = [f"Verification status: {verification_status.value}"]
        if recovered:
            parts.append(f"Recovered: {len(recovered)} actions")
        if failed:
            parts.append(f"Failed: {len(failed)} actions")
        if manual:
            parts.append(f"Manual recovery required: {len(manual)} actions")
        if not recovered and not failed and not manual:
            parts.append("No actions were processed")
        return "; ".join(parts)
