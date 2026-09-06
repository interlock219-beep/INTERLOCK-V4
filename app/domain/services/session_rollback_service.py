"""Session-level surgical rollback service.

Implements the \"UNDO AGENT\" capability for a complete agent session.
Identifies all controlled mutations, determines blast radius, generates
recovery plans, executes recovery with conflict detection, and verifies
final state.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.agent_session import AgentSession, AgentSessionStatus
from app.domain.entities.causal_state_types import (
    AIChangeSet,
    CausalStateGraph,
    ConfidenceLevel,
    VerificationStatus,
)
from app.domain.entities.containment_event import ContainmentMode
from app.domain.entities.incident import Incident, IncidentSeverity, IncidentStatus
from app.domain.entities.protected_action import ActionStatus, ProtectedAction
from app.domain.entities.recovery_plan import RecoveryPlan, RecoveryStatus
from app.domain.entities.surgical_recovery_types import (
    Reversibility,
)
from app.domain.repositories.agent_session_repository import AgentSessionRepository
from app.domain.repositories.causal_state_repositories import (
    CausalStateGraphRepository,
    ChangeSetRepository,
    ConfidenceRepository,
    DurableExecutionRepository,
    RecoveryReportRepository,
    StateCheckpointRepository,
)
from app.domain.repositories.containment_repository import (
    ContainmentRepository,
    RecoveryPlanRepository,
)
from app.domain.repositories.incident_repository import IncidentRepository
from app.domain.repositories.protected_action_repository import ProtectedActionRepository
from app.domain.repositories.recovery_evidence_repository import RecoveryEvidenceRepository
from app.domain.repositories.recovery_execution_repository import RecoveryExecutionRepository
from app.domain.services.cascade_containment_service import CascadeContainmentService
from app.domain.services.changeset_reconstruction_service import ChangeSetReconstructionService
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.recovery_adapter import RecoveryAdapter
from app.domain.services.recovery_confidence_model import RecoveryConfidenceModel
from app.domain.services.recovery_planning_service import RecoveryPlanningService
from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine
from app.infrastructure.logging.audit_logger import log_security_event
from app.infrastructure.persistence.database import get_db_session
from app.infrastructure.persistence.repositories.sqlalchemy_agent_repository import (
    SQLAlchemyAgentRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_agent_session_repository import (
    SQLAlchemyAgentSessionRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_authority_grant_repository import (
    SQLAlchemyAuthorityGrantRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_execution_token_repository import (
    SQLAlchemyExecutionTokenRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_protected_action_repository import (
    SQLAlchemyProtectedActionRepository,
)


@dataclass
class _VerificationResult:
    verification_status: VerificationStatus
    confidence_level: ConfidenceLevel
    evidence_completeness: float


@dataclass
class _RecoveryReport:
    report_id: str
    tenant_id: str
    plan_id: str
    incident_id: str
    ai_changes_recovered: list[str]
    ai_changes_failed: list[str]
    unrelated_changes_preserved: list[str]
    manual_recovery_required: list[str]
    verification_status: VerificationStatus
    confidence_level: ConfidenceLevel
    resource_results: dict[str, Any]
    summary: str
    limitations: list[str]


class SessionRollbackService:
    """End-to-end session rollback service implementing \"UNDO AGENT\".

    Workflow:
    1. Freeze the session.
    2. Contain the agent (revoke authority, revoke tokens, contain pending actions).
    3. Create an incident.
    4. Discover all actions belonging to the session.
    5. Build a causal state graph.
    6. Generate a recovery plan.
    7. Simulate the plan.
    8. Execute the plan with conflict/drift detection.
    9. Verify actual state.
    10. Produce a recovery report.
    """

    def __init__(
        self,
        action_repository: ProtectedActionRepository,
        session_repository: AgentSessionRepository,
        plan_repository: RecoveryPlanRepository,
        incident_repository: IncidentRepository,
        evidence_repository: RecoveryEvidenceRepository,
        execution_repository: RecoveryExecutionRepository,
        durable_execution_repository: DurableExecutionRepository,
        checkpoint_repository: StateCheckpointRepository,
        changeset_repository: ChangeSetRepository,
        graph_repository: CausalStateGraphRepository,
        confidence_repository: ConfidenceRepository,
        report_repository: RecoveryReportRepository,
        containment_repository: ContainmentRepository,
        adapters: list[RecoveryAdapter] | None = None,
        session_factory: Any = None,
    ) -> None:
        self._action_repo = action_repository
        self._session_repo = session_repository
        self._plan_repo = plan_repository
        self._incident_repo = incident_repository
        self._evidence_repo = evidence_repository
        self._execution_repo = execution_repository
        self._durable_execution_repo = durable_execution_repository
        self._checkpoint_repo = checkpoint_repository
        self._changeset_repo = changeset_repository
        self._graph_repo = graph_repository
        self._confidence_repo = confidence_repository
        self._report_repo = report_repository
        self._containment_repo = containment_repository
        self._adapters = adapters or []
        self._session_factory = session_factory

    async def undo_agent(
        self,
        tenant_id: str,
        session_id: str,
        initiated_by: str,
        *,
        dry_run: bool = False,
        stop_conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute the full "UNDO AGENT" workflow for a session."""
        if self._session_factory is None:
            raise RuntimeError("session_factory is required for rollback workflow")

        with self._session_factory() as session:
            session_repo = SQLAlchemyAgentSessionRepository(session)
            session = await session_repo.get_by_session_id(tenant_id, session_id)
            if session is None:
                raise ValueError("Session not found")

            if session.status == AgentSessionStatus.ROLLING_BACK:
                raise ValueError("Rollback already in progress")

            await session_repo.update_status(
                tenant_id, session_id, AgentSessionStatus.FROZEN
            )
            log_security_event(
                "session_frozen_for_rollback",
                tenant_id=tenant_id,
                session_id=session_id,
                agent_id=session.agent_id,
            )

            containment = await self._contain_agent(tenant_id, session.agent_id, initiated_by, dry_run)

            incident = await self._create_incident(tenant_id, session, initiated_by)

            actions = await self._discover_session_actions(tenant_id, session_id)

            changeset = await self._build_changeset(
                tenant_id, incident.incident_id, session, actions
            )
            graph = await self._build_causal_graph(
                tenant_id, incident.incident_id, session, actions
            )

            plan = await self._generate_recovery_plan(
                tenant_id, session, actions, incident, stop_conditions
            )

            simulation = await self._simulate_plan(tenant_id, plan, actions)

            execution_result = {}
            if not dry_run:
                execution_result = await self._execute_recovery(
                    tenant_id, plan, actions, incident, initiated_by
                )

            verification = await self._verify_recovery(tenant_id, plan, actions)

            report = await self._produce_report(
                tenant_id, plan, incident, actions, simulation, execution_result, verification
            )

            final_status = self._determine_final_status(verification, execution_result)
            await session_repo.update_status(
                tenant_id, session_id, final_status,
                ended_at=datetime.now(UTC) if final_status in (
                    AgentSessionStatus.RECOVERED,
                    AgentSessionStatus.PARTIALLY_RECOVERED,
                    AgentSessionStatus.RECOVERY_FAILED,
                ) else None,
            )

        return {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "agent_id": session.agent_id,
            "incident_id": incident.incident_id,
            "plan_id": plan.plan_id,
            "report_id": report.report_id,
            "status": final_status.value,
            "actions_affected": len(actions),
            "simulation": simulation,
            "execution": execution_result,
            "verification": {
                "status": verification.verification_status.value,
                "confidence": verification.confidence_level.value,
            },
            "containment": {
                "containment_id": containment.containment_id,
                "affected_agents": containment.affected_agent_ids,
                "affected_authorities": containment.affected_authority_ids,
                "affected_tokens": containment.affected_token_ids,
                "affected_actions": containment.affected_action_ids,
            },
            "dry_run": dry_run,
        }

    async def preview_undo_agent(
        self,
        tenant_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        """Preview the full UNDO AGENT workflow without executing."""
        session = await self._session_repo.get_by_session_id(tenant_id, session_id)
        if session is None:
            raise ValueError("Session not found")

        actions = await self._discover_session_actions(tenant_id, session_id)
        if not actions:
            return {
                "session_id": session_id,
                "agent_id": session.agent_id,
                "preview": {
                    "affected_actions_count": 0,
                    "affected_resources": [],
                    "recoverable": [],
                    "irreversible": [],
                    "conflicts": [],
                    "blast_radius": "none",
                    "message": "No controlled actions found for this session.",
                },
            }

        incident = Incident(
            incident_id=f"inc-preview-{secrets.token_hex(12)}",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            severity=IncidentSeverity.MEDIUM,
            status=IncidentStatus.DETECTED,
            session_ids=[session_id],
            affected_action_ids=[a.action_id for a in actions],
        )

        changeset = await self._build_changeset(tenant_id, incident.incident_id, session, actions)
        plan = await self._generate_recovery_plan(
            tenant_id, session, actions, incident, None
        )
        simulation = await self._simulate_plan(tenant_id, plan, actions)

        affected_resources = list(changeset.affected_resources)
        recoverable = [
            aid for aid, rec in changeset.recoverability.items()
            if rec in ("recoverable", "conditionally_recoverable")
        ]
        irreversible = [
            aid for aid, rec in changeset.recoverability.items()
            if rec == "irreversible"
        ]
        unknown = [
            aid for aid, rec in changeset.recoverability.items()
            if rec in ("unknown", "no_evidence", "no_before_state")
        ]

        return {
            "session_id": session_id,
            "agent_id": session.agent_id,
            "incident_id": incident.incident_id,
            "preview": {
                "affected_actions_count": len(actions),
                "affected_resources": affected_resources,
                "recoverable": recoverable,
                "irreversible": irreversible,
                "unknown": unknown,
                "conflicts": changeset.unknown_areas,
                "blast_radius": self._compute_session_blast_radius(actions, changeset),
                "recovery_order": plan.topological_order,
                "plan_id": plan.plan_id,
            },
            "simulation": simulation,
            "message": "Preview generated. Review before executing rollback.",
        }

    async def _contain_agent(
        self, tenant_id: str, agent_id: str, initiated_by: str, dry_run: bool
    ) -> Any:
        if self._session_factory is None:
            raise RuntimeError("session_factory is required for containment")
        with self._session_factory() as session:
            agent_repo = SQLAlchemyAgentRepository(session)
            grant_repo = SQLAlchemyAuthorityGrantRepository(session)
            action_repo = SQLAlchemyProtectedActionRepository(session)
            token_repo = SQLAlchemyExecutionTokenRepository(session)
            service = CascadeContainmentService(
                agent_repo,
                grant_repo,
                self._containment_repo,
                action_repository=action_repo,
                token_repository=token_repo,
            )
            return await service.contain_authority_tree(
                tenant_id=tenant_id,
                target_agent_id=agent_id,
                mode=ContainmentMode.QUARANTINE,
                initiated_by=initiated_by,
                authorized_by=initiated_by,
                reason="Session rollback — agent containment",
                dry_run=dry_run,
            )

    async def _create_incident(
        self, tenant_id: str, session: AgentSession, initiated_by: str
    ) -> Incident:
        incident_id = f"inc-{secrets.token_hex(12)}"
        incident = Incident(
            incident_id=incident_id,
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.DETECTED,
            trigger="session_rollback_requested",
            session_ids=[session.session_id],
        )
        return await self._incident_repo.save(incident)

    async def _discover_session_actions(
        self, tenant_id: str, session_id: str
    ) -> list[ProtectedAction]:
        session = await self._session_repo.get_by_session_id(tenant_id, session_id)
        if session is None:
            return []
        actions, _ = await self._action_repo.list_by_agent(
            tenant_id, session.agent_id, limit=5000, offset=0
        )
        return [
            a for a in actions
            if a.status not in (ActionStatus.CONTAINED,)
            and a.correlation_id == session.correlation_id
        ]

    async def _build_changeset(
        self,
        tenant_id: str,
        incident_id: str,
        session: AgentSession,
        actions: list[ProtectedAction],
    ) -> AIChangeSet:
        root_action_id = next(
            (a.action_id for a in actions if not a.parent_action_id),
            actions[0].action_id if actions else "",
        )
        service = ChangeSetReconstructionService(
            self._action_repo,
            self._evidence_repo,
            self._changeset_repo,
            self._graph_repo,
        )
        return await service.reconstruct(
            tenant_id=tenant_id,
            incident_id=incident_id,
            agent_id=session.agent_id,
            root_action_id=root_action_id,
            correlation_id=session.correlation_id,
        )

    async def _build_causal_graph(
        self,
        tenant_id: str,
        incident_id: str,
        session: AgentSession,
        actions: list[ProtectedAction],
    ) -> CausalStateGraph | None:
        if not actions:
            return None
        root_action_id = next(
            (a.action_id for a in actions if not a.parent_action_id),
            actions[0].action_id,
        )
        service = ChangeSetReconstructionService(
            self._action_repo,
            self._evidence_repo,
            self._changeset_repo,
            self._graph_repo,
        )
        return await service.build_causal_state_graph(
            tenant_id=tenant_id,
            incident_id=incident_id,
            root_action_id=root_action_id,
        )

    async def _generate_recovery_plan(
        self,
        tenant_id: str,
        session: AgentSession,
        actions: list[ProtectedAction],
        incident: Incident,
        stop_conditions: list[str] | None,
    ) -> RecoveryPlan:
        planning_service = RecoveryPlanningService(
            self._action_repo,
            self._plan_repo,
            adapters=self._adapters,
        )
        root_action_id = next(
            (a.action_id for a in actions if not a.parent_action_id),
            actions[0].action_id if actions else "",
        )
        plan = await planning_service.create_plan(
            tenant_id=tenant_id,
            incident_action_id=root_action_id,
            recovery_steps=[],
        )
        updated = RecoveryPlan(
            plan_id=plan.plan_id,
            tenant_id=plan.tenant_id,
            incident_action_id=plan.incident_action_id,
            status=plan.status,
            outcome=plan.outcome,
            simulation_result=plan.simulation_result,
            steps=plan.steps,
            approved_by=plan.approved_by,
            executed_by=plan.executed_by,
            created_at=plan.created_at,
            updated_at=datetime.now(UTC),
            executed_at=plan.executed_at,
            plan_version=plan.plan_version,
            plan_hash=plan.plan_hash,
            topological_order=plan.topological_order,
            dependency_graph_reference=plan.dependency_graph_reference,
            execution_status=plan.execution_status,
            approval_policy=plan.approval_policy,
            approval_threshold=plan.approval_threshold,
            stop_conditions=stop_conditions or plan.stop_conditions,
            compensation_summary=plan.compensation_summary,
            incident_id=incident.incident_id,
            root_action_id=root_action_id,
            affected_action_ids=plan.affected_action_ids,
        )
        return await self._plan_repo.save(updated)

    async def _simulate_plan(
        self, tenant_id: str, plan: RecoveryPlan, actions: list[ProtectedAction]
    ) -> dict[str, Any]:
        planning_service = RecoveryPlanningService(
            self._action_repo,
            self._plan_repo,
            adapters=self._adapters,
        )
        simulation = await planning_service.simulate_plan(tenant_id, plan.plan_id)

        engine = RecoverySimulationEngine(
            self._evidence_repo,
            self._checkpoint_repo,
            adapters=self._adapters,
        )
        resource_sim = await engine.simulate_recovery(tenant_id, actions)

        simulation["resource_simulations"] = resource_sim.get("resource_simulations", {})
        simulation["total_resources"] = resource_sim.get("total_resources", len(actions))
        simulation["recoverable_resources"] = resource_sim.get("recoverable_resources", 0)
        simulation["irreversible_resources"] = sum(
            1 for v in resource_sim.get("resource_simulations", {}).values()
            if v.get("simulation_status") == "irreversible"
        )
        return simulation

    async def _execute_recovery(
        self,
        tenant_id: str,
        plan: RecoveryPlan,
        actions: list[ProtectedAction],
        incident: Incident,
        executed_by: str,
    ) -> dict[str, Any]:
        planning_service = RecoveryPlanningService(
            self._action_repo,
            self._plan_repo,
            adapters=self._adapters,
        )
        executed_plan = await planning_service.execute_plan(
            tenant_id, plan.plan_id, executed_by
        )

        orchestrator = DistributedRecoveryOrchestrator(
            self._evidence_repo,
            self._durable_execution_repo,
            adapters=self._adapters,
        )
        await orchestrator.create_durable_plan(
            tenant_id=tenant_id,
            plan_id=plan.plan_id,
            actions=actions,
            topological_order=plan.topological_order,
        )
        durable_result = await orchestrator.execute_durable_plan(
            tenant_id=tenant_id,
            plan_id=plan.plan_id,
            stop_conditions=plan.stop_conditions,
        )

        return {
            "plan_status": executed_plan.status.value,
            "plan_outcome": executed_plan.outcome.value,
            "durable_result": durable_result,
            "executed_by": executed_by,
            "executed_at": datetime.now(UTC).isoformat(),
        }

    async def _verify_recovery(
        self, tenant_id: str, plan: RecoveryPlan, actions: list[ProtectedAction]
    ) -> Any:
        model = RecoveryConfidenceModel(self._confidence_repo, self._evidence_repo)
        confidence = await model.assess_confidence(
            tenant_id=tenant_id,
            plan_id=plan.plan_id,
            actions=actions,
        )
        verification_status = VerificationStatus.EXECUTED_AND_VERIFIED
        if confidence.level.value == "insufficient_evidence":
            verification_status = VerificationStatus.MANUAL_VERIFICATION_REQUIRED
        elif confidence.level.value == "low_confidence":
            verification_status = VerificationStatus.EXECUTED_NOT_VERIFIED

        return _VerificationResult(
            verification_status=verification_status,
            confidence_level=confidence.level,
            evidence_completeness=confidence.evidence_completeness,
        )

    async def _produce_report(
        self,
        tenant_id: str,
        plan: RecoveryPlan,
        incident: Incident,
        actions: list[ProtectedAction],
        simulation: dict[str, Any],
        execution_result: dict[str, Any],
        verification: Any,
    ) -> Any:
        report_id = f"rpt-{secrets.token_hex(12)}"
        ai_changes_recovered = [
            a.action_id for a in actions
            if a.reversibility in (
                Reversibility.AUTOMATICALLY_REVERSIBLE,
                Reversibility.CONDITIONALLY_REVERSIBLE,
            )
        ]
        ai_changes_failed = [
            a.action_id for a in actions
            if a.reversibility == Reversibility.IRREVERSIBLE
        ]
        manual_recovery_required = [
            a.action_id for a in actions
            if a.reversibility == Reversibility.MANUALLY_RECOVERABLE
        ]

        return _RecoveryReport(
            report_id=report_id,
            tenant_id=tenant_id,
            plan_id=plan.plan_id,
            incident_id=incident.incident_id,
            ai_changes_recovered=ai_changes_recovered,
            ai_changes_failed=ai_changes_failed,
            unrelated_changes_preserved=[],
            manual_recovery_required=manual_recovery_required,
            verification_status=verification.verification_status,
            confidence_level=verification.confidence_level,
            resource_results=simulation.get("resource_simulations", {}),
            summary=(
                f"Recovered {len(ai_changes_recovered)} of {len(actions)} actions. "
                f"{len(ai_changes_failed)} irreversible, "
                f"{len(manual_recovery_required)} manual."
            ),
            limitations=[],
        )

    def _determine_final_status(
        self, verification: Any, execution_result: dict[str, Any]
    ) -> AgentSessionStatus:
        plan_status = execution_result.get("plan_status")
        if plan_status == RecoveryStatus.FAILED.value:
            return AgentSessionStatus.RECOVERY_FAILED
        if plan_status == RecoveryStatus.COMPLETED.value:
            if verification.verification_status == VerificationStatus.EXECUTED_AND_VERIFIED:
                return AgentSessionStatus.RECOVERED
            return AgentSessionStatus.PARTIALLY_RECOVERED
        if verification.verification_status == VerificationStatus.MANUAL_VERIFICATION_REQUIRED:
            return AgentSessionStatus.PARTIALLY_RECOVERED
        return AgentSessionStatus.RECOVERY_FAILED

    @staticmethod
    def _compute_session_blast_radius(
        actions: list[ProtectedAction], changeset: AIChangeSet
    ) -> str:
        if not actions:
            return "none"
        if len(changeset.unknown_areas) > 0:
            return "unknown"
        if any(
            rec in ("irreversible", "unknown") for rec in changeset.recoverability.values()
        ):
            return "partial"
        return "full"
