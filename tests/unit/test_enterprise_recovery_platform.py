from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.entities.chaos_types import (
    DigitalTwin,
    SimulationScenario,
)
from app.domain.entities.enterprise_recovery_types import (
    PlatformOperationResult,
    RecoveryPlatformStatus,
)
from app.domain.entities.incident import Incident, IncidentSeverity, IncidentStatus
from app.domain.services.chaos_simulation_engine import ChaosSimulationEngine
from app.domain.services.enterprise_recovery_platform import EnterpriseRecoveryPlatform
from app.domain.services.self_healing_service import SelfHealingService
from app.infrastructure.persistence.repositories.in_memory_forensic_audit_repository import (
    InMemoryForensicAuditRepository,
)
from app.infrastructure.persistence.repositories.in_memory_incident_orchestration_repository import (
    InMemoryIncidentOrchestrationRepository,
)
from app.domain.services.merkle_audit_log_service import MerkleAuditLogService


@pytest.fixture
def tenant_id():
    return "tenant-1"


@pytest.fixture
def incident():
    return Incident(
        incident_id="inc-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        severity=IncidentSeverity.CRITICAL,
        status=IncidentStatus.DETECTED,
        trigger="unauthorized_data_export",
        affected_action_ids=["action-1"],
        affected_resources=["resource-1"],
    )


@pytest.fixture
def mock_incident_repo():
    class MockIncidentRepo:
        async def list_by_tenant(self, tenant_id, status=None, limit=100, offset=0):
            return [], 0

    return MockIncidentRepo()


@pytest.fixture
def platform(mock_incident_repo, tenant_id):
    return EnterpriseRecoveryPlatform(
        incident_repository=mock_incident_repo,
        orchestration_repository=InMemoryIncidentOrchestrationRepository(),
        forensic_audit_service=MerkleAuditLogService(
            audit_repository=InMemoryForensicAuditRepository()
        ),
        chaos_engine=ChaosSimulationEngine(),
        self_healing_service=SelfHealingService(),
    )


@pytest.mark.asyncio
async def test_handle_incident_runs_full_workflow(platform, tenant_id, incident):
    result = await platform.handle_incident(tenant_id, incident)

    assert result.tenant_id == tenant_id
    assert result.status == RecoveryPlatformStatus.SUCCESS
    assert "forensic_audit" in result.components_succeeded
    assert len(result.operation_id) > 0


@pytest.mark.asyncio
async def test_handle_incident_without_optional_services(tenant_id, incident):
    platform = EnterpriseRecoveryPlatform()

    result = await platform.handle_incident(tenant_id, incident)

    assert result.status in (
        RecoveryPlatformStatus.SUCCESS,
        RecoveryPlatformStatus.FAILURE,
    )
    assert len(result.components_executed) == 0


@pytest.mark.asyncio
async def test_handle_incident_chaos_runs_for_critical(
    platform, tenant_id, incident
):
    result = await platform.handle_incident(tenant_id, incident)

    if "chaos_simulation" in result.components_executed:
        assert "chaos_simulation" in result.components_succeeded
        assert "chaos_result" in result.result_data


@pytest.mark.asyncio
async def test_handle_incident_self_healing_runs(platform, tenant_id, incident):
    result = await platform.handle_incident(tenant_id, incident)

    assert "self_healing" in result.components_succeeded
    assert "healing_result" in result.result_data


@pytest.mark.asyncio
async def test_handle_incident_forensic_audit_logs(platform, tenant_id, incident):
    await platform.handle_incident(tenant_id, incident)

    repo = platform._forensics._repo
    entries, _ = await repo.list_by_event_type(
        tenant_id, "incident_detected"
    )
    assert len(entries) >= 1
    assert entries[0].event_type.value == "incident_detected"


@pytest.mark.asyncio
async def test_get_resilience_metrics_with_no_data(platform, tenant_id):
    metrics = await platform.get_resilience_metrics(tenant_id)

    assert metrics.tenant_id == tenant_id
    assert "overall_availability" in metrics.values
    assert "overall_resilience" in metrics.values
    assert metrics.values["overall_resilience"] >= 0.0


@pytest.mark.asyncio
async def test_get_recovery_summary_no_incidents(platform, tenant_id):
    summary = await platform.get_recovery_summary(tenant_id)

    assert summary.tenant_id == tenant_id
    assert summary.active_incidents == []
    assert len(summary.recent_incidents) == 0
    assert summary.resilience_score >= 0.0


@pytest.mark.asyncio
async def test_get_recovery_summary_with_incidents(
    platform, mock_incident_repo, tenant_id, incident
):
    class RepoWithIncidents:
        async def list_by_tenant(self, tid, status=None, limit=100, offset=0):
            return [incident], 1

    platform._incident_repo = RepoWithIncidents()

    summary = await platform.get_recovery_summary(tenant_id)

    assert "inc-1" in summary.recent_incidents
    assert "inc-1" in summary.active_incidents


@pytest.mark.asyncio
async def test_platform_recommendations_on_failure(tenant_id, incident):
    platform = EnterpriseRecoveryPlatform()

    result = await platform.handle_incident(tenant_id, incident)

    assert result.status == RecoveryPlatformStatus.FAILURE
    assert any("Manual intervention" in r for r in result.recommendations)


@pytest.mark.asyncio
async def test_platform_recommendations_on_success(
    platform, tenant_id, incident
):
    result = await platform.handle_incident(tenant_id, incident)

    assert result.status == RecoveryPlatformStatus.SUCCESS
