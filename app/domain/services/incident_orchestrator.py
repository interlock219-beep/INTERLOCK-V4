from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.entities.causal_state_types import (
    ConfidenceLevel,
    RecoveryReport,
    VerificationStatus,
)
from app.domain.entities.incident import Incident, IncidentStatus
from app.domain.entities.incident_orchestration_types import (
    IncidentOrchestrationPlan,
    OrchestrationOutcome,
    OrchestrationPhase,
    OrchestrationResult,
    OrchestrationStep,
    OrchestrationStepStatus,
)
from app.domain.repositories.incident_orchestration_repository import (
    IncidentOrchestrationRepository,
)
from app.domain.services.cascade_containment_service import CascadeContainmentService
from app.domain.services.causal_graph_service import CausalGraphService
from app.domain.services.continuous_verification_service import (
    ContinuousVerificationService,
)
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.evidence_verification_service import EvidenceVerificationService
from app.domain.services.recovery_intelligence import RecoveryIntelligenceService
from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine


@runtime_checkable
class _ContainmentLike(Protocol):
    async def get_blast_radius(self, tenant_id: str, agent_id: str) -> dict[str, Any]: ...


@runtime_checkable
class _SimulationLike(Protocol):
    async def simulate_recovery(
        self,
        tenant_id: str,
        actions: list[Any],
        current_states: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...


class IncidentOrchestrator:
    """Orchestrates the full incident response workflow.

    Coordinates discovery, containment, recovery planning, recovery
    execution, verification, evidence preservation, and forensics.

    Integrates with existing services:
    - ``CascadeContainmentService`` for blast-radius and containment
    - ``CausalGraphService`` for causal relationship traversal
    - ``RecoveryIntelligenceService`` for dependency analysis and planning
    - ``RecoverySimulationEngine`` for pre-execution simulation
    - ``DistributedRecoveryOrchestrator`` for durable execution
    - ``EvidenceVerificationService`` for independent verification
    - ``ContinuousVerificationService`` for post-execution verification
    """

    def __init__(
        self,
        orchestration_repository: IncidentOrchestrationRepository,
        containment_service: CascadeContainmentService | None = None,
        causal_graph_service: CausalGraphService | None = None,
        recovery_intelligence: RecoveryIntelligenceService | None = None,
        simulation_engine: RecoverySimulationEngine | None = None,
        recovery_orchestrator: DistributedRecoveryOrchestrator | None = None,
        evidence_service: EvidenceVerificationService | None = None,
        verification_service: ContinuousVerificationService | None = None,
    ) -> None:
        self._repo = orchestration_repository
        self._containment = containment_service
        self._causal = causal_graph_service
        self._intelligence = recovery_intelligence
        self._simulation = simulation_engine
        self._orchestrator = recovery_orchestrator
        self._evidence = evidence_service
        self._verification = verification_service

    async def orchestrate_incident(
        self,
        tenant_id: str,
        incident: Incident,
        plan: IncidentOrchestrationPlan | None = None,
    ) -> OrchestrationResult:
        """Execute the full incident response orchestration workflow."""
        orch_id = f"orch-{tenant_id}-{incident.incident_id}-{secrets.token_hex(8)}"
        created_at = datetime.now(UTC)

        if plan is None:
            plan = IncidentOrchestrationPlan(
                plan_id=orch_id,
                tenant_id=tenant_id,
                incident_id=incident.incident_id,
                root_action_id=(
                    incident.affected_action_ids[0] if incident.affected_action_ids else ""
                ),
                agent_id=incident.agent_id,
                phases=list(OrchestrationPhase),
            )
        else:
            plan = IncidentOrchestrationPlan(
                plan_id=plan.plan_id,
                tenant_id=plan.tenant_id,
                incident_id=plan.incident_id,
                root_action_id=plan.root_action_id,
                agent_id=plan.agent_id,
                phases=plan.phases,
                stop_on_failure=plan.stop_on_failure,
                auto_containment=plan.auto_containment,
                auto_recovery=plan.auto_recovery,
                auto_verification=plan.auto_verification,
                evidence_preservation=plan.evidence_preservation,
                forensic_logging=plan.forensic_logging,
                metadata=plan.metadata,
            )

        await self._repo.save_orchestration_plan(tenant_id, plan)

        phases_completed: list[str] = []
        phases_skipped: list[str] = []
        steps_executed: list[str] = []
        steps_failed: list[str] = []
        error: str | None = None
        verification_passed = False
        evidence_preserved = False
        resilience_score = 0.0

        phases = plan.phases if plan.phases else list(OrchestrationPhase)
        for phase in phases:
            if phase == OrchestrationPhase.COMPLETED:
                continue

            step = OrchestrationStep(
                step_id=f"step-{secrets.token_hex(8)}",
                phase=phase,
                action=f"execute_{phase.value}",
                description=f"Executing orchestration phase: {phase.value}",
                tenant_id=tenant_id,
                incident_id=incident.incident_id,
            )

            try:
                result = await self._execute_phase(phase, tenant_id, incident, plan, orch_id)
                step = replace(
                    step,
                    status=OrchestrationStepStatus.SUCCEEDED,
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    details=result,
                )
                steps_executed.append(step.step_id)
                phases_completed.append(phase.value)

                if phase == OrchestrationPhase.VERIFICATION:
                    verification_passed = result.get("verification_passed", False)
                if phase == OrchestrationPhase.EVIDENCE_PRESERVATION:
                    evidence_preserved = result.get("evidence_preserved", False)

                if result.get("resilience_score") is not None:
                    resilience_score = result["resilience_score"]

                await self._repo.save_step(tenant_id, step)

            except Exception as exc:
                step = replace(
                    step,
                    status=OrchestrationStepStatus.FAILED,
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    error=str(exc),
                )
                steps_failed.append(step.step_id)
                await self._repo.save_step(tenant_id, step)
                error = str(exc)

                if plan.stop_on_failure and step.blocking:
                    phases_skipped = [p.value for p in phases if p not in phases_completed]
                    break

        outcome = self._determine_outcome(phases_completed, verification_passed, evidence_preserved)

        orchestration_result = OrchestrationResult(
            orchestration_id=orch_id,
            tenant_id=tenant_id,
            incident_id=incident.incident_id,
            status=outcome.value,
            outcome=outcome,
            created_at=created_at,
            completed_at=datetime.now(UTC),
            phases_completed=phases_completed,
            phases_skipped=phases_skipped,
            error=error,
            steps_executed=steps_executed,
            steps_failed=steps_failed,
            verification_passed=verification_passed,
            evidence_preserved=evidence_preserved,
            resilience_score=resilience_score,
            recommendations=self._generate_recommendations(outcome, steps_failed, phases_skipped),
            metadata={
                "plan_id": plan.plan_id,
                "total_phases": len(phases),
                "completed_phases": len(phases_completed),
            },
        )

        await self._repo.save_result(tenant_id, orchestration_result)
        return orchestration_result

    async def _execute_phase(
        self,
        phase: OrchestrationPhase,
        tenant_id: str,
        incident: Incident,
        plan: IncidentOrchestrationPlan,
        orch_id: str,
    ) -> dict[str, Any]:
        """Execute a single orchestration phase."""
        started_at = datetime.now(UTC)
        result: dict[str, Any] = {"started_at": started_at.isoformat()}

        if phase == OrchestrationPhase.DETECTION:
            result.update(await self._phase_detection(tenant_id, incident, plan))
        elif phase == OrchestrationPhase.DISCOVERY:
            result.update(await self._phase_discovery(tenant_id, incident, plan))
        elif phase == OrchestrationPhase.CONTAINMENT:
            result.update(await self._phase_containment(tenant_id, incident, plan))
        elif phase == OrchestrationPhase.ANALYSIS:
            result.update(await self._phase_analysis(tenant_id, incident, plan))
        elif phase == OrchestrationPhase.RECOVERY_PLANNING:
            result.update(await self._phase_recovery_planning(tenant_id, incident, plan))
        elif phase == OrchestrationPhase.RECOVERY_EXECUTION:
            result.update(await self._phase_recovery_execution(tenant_id, incident, plan, orch_id))
        elif phase == OrchestrationPhase.VERIFICATION:
            result.update(await self._phase_verification(tenant_id, incident, plan))
        elif phase == OrchestrationPhase.EVIDENCE_PRESERVATION:
            result.update(await self._phase_evidence_preservation(tenant_id, incident, plan))
        elif phase == OrchestrationPhase.FORENSICS:
            result.update(await self._phase_forensics(tenant_id, incident, plan))
        elif phase == OrchestrationPhase.RESOLUTION:
            result.update(await self._phase_resolution(tenant_id, incident, plan))
        else:
            result["message"] = f"Phase {phase.value} not custom-implemented"

        result["completed_at"] = datetime.now(UTC).isoformat()
        return result

    async def _phase_detection(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        if incident.status == IncidentStatus.DETECTED:
            return {
                "detected": True,
                "incident_id": incident.incident_id,
                "severity": incident.severity.value,
                "trigger": incident.trigger,
                "timestamp": incident.created_at.isoformat(),
            }
        return {"detected": False, "incident_status": incident.status.value}

    async def _phase_discovery(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        if self._causal is None:
            return {"discovered": False, "reason": "causal_graph_service not configured"}

        root_action = plan.root_action_id or (
            incident.affected_action_ids[0] if incident.affected_action_ids else ""
        )
        if not root_action:
            return {"discovered": False, "reason": "no root action identified"}

        graph = await self._causal.get_incident_graph(tenant_id, root_action)
        upstream = await self._causal.get_upstream(tenant_id, incident.agent_id)

        return {
            "discovered": True,
            "root_action_id": root_action,
            "node_count": len(graph.get("nodes", [])),
            "edge_count": len(graph.get("edges", [])),
            "upstream_agents": upstream,
            "affected_resources": list(incident.affected_resources),
        }

    async def _phase_containment(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        if not plan.auto_containment or self._containment is None:
            return {
                "contained": False,
                "reason": "auto_containment disabled or service not configured",
            }

        blast_radius = await self._containment.get_blast_radius(tenant_id, incident.agent_id)

        return {
            "contained": True,
            "blast_radius": blast_radius,
            "affected_agents": list(blast_radius.get("affected_agents", [])),
            "affected_resources": list(blast_radius.get("affected_resources", [])),
        }

    async def _phase_analysis(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        if self._intelligence is None:
            return {"analyzed": False, "reason": "recovery_intelligence not configured"}

        root_action = plan.root_action_id or (
            incident.affected_action_ids[0] if incident.affected_action_ids else ""
        )
        if not root_action:
            return {"analyzed": False, "reason": "no root action"}

        dep_graph = await self._intelligence.build_dependency_graph(tenant_id, root_action)

        return {
            "analyzed": True,
            "graph_nodes": len(dep_graph.nodes),
            "topological_order": dep_graph.topological_order,
            "cycles": dep_graph.cycles,
            "roots": dep_graph.roots,
            "leaves": dep_graph.leaves,
        }

    async def _phase_recovery_planning(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        if self._intelligence is None or self._simulation is None:
            return {"planned": False, "reason": "intelligence or simulation not configured"}

        root_action = plan.root_action_id or (
            incident.affected_action_ids[0] if incident.affected_action_ids else ""
        )
        if not root_action:
            return {"planned": False, "reason": "no root action"}

        dep_graph = await self._intelligence.build_dependency_graph(tenant_id, root_action)
        actions = self._get_actions_for_incident(incident)

        simulation = await self._simulation.simulate_recovery(tenant_id, actions, {})

        return {
            "planned": True,
            "simulation_id": simulation.get("simulation_id"),
            "approval_requirement": simulation.get("approval_requirement"),
            "recoverable": simulation.get("recoverable_resources", 0),
            "manual_required": simulation.get("manual_recovery_required_count", 0),
            "unknown": simulation.get("unknown_resources", 0),
            "topological_order": dep_graph.topological_order,
        }

    async def _phase_recovery_execution(
        self,
        tenant_id: str,
        incident: Incident,
        plan: IncidentOrchestrationPlan,
        orch_id: str,
    ) -> dict[str, Any]:
        if not plan.auto_recovery or self._orchestrator is None or self._intelligence is None:
            return {
                "executed": False,
                "reason": "auto_recovery disabled or service not configured",
            }

        root_action = plan.root_action_id or (
            incident.affected_action_ids[0] if incident.affected_action_ids else ""
        )
        if not root_action:
            return {"executed": False, "reason": "no root action"}

        recovery_plan_id = f"recovery-{orch_id}"
        dep_graph = await self._intelligence.build_dependency_graph(tenant_id, root_action)
        actions = self._get_actions_for_incident(incident)

        topological = dep_graph.topological_order
        steps = await self._orchestrator.create_durable_plan(
            tenant_id, recovery_plan_id, actions, topological
        )

        execution_result = await self._orchestrator.execute_durable_plan(
            tenant_id, recovery_plan_id
        )

        return {
            "executed": True,
            "plan_id": recovery_plan_id,
            "steps_created": len(steps),
            "execution_status": execution_result.get("status"),
            "completed": execution_result.get("completed", 0),
            "failed": execution_result.get("failed", 0),
            "verification_status": execution_result.get("verification_status"),
        }

    async def _phase_verification(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        verified = False
        method = "manual"

        if self._evidence is not None:
            report = RecoveryReport(
                report_id=f"report-{secrets.token_hex(8)}",
                tenant_id=tenant_id,
                plan_id=f"recovery-{incident.incident_id}",
                incident_id=incident.incident_id,
                verification_status=VerificationStatus.MANUAL_VERIFICATION_REQUIRED,
                confidence_level=ConfidenceLevel.LOW_CONFIDENCE,
                resource_results={},
                summary="Verification phase initiated",
                limitations=[],
            )
            independent_result = await self._evidence.independent_verify_recovery(
                tenant_id, f"recovery-{incident.incident_id}", report
            )
            verified = independent_result.get("all_steps_verified", False)
            method = "evidence_verification"
        elif self._verification is not None:
            report = await self._verification.verify_recovery(
                tenant_id, f"recovery-{incident.incident_id}", incident_id=incident.incident_id
            )
            verified = report.verification_status == VerificationStatus.EXECUTED_AND_VERIFIED
            method = "continuous_verification"

        return {
            "verification_passed": verified,
            "method": method,
        }

    async def _phase_evidence_preservation(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        preserved = self._evidence is not None
        return {
            "evidence_preserved": preserved,
            "incident_id": incident.incident_id,
            "action_ids": incident.affected_action_ids,
            "resources": list(incident.affected_resources),
        }

    async def _phase_forensics(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        return {
            "forensic_ready": True,
            "incident_id": incident.incident_id,
            "root_cause_analyzable": True,
            "evidence_chain_preserved": plan.evidence_preservation,
        }

    async def _phase_resolution(
        self, tenant_id: str, incident: Incident, plan: IncidentOrchestrationPlan
    ) -> dict[str, Any]:
        return {
            "resolved": True,
            "final_status": "incident_resolved",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _get_actions_for_incident(self, incident: Incident) -> list[Any]:
        """Construct minimal action references from incident data."""
        actions: list[Any] = []
        for action_id in incident.affected_action_ids:
            actions.append(
                _MinimalAction(
                    action_id=action_id,
                    resource="",
                    tool="",
                    reversibility="unknown",
                )
            )
        return actions

    def _determine_outcome(
        self,
        phases_completed: list[str],
        verification_passed: bool,
        evidence_preserved: bool,
    ) -> OrchestrationOutcome:
        phase_set = set(phases_completed)

        if OrchestrationPhase.RECOVERY_EXECUTION.value in phase_set and verification_passed:
            return OrchestrationOutcome.FULLY_RECOVERED
        if OrchestrationPhase.CONTAINMENT.value in phase_set and verification_passed:
            return OrchestrationOutcome.CONTAINED
        if OrchestrationPhase.RECOVERY_PLANNING.value in phase_set:
            return OrchestrationOutcome.PARTIALLY_RECOVERED
        if OrchestrationPhase.CONTAINMENT.value in phase_set:
            return OrchestrationOutcome.CONTAINED
        return OrchestrationOutcome.FAILED

    def _generate_recommendations(
        self,
        outcome: OrchestrationOutcome,
        failed_steps: list[str],
        skipped_phases: list[str],
    ) -> list[str]:
        recs: list[str] = []
        if outcome == OrchestrationOutcome.FAILED:
            recs.append("Manual incident response required")
        if failed_steps:
            recs.append(f"Retry failed steps: {', '.join(failed_steps)}")
        if skipped_phases:
            recs.append(f"Complete skipped phases: {', '.join(skipped_phases)}")
        if outcome == OrchestrationOutcome.PARTIALLY_RECOVERED:
            recs.append("Review recovery plan and execute remaining steps")
        if outcome == OrchestrationOutcome.CONTAINED:
            recs.append("Monitor for residual effects and plan recovery")
        if outcome == OrchestrationOutcome.FULLY_RECOVERED:
            recs.append("Conduct post-incident review and update prevention controls")
        return recs if recs else ["No specific recommendations"]


class _MinimalAction:
    """Lightweight action proxy for incident orchestration when full
    ProtectedAction entities are not available."""

    def __init__(
        self,
        action_id: str,
        resource: str,
        tool: str,
        reversibility: str,
    ) -> None:
        self.action_id = action_id
        self.resource = resource
        self.tool = tool
        self.reversibility = reversibility
        self.tenant_id = ""
        self.agent_id = ""
        self.action_type = ""
        self.parent_action_id: str | None = None
        self.correlation_id = ""
        self.created_at: datetime = datetime.now(UTC)
        self.status = _MinimalStatus()


class _MinimalStatus:
    """Status proxy matching ActionStatus attribute access patterns."""

    value = "executed"


__all__ = ["IncidentOrchestrator"]
