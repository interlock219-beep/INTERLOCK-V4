from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.entities.incident import Incident, IncidentSeverity, IncidentStatus
from app.domain.entities.incident_orchestration_types import (
    IncidentOrchestrationPlan,
    OrchestrationOutcome,
    OrchestrationPhase,
    OrchestrationResult,
    OrchestrationStep,
    OrchestrationStepStatus,
)
from app.infrastructure.persistence.repositories.in_memory_incident_orchestration_repository import (
    InMemoryIncidentOrchestrationRepository,
)
from app.domain.services.incident_orchestrator import IncidentOrchestrator


@pytest.fixture
def tenant_id():
    return "tenant-1"


@pytest.fixture
def repo():
    return InMemoryIncidentOrchestrationRepository()


@pytest.fixture
def incident():
    return Incident(
        incident_id="inc-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        severity=IncidentSeverity.HIGH,
        status=IncidentStatus.DETECTED,
        trigger="unauthorized_action",
        affected_action_ids=["action-1", "action-2"],
        affected_resources=["resource-1"],
    )


@pytest.fixture
def orchestrator(repo):
    return IncidentOrchestrator(orchestration_repository=repo)


@pytest.mark.asyncio
async def test_orchestrate_incident_creates_plan_and_result(
    orchestrator, repo, tenant_id, incident
):
    plan = IncidentOrchestrationPlan(
        plan_id="plan-1",
        tenant_id=tenant_id,
        incident_id=incident.incident_id,
        root_action_id="action-1",
        agent_id=incident.agent_id,
        phases=[OrchestrationPhase.DETECTION, OrchestrationPhase.RESOLUTION],
        auto_containment=False,
        auto_recovery=False,
    )

    result = await orchestrator.orchestrate_incident(tenant_id, incident, plan=plan)

    assert result.orchestration_id is not None
    assert result.tenant_id == tenant_id
    assert result.incident_id == incident.incident_id
    assert result.phases_completed is not None
    assert "detection" in result.phases_completed
    assert "resolution" in result.phases_completed
    assert result.error is None
    assert len(result.recommendations) > 0


@pytest.mark.asyncio
async def test_orchestrate_incident_without_plan_creates_default(
    orchestrator, repo, tenant_id, incident
):
    result = await orchestrator.orchestrate_incident(tenant_id, incident)

    assert result.outcome in OrchestrationOutcome
    assert result.completed_at is not None
    assert result.created_at <= result.completed_at


@pytest.mark.asyncio
async def test_orchestrate_incident_phases_without_services(
    orchestrator, repo, tenant_id, incident
):
    plan = IncidentOrchestrationPlan(
        plan_id="plan-1",
        tenant_id=tenant_id,
        incident_id=incident.incident_id,
        root_action_id="action-1",
        agent_id=incident.agent_id,
        phases=[OrchestrationPhase.DETECTION, OrchestrationPhase.RESOLUTION],
        auto_containment=False,
        auto_recovery=False,
        auto_verification=True,
    )

    result = await orchestrator.orchestrate_incident(tenant_id, incident, plan=plan)

    assert result.outcome == OrchestrationOutcome.FAILED
    assert "detection" in result.phases_completed
    assert "resolution" in result.phases_completed
    assert result.error is None


@pytest.mark.asyncio
async def test_orchestrate_incident_with_containment_disabled(
    orchestrator, repo, tenant_id, incident
):
    plan = IncidentOrchestrationPlan(
        plan_id="plan-1",
        tenant_id=tenant_id,
        incident_id=incident.incident_id,
        root_action_id="action-1",
        agent_id=incident.agent_id,
        phases=[
            OrchestrationPhase.DETECTION,
            OrchestrationPhase.CONTAINMENT,
            OrchestrationPhase.RESOLUTION,
        ],
        auto_containment=False,
        auto_recovery=False,
    )

    result = await orchestrator.orchestrate_incident(tenant_id, incident, plan=plan)

    assert "containment" in result.phases_completed
    assert result.error is None


