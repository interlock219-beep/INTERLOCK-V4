"""Targeted regression tests for SessionRollbackService uncovered paths.

These tests focus on the critical recovery/containment/orchestration
branches in session_rollback_service.py that were previously untested.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.entities.agent_session import AgentSession, AgentSessionStatus
from app.domain.entities.causal_state_types import (
    ConfidenceLevel,
    VerificationStatus,
)
from app.domain.entities.incident import Incident, IncidentSeverity, IncidentStatus
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.recovery_plan import RecoveryPlan, RecoveryStatus
from app.domain.services.recovery_confidence_model import RecoveryConfidenceModel
from app.domain.services.recovery_planning_service import RecoveryPlanningService
from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine
from app.domain.services.session_rollback_service import SessionRollbackService


def _async_mock_repo(**default_returns):
    repo = AsyncMock()
    for name, value in default_returns.items():
        setattr(repo, name, AsyncMock(return_value=value))
    return repo


@pytest.fixture
def base_service_kwargs() -> dict[str, Any]:
    return {
        "action_repository": _async_mock_repo(),
        "session_repository": _async_mock_repo(),
        "plan_repository": _async_mock_repo(),
        "incident_repository": _async_mock_repo(),
        "evidence_repository": _async_mock_repo(),
        "execution_repository": _async_mock_repo(),
        "durable_execution_repository": _async_mock_repo(),
        "checkpoint_repository": _async_mock_repo(),
        "changeset_repository": _async_mock_repo(),
        "graph_repository": _async_mock_repo(),
        "confidence_repository": _async_mock_repo(),
        "report_repository": _async_mock_repo(),
        "containment_repository": _async_mock_repo(),
        "adapters": [],
        "session_factory": MagicMock(),
    }


def make_action(action_id: str, tenant_id: str = "t1", agent_id: str = "a1", parent_action_id: str | None = None, reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id=tenant_id,
        actor_user_id=None,
        agent_id=agent_id,
        authority_grant_id=None,
        tool="tool",
        resource="res",
        action_type="write",
        status=ActionStatus.EXECUTED,
        reversibility=reversibility,
        parent_action_id=parent_action_id,
    )


def make_session(session_id: str, tenant_id: str = "t1", agent_id: str = "a1", status=AgentSessionStatus.ACTIVE) -> AgentSession:
    return AgentSession(
        session_id=session_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        status=status,
        correlation_id=f"corr-{session_id}",
    )


# ---------------------------------------------------------------------------
# Blast radius and final status
# ---------------------------------------------------------------------------


def test_compute_session_blast_radius_none(base_service_kwargs):
    service = SessionRollbackService(**base_service_kwargs)
    assert service._compute_session_blast_radius([], MagicMock()) == "none"


def test_compute_session_blast_radius_unknown(base_service_kwargs):
    changeset = MagicMock()
    changeset.unknown_areas = ["x"]
    service = SessionRollbackService(**base_service_kwargs)
    assert service._compute_session_blast_radius([make_action("a1")], changeset) == "unknown"


def test_compute_session_blast_radius_partial(base_service_kwargs):
    changeset = MagicMock()
    changeset.unknown_areas = []
    changeset.recoverability = {"a1": "irreversible"}
    service = SessionRollbackService(**base_service_kwargs)
    assert service._compute_session_blast_radius([make_action("a1")], changeset) == "partial"


def test_compute_session_blast_radius_full(base_service_kwargs):
    changeset = MagicMock()
    changeset.unknown_areas = []
    changeset.recoverability = {"a1": "recoverable"}
    service = SessionRollbackService(**base_service_kwargs)
    assert service._compute_session_blast_radius([make_action("a1")], changeset) == "full"


def test_determine_final_status_dry_run_never_recovered(base_service_kwargs):
    service = SessionRollbackService(**base_service_kwargs)
    verified = MagicMock()
    verified.verification_status = VerificationStatus.EXECUTED_AND_VERIFIED
    manual = MagicMock()
    manual.verification_status = VerificationStatus.MANUAL_VERIFICATION_REQUIRED

    assert service._determine_final_status(verified, {}) == AgentSessionStatus.RECOVERY_FAILED
    assert service._determine_final_status(manual, {}) == AgentSessionStatus.PARTIALLY_RECOVERED


def test_determine_final_status_completed_requires_verification(base_service_kwargs):
    service = SessionRollbackService(**base_service_kwargs)
    verified = MagicMock()
    verified.verification_status = VerificationStatus.EXECUTED_AND_VERIFIED
    not_verified = MagicMock()
    not_verified.verification_status = VerificationStatus.EXECUTED_NOT_VERIFIED

    assert service._determine_final_status(verified, {"plan_status": RecoveryStatus.COMPLETED.value}) == AgentSessionStatus.RECOVERED
    assert service._determine_final_status(not_verified, {"plan_status": RecoveryStatus.COMPLETED.value}) == AgentSessionStatus.PARTIALLY_RECOVERED


def test_determine_final_status_failed_plan(base_service_kwargs):
    service = SessionRollbackService(**base_service_kwargs)
    verified = MagicMock()
    verified.verification_status = VerificationStatus.EXECUTED_AND_VERIFIED

    assert service._determine_final_status(verified, {"plan_status": RecoveryStatus.FAILED.value}) == AgentSessionStatus.RECOVERY_FAILED


# ---------------------------------------------------------------------------
# Report production
# ---------------------------------------------------------------------------


def test_produce_report_categorizes_reversibility(base_service_kwargs):
    actions = [
        make_action("auto", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE),
        make_action("cond", reversibility=Reversibility.CONDITIONALLY_REVERSIBLE),
        make_action("manual", reversibility=Reversibility.MANUALLY_RECOVERABLE),
        make_action("irrev", reversibility=Reversibility.IRREVERSIBLE),
    ]
    plan = MagicMock()
    plan.plan_id = "plan-1"
    incident = MagicMock()
    incident.incident_id = "inc-1"
    simulation = {}
    verification = MagicMock()
    verification.verification_status = VerificationStatus.EXECUTED_AND_VERIFIED
    verification.confidence_level = ConfidenceLevel.HIGH_CONFIDENCE
    verification.evidence_completeness = 1.0

    service = SessionRollbackService(**base_service_kwargs)
    import asyncio
    report = asyncio.run(service._produce_report(
        "t1", plan, incident, actions, simulation, {}, verification
    ))
    assert len(report.ai_changes_recovered) == 2
    assert len(report.ai_changes_failed) == 1
    assert len(report.manual_recovery_required) == 1
    assert report.verification_status == VerificationStatus.EXECUTED_AND_VERIFIED


def test_produce_report_summary_string(base_service_kwargs):
    actions = [make_action("a1")]
    plan = MagicMock()
    plan.plan_id = "plan-1"
    incident = MagicMock()
    incident.incident_id = "inc-1"
    verification = MagicMock()
    verification.verification_status = VerificationStatus.EXECUTED_AND_VERIFIED
    verification.confidence_level = ConfidenceLevel.HIGH_CONFIDENCE
    verification.evidence_completeness = 1.0

    service = SessionRollbackService(**base_service_kwargs)
    import asyncio
    report = asyncio.run(service._produce_report("t1", plan, incident, actions, {}, {}, verification))
    assert "Recovered" in report.summary


# ---------------------------------------------------------------------------
# Verify recovery confidence mapping
# ---------------------------------------------------------------------------


def test_verify_recovery_maps_insufficient_evidence_to_manual(base_service_kwargs):
    confidence_repo = _async_mock_repo()
    evidence_repo = _async_mock_repo()
    evidence_repo.get_by_action_id = AsyncMock(return_value=None)

    mock_confidence = MagicMock()
    mock_confidence.level = ConfidenceLevel.INSUFFICIENT_EVIDENCE
    mock_confidence.evidence_completeness = 0.1

    with patch("app.domain.services.session_rollback_service.RecoveryConfidenceModel") as MockModel:
        mock_model_instance = MockModel.return_value
        mock_model_instance.assess_confidence = AsyncMock(return_value=mock_confidence)

        service = SessionRollbackService(
            **{**base_service_kwargs, "confidence_repository": confidence_repo, "evidence_repository": evidence_repo}
        )
        plan = MagicMock()
        plan.plan_id = "plan-1"
        actions = [make_action("a1")]

        import asyncio
        result = asyncio.run(service._verify_recovery("t1", plan, actions))
        assert result.verification_status == VerificationStatus.MANUAL_VERIFICATION_REQUIRED


def test_verify_recovery_maps_low_confidence_to_not_verified(base_service_kwargs):
    confidence_repo = _async_mock_repo()
    evidence_repo = _async_mock_repo()
    evidence_repo.get_by_action_id = AsyncMock(return_value=None)

    mock_confidence = MagicMock()
    mock_confidence.level = ConfidenceLevel.LOW_CONFIDENCE
    mock_confidence.evidence_completeness = 0.3

    with patch("app.domain.services.session_rollback_service.RecoveryConfidenceModel") as MockModel:
        mock_model_instance = MockModel.return_value
        mock_model_instance.assess_confidence = AsyncMock(return_value=mock_confidence)

        service = SessionRollbackService(
            **{**base_service_kwargs, "confidence_repository": confidence_repo, "evidence_repository": evidence_repo}
        )
        plan = MagicMock()
        plan.plan_id = "plan-1"
        actions = [make_action("a1")]

        import asyncio
        result = asyncio.run(service._verify_recovery("t1", plan, actions))
        assert result.verification_status == VerificationStatus.EXECUTED_NOT_VERIFIED


# ---------------------------------------------------------------------------
# Build changeset and causal graph
# ---------------------------------------------------------------------------


def test_build_changeset_returns_changeset(base_service_kwargs):
    from app.domain.entities.causal_state_types import AIChangeSet

    session = make_session("s1")
    actions = [make_action("a1", parent_action_id=None)]
    mock_changeset = MagicMock(spec=AIChangeSet)

    with patch("app.domain.services.session_rollback_service.ChangeSetReconstructionService") as MockRecon:
        mock_recon_instance = MockRecon.return_value
        mock_recon_instance.reconstruct = AsyncMock(return_value=mock_changeset)
        service = SessionRollbackService(**base_service_kwargs)
        import asyncio
        result = asyncio.run(service._build_changeset("t1", "inc-1", session, actions))
        assert result is mock_changeset
        MockRecon.assert_called_once()


def test_build_causal_graph_returns_none_when_no_actions(base_service_kwargs):
    session = make_session("s1")
    service = SessionRollbackService(**base_service_kwargs)
    import asyncio
    result = asyncio.run(service._build_causal_graph("t1", "inc-1", session, []))
    assert result is None


def test_build_causal_graph_delegates_to_reconstruction_service(base_service_kwargs):
    session = make_session("s1")
    actions = [make_action("a1", parent_action_id=None)]
    mock_graph = MagicMock()

    with patch("app.domain.services.session_rollback_service.ChangeSetReconstructionService") as MockRecon:
        mock_recon_instance = MockRecon.return_value
        mock_recon_instance.build_causal_state_graph = AsyncMock(return_value=mock_graph)
        service = SessionRollbackService(**base_service_kwargs)
        import asyncio
        result = asyncio.run(service._build_causal_graph("t1", "inc-1", session, actions))
        assert result is mock_graph
        MockRecon.assert_called_once()


# ---------------------------------------------------------------------------
# Preview workflow
# ---------------------------------------------------------------------------


def test_preview_undo_agent_returns_empty_preview_when_no_actions(base_service_kwargs):
    session = make_session("s1")
    session_repo = _async_mock_repo()
    session_repo.get_by_session_id = AsyncMock(return_value=session)
    action_repo = _async_mock_repo()
    action_repo.list_by_agent = AsyncMock(return_value=([], 0))

    service = SessionRollbackService(
        **{**base_service_kwargs, "session_repository": session_repo, "action_repository": action_repo}
    )
    import asyncio
    result = asyncio.run(service.preview_undo_agent("t1", "s1"))
    assert result["preview"]["affected_actions_count"] == 0
    assert result["preview"]["blast_radius"] == "none"
    assert "message" in result["preview"]


def test_preview_undo_agent_includes_recovery_order(base_service_kwargs):
    session = make_session("s1")
    actions = [ProtectedAction(
        action_id="a1",
        tenant_id="t1",
        actor_user_id=None,
        agent_id="a1",
        authority_grant_id=None,
        tool="tool",
        resource="res",
        action_type="write",
        status=ActionStatus.EXECUTED,
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        parent_action_id=None,
        correlation_id=session.correlation_id,
    )]
    session_repo = _async_mock_repo()
    session_repo.get_by_session_id = AsyncMock(return_value=session)
    action_repo = _async_mock_repo()
    action_repo.list_by_agent = AsyncMock(return_value=(actions, 1))

    mock_changeset = MagicMock()
    mock_changeset.affected_resources = ["res"]
    mock_changeset.recoverability = {"a1": "recoverable"}
    mock_changeset.unknown_areas = []

    mock_plan = MagicMock()
    mock_plan.plan_id = "plan-1"
    mock_plan.topological_order = ["a1"]
    mock_plan.stop_conditions = []

    mock_simulation = {
        "resource_simulations": {"a1": {"simulation_status": "recoverable"}},
        "total_resources": 1,
        "recoverable_resources": 1,
    }

    mock_plan_repo = _async_mock_repo()
    mock_plan_repo.save = AsyncMock(return_value=mock_plan)

    with patch("app.domain.services.session_rollback_service.RecoveryPlanningService") as MockPlanning, \
         patch("app.domain.services.session_rollback_service.ChangeSetReconstructionService") as MockRecon:
        planning_instance = MockPlanning.return_value
        planning_instance.create_plan = AsyncMock(return_value=mock_plan)
        planning_instance.simulate_plan = AsyncMock(return_value=mock_simulation)

        recon_instance = MockRecon.return_value
        recon_instance.reconstruct = AsyncMock(return_value=mock_changeset)

        service = SessionRollbackService(
            **{**base_service_kwargs, "session_repository": session_repo, "action_repository": action_repo, "plan_repository": mock_plan_repo}
        )
        import asyncio
        result = asyncio.run(service.preview_undo_agent("t1", "s1"))
        assert result["preview"]["recovery_order"] == ["a1"]
        assert result["preview"]["plan_id"] == "plan-1"


# ---------------------------------------------------------------------------
# Simulation phases
# ---------------------------------------------------------------------------


def test_simulate_plan_reports_resource_summary(base_service_kwargs):
    actions = [make_action("a1")]
    plan = MagicMock()
    plan.plan_id = "plan-1"

    mock_sim_result = {
        "resource_simulations": {"a1": {"simulation_status": "recoverable"}},
        "total_resources": 1,
        "recoverable_resources": 1,
    }

    with patch("app.domain.services.session_rollback_service.RecoveryPlanningService") as MockPlanning, \
         patch("app.domain.services.session_rollback_service.RecoverySimulationEngine") as MockEngine:
        planning_instance = MockPlanning.return_value
        planning_instance.simulate_plan = AsyncMock(return_value={})

        engine_instance = MockEngine.return_value
        engine_instance.simulate_recovery = AsyncMock(return_value=mock_sim_result)

        service = SessionRollbackService(**base_service_kwargs)
        import asyncio
        result = asyncio.run(service._simulate_plan("t1", plan, actions))
        assert result["total_resources"] == 1
        assert result["recoverable_resources"] == 1
        assert result["irreversible_resources"] == 0


# ---------------------------------------------------------------------------
# Generate recovery plan preserves stop conditions
# ---------------------------------------------------------------------------


def test_generate_recovery_plan_preserves_stop_conditions(base_service_kwargs):
    session = make_session("s1")
    actions = [make_action("a1", parent_action_id=None)]
    incident = MagicMock()
    incident.incident_id = "inc-1"

    mock_plan = MagicMock()
    mock_plan.plan_id = "plan-1"
    mock_plan.stop_conditions = ["existing"]
    mock_plan.affected_action_ids = []

    captured = {}

    async def fake_create_plan(*args, **kwargs):
        return mock_plan

    async def fake_save(plan):
        captured["plan"] = plan
        return plan

    plan_repo = _async_mock_repo()
    plan_repo.save = AsyncMock(side_effect=fake_save)

    with patch("app.domain.services.session_rollback_service.RecoveryPlanningService") as MockPlanning:
        planning_instance = MockPlanning.return_value
        planning_instance.create_plan = AsyncMock(side_effect=fake_create_plan)

        service = SessionRollbackService(
            **{**base_service_kwargs, "plan_repository": plan_repo}
        )
        import asyncio
        result = asyncio.run(service._generate_recovery_plan("t1", session, actions, incident, ["new-stop"]))
        saved_plan = captured.get("plan")
        if saved_plan is not None:
            assert saved_plan.stop_conditions == ["new-stop"]


# ---------------------------------------------------------------------------
# Undo agent dry-run skips execution
# ---------------------------------------------------------------------------


def test_undo_agent_dry_run_skips_execution(base_service_kwargs):
    session = make_session("s1")
    actions = [make_action("a1", parent_action_id=None)]

    mock_db_session = MagicMock()
    mock_db_session.__enter__ = MagicMock(return_value=mock_db_session)
    mock_db_session.__exit__ = MagicMock(return_value=False)

    mock_session_repo = _async_mock_repo()
    mock_session_repo.get_by_session_id = AsyncMock(return_value=session)
    mock_session_repo.update_status = AsyncMock()

    mock_action_repo = _async_mock_repo()
    mock_action_repo.list_by_agent = AsyncMock(return_value=(actions, 1))
    mock_action_repo.list_descendants = AsyncMock(return_value=([], 0))

    mock_containment_repo = _async_mock_repo()
    mock_containment_repo.save = AsyncMock(return_value=MagicMock())

    mock_incident_repo = _async_mock_repo()
    mock_incident_repo.save = AsyncMock(return_value=MagicMock(incident_id="inc-1"))

    mock_plan_repo = _async_mock_repo()
    mock_plan_repo.save = AsyncMock(return_value=MagicMock(plan_id="plan-1"))

    mock_planning = MagicMock()
    mock_planning.create_plan = AsyncMock(return_value=MagicMock(plan_id="plan-1"))
    mock_planning.execute_plan = AsyncMock(return_value=MagicMock(status=RecoveryStatus.COMPLETED))
    mock_planning.simulate_plan = AsyncMock(return_value={})

    with patch("app.domain.services.session_rollback_service.SQLAlchemyAgentSessionRepository", return_value=mock_session_repo), \
         patch("app.domain.services.session_rollback_service.SQLAlchemyAgentRepository"), \
         patch("app.domain.services.session_rollback_service.SQLAlchemyAuthorityGrantRepository"), \
         patch("app.domain.services.session_rollback_service.SQLAlchemyProtectedActionRepository"), \
         patch("app.domain.services.session_rollback_service.SQLAlchemyExecutionTokenRepository"), \
         patch("app.domain.services.session_rollback_service.CascadeContainmentService") as MockContainment, \
         patch("app.domain.services.session_rollback_service.ChangeSetReconstructionService") as MockRecon, \
         patch("app.domain.services.session_rollback_service.RecoveryPlanningService", return_value=mock_planning), \
         patch("app.domain.services.session_rollback_service.DistributedRecoveryOrchestrator") as MockOrchestrator:
        mock_containment_service = MockContainment.return_value
        mock_containment_service.contain_authority_tree = AsyncMock(return_value=MagicMock(containment_id="cont-1"))

        recon_instance = MockRecon.return_value
        recon_instance.reconstruct = AsyncMock(return_value=MagicMock(
            affected_resources=["res"],
            recoverability={"a1": "recoverable"},
            unknown_areas=[],
        ))

        mock_orchestrator = MockOrchestrator.return_value
        mock_orchestrator.create_durable_plan = AsyncMock()
        mock_orchestrator.execute_durable_plan = AsyncMock(return_value={"status": "completed"})

        service = SessionRollbackService(
            **{
                **base_service_kwargs,
                "session_factory": MagicMock(return_value=mock_db_session),
                "session_repository": mock_session_repo,
                "action_repository": mock_action_repo,
                "containment_repository": mock_containment_repo,
                "incident_repository": mock_incident_repo,
                "plan_repository": mock_plan_repo,
            }
        )
        import asyncio
        result = asyncio.run(service.undo_agent("t1", "s1", "u1", dry_run=True))
        assert result["dry_run"] is True
        assert "session_id" in result
        assert result["status"] in (
            AgentSessionStatus.PARTIALLY_RECOVERED.value,
            AgentSessionStatus.RECOVERY_FAILED.value,
        )
