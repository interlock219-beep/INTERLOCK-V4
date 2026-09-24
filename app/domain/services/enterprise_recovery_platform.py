from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.enterprise_recovery_types import (
    PlatformOperationResult,
    RecoveryPlatformStatus,
    RecoverySummary,
    ResilienceMetrics,
)
from app.domain.entities.incident import Incident
from app.domain.entities.incident_orchestration_types import (
    OrchestrationOutcome,
    OrchestrationResult,
)
from app.domain.repositories.incident_orchestration_repository import (
    IncidentOrchestrationRepository,
)
from app.domain.services.cascade_containment_service import CascadeContainmentService
from app.domain.services.chaos_simulation_engine import ChaosSimulationEngine
from app.domain.services.continuous_verification_service import (
    ContinuousVerificationService,
)
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.evidence_verification_service import EvidenceVerificationService
from app.domain.services.graph_integration_service import GraphIntegrationService
from app.domain.services.incident_orchestrator import IncidentOrchestrator
from app.domain.services.merkle_audit_log_service import MerkleAuditLogService
from app.domain.services.recovery_intelligence import RecoveryIntelligenceService
from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine
from app.domain.services.self_healing_service import SelfHealingService


class EnterpriseRecoveryPlatform:
    """Unified facade for enterprise-scale AI incident recovery.

    Aggregates all domain services into a single entry point that can
    orchestrate incident detection through resolution, run chaos and
    digital-twin simulations, perform self-healing, and maintain
    resilience metrics.

    All components are optional at construction time; the facade gracefully
    degrades when a component is not configured.
    """

    def __init__(
        self,
        incident_repository: Any = None,
        orchestration_repository: IncidentOrchestrationRepository | None = None,
        forensic_audit_service: MerkleAuditLogService | None = None,
        graph_service: GraphIntegrationService | None = None,
        recovery_intelligence: RecoveryIntelligenceService | None = None,
        simulation_engine: RecoverySimulationEngine | None = None,
        chaos_engine: ChaosSimulationEngine | None = None,
        distributed_orchestrator: DistributedRecoveryOrchestrator | None = None,
        evidence_service: EvidenceVerificationService | None = None,
        verification_service: ContinuousVerificationService | None = None,
        containment_service: CascadeContainmentService | None = None,
        self_healing_service: SelfHealingService | None = None,
    ) -> None:
        self._incident_repo = incident_repository
        self._orchestration_repo = orchestration_repository
        self._forensics = forensic_audit_service
        self._graph = graph_service
        self._intelligence = recovery_intelligence
        self._simulation = simulation_engine
        self._chaos = chaos_engine
        self._distributed = distributed_orchestrator
        self._evidence = evidence_service
        self._verification = verification_service
        self._containment = containment_service
        self._healing = self_healing_service

        self._orchestrator: IncidentOrchestrator | None = None
        self._build_orchestrator()

    def _build_orchestrator(self) -> None:
        """Build the IncidentOrchestrator lazily from available services."""
        if self._orchestration_repo is not None:
            self._orchestrator = IncidentOrchestrator(
                orchestration_repository=self._orchestration_repo,
                containment_service=self._containment,
                causal_graph_service=None,
                recovery_intelligence=self._intelligence,
                simulation_engine=self._simulation,
                recovery_orchestrator=self._distributed,
                evidence_service=self._evidence,
                verification_service=self._verification,
            )

    async def handle_incident(
        self,
        tenant_id: str,
        incident: Incident,
    ) -> PlatformOperationResult:
        """Handle a full incident through the recovery platform."""
        operation_id = f"op-{tenant_id}-{incident.incident_id}-{secrets.token_hex(8)}"
        started_at = datetime.now(UTC)
        components_executed: list[str] = []
        components_succeeded: list[str] = []
        components_failed: list[str] = []
        error: str | None = None
        result_data: dict[str, Any] = {}

        try:
            if self._forensics is not None:
                components_executed.append("forensic_audit")
                from app.domain.entities.forensic_types import (
                    AuditEventSeverity,
                    AuditEventType,
                    AuditLogEntry,
                )
                entry = AuditLogEntry(
                    entry_id=f"audit-{tenant_id}-{incident.incident_id}-{secrets.token_hex(8)}",
                    tenant_id=tenant_id,
                    event_type=AuditEventType.INCIDENT_DETECTED,
                    severity=AuditEventSeverity.CRITICAL,
                    description=f"Incident {incident.incident_id} detected for agent {incident.agent_id}",
                    actor="system",
                    resource_id=incident.agent_id,
                    event_data={
                        "incident_id": incident.incident_id,
                        "severity": incident.severity.value,
                        "agent_id": incident.agent_id,
                        "trigger": incident.trigger,
                    },
                )
                await self._forensics.append_entry(tenant_id, entry)
                components_succeeded.append("forensic_audit")

            if self._orchestrator is not None:
                components_executed.append("incident_orchestration")
                orch_result = await self._orchestrator.orchestrate_incident(tenant_id, incident)
                components_succeeded.append("incident_orchestration")
                result_data["orchestration_result"] = {
                    "outcome": orch_result.outcome.value,
                    "status": orch_result.status,
                    "phases_completed": orch_result.phases_completed,
                    "verification_passed": orch_result.verification_passed,
                    "recommendations": orch_result.recommendations,
                }

            if self._chaos is not None and incident.severity.value in ("critical", "high"):
                components_executed.append("chaos_simulation")
                try:
                    sim_result = await self._run_post_incident_chaos(tenant_id, incident)
                    components_succeeded.append("chaos_simulation")
                    result_data["chaos_result"] = sim_result
                except Exception as exc:
                    components_failed.append("chaos_simulation")
                    result_data["chaos_error"] = str(exc)

            if self._healing is not None:
                components_executed.append("self_healing")
                try:
                    heal_result = await self._trigger_self_healing(tenant_id, incident)
                    components_succeeded.append("self_healing")
                    result_data["healing_result"] = heal_result
                except Exception as exc:
                    components_failed.append("self_healing")
                    result_data["healing_error"] = str(exc)

            if self._graph is not None and self._intelligence is not None:
                components_executed.append("graph_integration")
                try:
                    root_action = (
                        incident.affected_action_ids[0] if incident.affected_action_ids else ""
                    )
                    if root_action:
                        dep_graph = await self._intelligence.build_dependency_graph(
                            tenant_id, root_action
                        )
                        recovery_graph = await self._graph.build_recovery_graph_from_dependencies(
                            tenant_id, incident.incident_id, root_action, dep_graph
                        )
                        consistency = self._graph.check_consistency(recovery_graph)
                        components_succeeded.append("graph_integration")
                        result_data["graph"] = {
                            "node_count": len(recovery_graph.nodes),
                            "edge_count": len(recovery_graph.edges),
                            "consistency": consistency.level.value,
                        }
                except Exception as exc:
                    components_failed.append("graph_integration")
                    result_data["graph_error"] = str(exc)

        except Exception as exc:
            error = str(exc)
            components_failed.extend(
                c for c in components_executed if c not in components_succeeded
            )

        completed_at = datetime.now(UTC)
        duration = (completed_at - started_at).total_seconds()

        if error is not None:
            status = RecoveryPlatformStatus.FAILURE
        elif components_failed:
            status = RecoveryPlatformStatus.PARTIAL_SUCCESS
        else:
            status = RecoveryPlatformStatus.SUCCESS

        return PlatformOperationResult(
            operation_id=operation_id,
            tenant_id=tenant_id,
            status=status,
            created_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            components_executed=components_executed,
            components_succeeded=components_succeeded,
            components_failed=components_failed,
            result_data=result_data,
            recommendations=self._generate_platform_recommendations(
                status, components_failed, result_data
            ),
            error=error,
        )

    async def _run_post_incident_chaos(
        self, tenant_id: str, incident: Incident
    ) -> dict[str, Any]:
        """Run a chaos experiment to validate resilience after an incident."""
        from app.domain.entities.chaos_types import (
            ChaosExperiment,
            ChaosFault,
            ChaosScenario,
            ChaosType,
            DigitalTwin,
            ExperimentStatus,
            FaultInjectionStrategy,
            ScenarioStatus,
            SimulationScenario,
        )

        twin = DigitalTwin(
            twin_id=f"twin-{tenant_id}-{incident.agent_id}-{secrets.token_hex(8)}",
            tenant_id=tenant_id,
            entity_id=incident.agent_id,
            entity_type="agent",
            current_state={"status": incident.status.value},
            failure_modes=[incident.trigger or "unknown_failure"],
            dependencies=incident.affected_action_ids,
            resilience_characteristics={"rating": 0.5},
        )

        scenario = SimulationScenario(
            scenario_id=f"sim-scenario-{secrets.token_hex(8)}",
            tenant_id=tenant_id,
            name="Post-incident resilience simulation",
            twin_id=twin.twin_id,
            description=f"Post-incident simulation for incident {incident.incident_id}",
            initial_conditions={"current_state": twin.current_state},
            injected_events=[
                {"type": incident.trigger or "unknown_failure", "severity": incident.severity.value}
            ],
            expected_outcomes=["failure_expected"],
        )

        sim_result = await self._chaos.run_simulation(tenant_id, twin, scenario)

        return {
            "simulation_id": sim_result.result_id,
            "predictions_matched": sim_result.predictions_matched,
            "resilience_score": sim_result.resilience_score,
            "recommendations": sim_result.mitigation_recommendations,
        }

    async def _trigger_self_healing(
        self, tenant_id: str, incident: Incident
    ) -> dict[str, Any]:
        """Trigger self-healing checks for the affected agent."""
        heal_result = await self._healing.check_health(
            tenant_id,
            incident.agent_id,
            "agent",
        )
        return {
            "health_status": heal_result["overall_health"],
            "actions_taken": heal_result.get("actions_taken", []),
        }

    def _generate_platform_recommendations(
        self,
        status: RecoveryPlatformStatus,
        failed_components: list[str],
        result_data: dict[str, Any],
    ) -> list[str]:
        """Generate high-level recommendations based on platform operation results."""
        recs: list[str] = []
        if status == RecoveryPlatformStatus.FAILURE:
            recs.append("Manual intervention required for incident resolution")
        if failed_components:
            recs.append(f"Review failed components: {', '.join(failed_components)}")
        if "orchestration_result" in result_data:
            orch = result_data["orchestration_result"]
            recs.extend(orch.get("recommendations", []))
        if "chaos_result" in result_data:
            recs.extend(result_data["chaos_result"].get("recommendations", []))
        if not recs:
            recs.append("System operating within expected parameters")
        return recs

    async def get_resilience_metrics(
        self, tenant_id: str, window_hours: int = 24
    ) -> ResilienceMetrics:
        """Aggregate resilience metrics for a tenant."""
        metrics_id = f"metrics-{tenant_id}-{secrets.token_hex(8)}"
        now = datetime.now(UTC)

        values: dict[str, float] = {}
        component_metrics: dict[str, dict[str, float]] = {}

        if self._orchestration_repo is not None:
            results = await self._collect_orchestration_results(tenant_id, window_hours)
            component_metrics["orchestration"] = {
                "total_incidents": float(len(results)),
                "full_recovery_rate": float(
                    sum(
                        1
                        for r in results
                        if r.outcome == OrchestrationOutcome.FULLY_RECOVERED
                    )
                )
                / max(len(results), 1),
                "contained_rate": float(
                    sum(
                        1
                        for r in results
                        if r.outcome == OrchestrationOutcome.CONTAINED
                    )
                )
                / max(len(results), 1),
            }

        if self._healing is not None:
            events = self._healing.get_healing_events(tenant_id, "")
            component_metrics["self_healing"] = {
                "total_events": float(len(events)),
                "recovery_rate": float(
                    sum(1 for e in events if e.resolved) / max(len(events), 1)
                ),
            }

        values = self._compute_overall_values(component_metrics)

        return ResilienceMetrics(
            metrics_id=metrics_id,
            tenant_id=tenant_id,
            created_at=now,
            values=values,
            component_metrics=component_metrics,
        )

    async def _collect_orchestration_results(
        self, tenant_id: str, window_hours: int
    ) -> list[OrchestrationResult]:
        """Collect recent orchestration results from the repository.

        Uses duck-typing to discover results from in-memory implementations.
        """
        results: list[OrchestrationResult] = []
        if self._orchestration_repo is None:
            return results
        internal = getattr(self._orchestration_repo, "_results", None)
        if internal is not None:
            for result in internal.values():
                if result.tenant_id == tenant_id:
                    results.append(result)
        return results

    def _compute_overall_values(
        self, component_metrics: dict[str, dict[str, float]]
    ) -> dict[str, float]:
        """Compute overall metric values from component metrics."""
        values: dict[str, float] = {}
        all_recovery_rates: list[float] = []
        for component, metrics in component_metrics.items():
            for key, val in metrics.items():
                values[f"{component}.{key}"] = val
            if "recovery_rate" in metrics:
                all_recovery_rates.append(metrics["recovery_rate"])
            if "full_recovery_rate" in metrics:
                all_recovery_rates.append(metrics["full_recovery_rate"])

        if all_recovery_rates:
            values["overall_availability"] = sum(all_recovery_rates) / len(all_recovery_rates)
        else:
            values["overall_availability"] = 1.0

        values["overall_resilience"] = values.get("overall_availability", 1.0)
        return values

    async def get_recovery_summary(
        self, tenant_id: str
    ) -> RecoverySummary:
        """Get a high-level recovery summary for a tenant."""
        from app.domain.entities.self_healing_types import HealthStatus

        summary_id = f"summary-{tenant_id}-{secrets.token_hex(8)}"
        now = datetime.now(UTC)

        active_incidents: list[str] = []
        recent_incidents: list[str] = []
        if self._incident_repo is not None:
            incidents, _ = await self._incident_repo.list_by_tenant(
                tenant_id, status=None, limit=100, offset=0
            )
            for inc in incidents:
                recent_incidents.append(inc.incident_id)
                if inc.status.value not in ("resolved", "recovery_failed"):
                    active_incidents.append(inc.incident_id)

        healing_events = self._healing.get_healing_events(tenant_id, "") if self._healing else []

        metrics = await self.get_resilience_metrics(tenant_id)
        resilience_score = metrics.values.get("overall_resilience", 0.5)

        if resilience_score >= 0.9:
            health = HealthStatus.HEALTHY
        elif resilience_score >= 0.7:
            health = HealthStatus.DEGRADED
        elif resilience_score >= 0.5:
            health = HealthStatus.UNHEALTHY
        else:
            health = HealthStatus.CRITICAL

        return RecoverySummary(
            summary_id=summary_id,
            tenant_id=tenant_id,
            created_at=now,
            active_incidents=active_incidents,
            recent_incidents=recent_incidents,
            healing_events=[e.event_id for e in healing_events],
            overall_health=health,
            resilience_score=resilience_score,
        )


__all__ = ["EnterpriseRecoveryPlatform"]