@pytest.mark.asyncio
async def test_orchestrate_incident_stop_on_failure_skips_remaining(
    repo, tenant_id, incident
):
    class FailingOrchestrator(IncidentOrchestrator):
        async def _execute_phase(self, *args, **kwargs):
            raise RuntimeError("Phase failed")

    orch = FailingOrchestrator(orchestration_repository=repo)

    plan = IncidentOrchestrationPlan(
        plan_id="plan-1",
        tenant_id=tenant_id,
        incident_id=incident.incident_id,
        root_action_id="action-1",
        agent_id=incident.agent_id,
        phases=[
            OrchestrationPhase.DETECTION,
            OrchestrationPhase.DISCOVERY,
            OrchestrationPhase.RESOLUTION,
        ],
        auto_containment=False,
        auto_recovery=False,
        stop_on_failure=True,
    )

    result = await orch.orchestrate_incident(tenant_id, incident, plan=plan)

    assert len(result.steps_failed) >= 1
    assert len(result.phases_skipped) > 0
    assert result.error is not None


@pytest.mark.asyncio
async def test_orchestrator_saves_plan_steps_and_result(
    orchestrator, repo, tenant_id, incident
):
    plan = IncidentOrchestrationPlan(
        plan_id="plan-1",
        tenant_id=tenant_id,
        incident_id=incident.incident_id,
        root_action_id="action-1",
        agent_id=incident.agent_id,
        phases=[OrchestrationPhase.DETECTION, OrchestrationPhase.RESOLUTION],
    )

    result = await orchestrator.orchestrate_incident(tenant_id, incident, plan=plan)

    saved_plan = await repo.get_orchestration_plan(tenant_id, plan.plan_id)
    assert saved_plan is not None

    saved_result = await repo.get_result(tenant_id, result.orchestration_id)
    assert saved_result is not None


@pytest.mark.asyncio
async def test_orchestrator_phase_detection(
    orchestrator, tenant_id, incident
):
    plan = IncidentOrchestrationPlan(
        plan_id="plan-1",
        tenant_id=tenant_id,
        incident_id=incident.incident_id,
        root_action_id="action-1",
        agent_id=incident.agent_id,
        phases=[OrchestrationPhase.DETECTION],
    )

    result = await orchestrator.orchestrate_incident(tenant_id, incident, plan=plan)

    assert "detection" in result.phases_completed


@pytest.mark.asyncio
async def test_orchestrator_determine_outcome_fully_recovered(
    orchestrator,
):
    outcome = orchestrator._determine_outcome(
        [OrchestrationPhase.RECOVERY_EXECUTION.value],
        verification_passed=True,
        evidence_preserved=True,
    )
    assert outcome == OrchestrationOutcome.FULLY_RECOVERED


@pytest.mark.asyncio
async def test_orchestrator_determine_outcome_contained(
    orchestrator,
):
    outcome = orchestrator._determine_outcome(
        [OrchestrationPhase.CONTAINMENT.value],
        verification_passed=True,
        evidence_preserved=True,
    )
    assert outcome == OrchestrationOutcome.CONTAINED


@pytest.mark.asyncio
async def test_orchestrator_determine_outcome_partially_recovered(
    orchestrator,
):
    outcome = orchestrator._determine_outcome(
        [OrchestrationPhase.RECOVERY_PLANNING.value],
        verification_passed=False,
        evidence_preserved=True,
    )
    assert outcome == OrchestrationOutcome.PARTIALLY_RECOVERED


@pytest.mark.asyncio
async def test_orchestrator_determine_outcome_failed(
    orchestrator,
):
    outcome = orchestrator._determine_outcome(
        [OrchestrationPhase.DETECTION.value],
        verification_passed=False,
        evidence_preserved=False,
    )
    assert outcome == OrchestrationOutcome.FAILED


@pytest.mark.asyncio
async def test_orchestrator_generate_recommendations_failed(orchestrator):
    recs = orchestrator._generate_recommendations(
        OrchestrationOutcome.FAILED,
        ["step-1"],
        ["analysis"],
    )
    assert "Manual incident response required" in recs
    assert any("step-1" in r for r in recs)
    assert any("analysis" in r for r in recs)


@pytest.mark.asyncio
async def test_orchestrator_generate_recommendations_fully_recovered(orchestrator):
    recs = orchestrator._generate_recommendations(
        OrchestrationOutcome.FULLY_RECOVERED,
        [],
        [],
    )
    assert "Conduct post-incident review" in recs[0]
