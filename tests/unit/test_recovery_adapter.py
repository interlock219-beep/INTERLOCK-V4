from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    ExecutionState,
    RecoveryAdapterType,
    Reversibility,
)
from app.domain.services.recovery_adapter import RecoveryAdapter


class MockRecoveryAdapter(RecoveryAdapter):
    async def can_recover(self, action: ProtectedAction) -> str:
        return "reversible"

    async def preview_recovery(self, action: ProtectedAction) -> dict:
        return {"reversible": True}

    async def execute_recovery(self, action: ProtectedAction, approved_by: str) -> dict:
        return {"status": "recovered"}


def make_action():
    return ProtectedAction(
        action_id="act-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        actor_user_id=None,
        authority_grant_id=None,
        tool="db",
        resource="table",
        action_type="write",
        status="allowed",
        decision_reason="",
        risk_score=0.0,
        created_at=None,
        evaluated_at=None,
        executed_at=None,
        parent_action_id=None,
        correlation_id=None,
        before_state_ref="before",
        after_state_ref="after",
        reversibility="reversible",
    )


@pytest.mark.asyncio
async def test_recovery_adapter_supports_reversible():
    adapter = MockRecoveryAdapter()
    action = make_action()
    assert await adapter.supports(action) is True


@pytest.mark.asyncio
async def test_recovery_adapter_capture_evidence():
    adapter = MockRecoveryAdapter()
    action = make_action()
    evidence = await adapter.capture_recovery_evidence(action)
    assert evidence.action_id == "act-1"
    assert evidence.target_system == "db"


@pytest.mark.asyncio
async def test_recovery_adapter_classify_reversibility():
    adapter = MockRecoveryAdapter()
    action = make_action()
    evidence = await adapter.capture_recovery_evidence(action)
    result = await adapter.classify_reversibility(action, evidence)
    assert result == Reversibility.AUTOMATICALLY_REVERSIBLE


@pytest.mark.asyncio
async def test_recovery_adapter_simulate():
    adapter = MockRecoveryAdapter()
    action = make_action()
    evidence = await adapter.capture_recovery_evidence(action)
    result = await adapter.simulate(action, evidence)
    assert result.would_succeed is True


@pytest.mark.asyncio
async def test_recovery_adapter_check_preconditions():
    adapter = MockRecoveryAdapter()
    action = make_action()
    result = await adapter.check_preconditions(action)
    assert result.satisfied is True


@pytest.mark.asyncio
async def test_recovery_adapter_detect_drift_with_before_state():
    adapter = MockRecoveryAdapter()
    action = make_action()
    evidence = await adapter.capture_recovery_evidence(action)
    result = await adapter.detect_drift(action, evidence)
    assert result.status.value == "no_drift"


@pytest.mark.asyncio
async def test_recovery_adapter_detect_drift_without_before_state():
    adapter = MockRecoveryAdapter()
    action = replace(make_action(), before_state_ref=None)
    evidence = await adapter.capture_recovery_evidence(action)
    result = await adapter.detect_drift(action, evidence)
    assert result.status.value == "insufficient_evidence"


@pytest.mark.asyncio
async def test_recovery_adapter_check_conflicts():
    adapter = MockRecoveryAdapter()
    action = make_action()
    evidence = await adapter.capture_recovery_evidence(action)
    result = await adapter.check_conflicts(action, evidence)
    assert result.status.value == "no_conflict"


@pytest.mark.asyncio
async def test_recovery_adapter_generate_compensation():
    adapter = MockRecoveryAdapter()
    action = make_action()
    evidence = await adapter.capture_recovery_evidence(action)
    result = await adapter.generate_compensation(action, evidence)
    assert result.action_id == "act-1"


@pytest.mark.asyncio
async def test_recovery_adapter_execute_compensation():
    adapter = MockRecoveryAdapter()
    action = make_action()
    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(comp, "idem-1")
    assert result.success is False
    assert result.execution_state == ExecutionState.REQUIRES_MANUAL_ACTION


@pytest.mark.asyncio
async def test_recovery_adapter_verify():
    adapter = MockRecoveryAdapter()
    action = make_action()
    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)
    result = await adapter.verify(comp)
    assert result.verified is False


def test_infer_adapter_type_database():
    adapter = MockRecoveryAdapter()
    adapter.adapter_name = "database_record"
    assert adapter._infer_adapter_type() == RecoveryAdapterType.DATABASE_RECORD


def test_infer_adapter_type_http():
    adapter = MockRecoveryAdapter()
    adapter.adapter_name = "http_adapter"
    assert adapter._infer_adapter_type() == RecoveryAdapterType.HTTP_REST


def test_infer_adapter_type_file():
    adapter = MockRecoveryAdapter()
    adapter.adapter_name = "file_version"
    assert adapter._infer_adapter_type() == RecoveryAdapterType.FILE_VERSION


def test_infer_adapter_type_unknown():
    adapter = MockRecoveryAdapter()
    adapter.adapter_name = "unknown"
    assert adapter._infer_adapter_type() == RecoveryAdapterType.UNSUPPORTED


def test_infer_capability_from_string():
    adapter = MockRecoveryAdapter()
    adapter.capability = "production_validated"
    assert adapter._infer_capability() == AdapterCapability.PRODUCTION_VALIDATED


def test_infer_capability_mock():
    adapter = MockRecoveryAdapter()
    adapter.capability = ""
    adapter.adapter_name = "mock_adapter"
    assert adapter._infer_capability() == AdapterCapability.MOCK


def test_infer_capability_stub():
    adapter = MockRecoveryAdapter()
    adapter.capability = ""
    adapter.adapter_name = "stub"
    assert adapter._infer_capability() == AdapterCapability.STUB
