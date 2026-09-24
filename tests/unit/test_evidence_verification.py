from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.entities.causal_state_types import (
    RecoveryReport,
    VerificationStatus,
)
from app.domain.entities.surgical_recovery_types import (
    RecoveryEvidence,
    Reversibility,
)
from app.domain.services.evidence_verification_service import EvidenceVerificationService


def test_compute_state_hash_deterministic():
    service = EvidenceVerificationService()
    state = {"key": "value", "nested": {"a": 1}}
    h1 = service.compute_state_hash(state)
    h2 = service.compute_state_hash(state)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_state_hash_changes_with_state():
    service = EvidenceVerificationService()
    h1 = service.compute_state_hash({"a": 1})
    h2 = service.compute_state_hash({"a": 2})
    assert h1 != h2


def test_verify_state_integrity_identical_states():
    service = EvidenceVerificationService()
    state = {"x": 1}
    result = service.verify_state_integrity(state, state)
    assert result["hashes_match"] is True
    assert result["state_changed"] is False
    assert result["verified"] is True


def test_verify_state_integrity_changed_states():
    service = EvidenceVerificationService()
    result = service.verify_state_integrity({"a": 1}, {"a": 2}, expected_hash=None)
    assert result["hashes_match"] is False
    assert result["state_changed"] is True
    assert result["verified"] is True


def test_verify_state_integrity_with_expected_hash():
    service = EvidenceVerificationService()
    state = {"a": 1}
    expected = service.compute_state_hash(state)
    result = service.verify_state_integrity(state, state, expected_hash=expected)
    assert result["expected_match"] is True
    assert result["verified"] is True


def test_verify_state_integrity_wrong_expected_hash():
    service = EvidenceVerificationService()
    result = service.verify_state_integrity({"a": 1}, {"a": 1}, expected_hash="bad")
    assert result["expected_match"] is False
    assert result["verified"] is False


def test_verify_evidence_integrity_valid():
    service = EvidenceVerificationService()
    evidence = RecoveryEvidence(
        evidence_id="ev-1",
        action_id="act-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        authority_grant_id="ag-1",
        parent_action_id=None,
        root_action_id=None,
        correlation_id="corr-1",
        incident_id=None,
        target_resource="db.table",
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_reference="s3://bucket/before/1",
        after_state_reference="s3://bucket/after/1",
        state_hash="sha256:abc123",
    )
    result = service.verify_evidence_integrity(evidence)
    assert result["integrity_ok"] is True
    assert result["verified"] is True
    assert result["reversibility"] == "automatically_reversible"


def test_verify_evidence_integrity_missing_fields():
    service = EvidenceVerificationService()
    evidence = RecoveryEvidence(
        evidence_id="",
        action_id="",
        tenant_id="",
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=None,
        correlation_id="corr-1",
        incident_id=None,
    )
    result = service.verify_evidence_integrity(evidence)
    assert result["integrity_ok"] is False
    assert "Missing evidence_id" in result["issues"]
    assert "Missing action_id" in result["issues"]
    assert "Missing tenant_id" in result["issues"]
    assert result["verified"] is False


@pytest.mark.asyncio
async def test_independent_verify_recovery_all_verified():
    service = EvidenceVerificationService()
    report = RecoveryReport(
        report_id="report-1",
        tenant_id="tenant-1",
        plan_id="plan-1",
        incident_id="inc-1",
        resource_results={
            "step-1": {"status": VerificationStatus.EXECUTED_AND_VERIFIED.value},
            "step-2": {"status": VerificationStatus.EXECUTED_AND_VERIFIED.value},
        },
    )
    result = await service.independent_verify_recovery("tenant-1", "plan-1", report)
    assert result["independent_verification"] is True
    assert result["all_steps_verified"] is True
    assert result["cannot_claim_recovered"] is False
    assert len(result["failed_steps"]) == 0


@pytest.mark.asyncio
async def test_independent_verify_recovery_partial_failure():
    service = EvidenceVerificationService()
    report = RecoveryReport(
        report_id="report-2",
        tenant_id="tenant-1",
        plan_id="plan-1",
        incident_id="inc-1",
        resource_results={
            "step-1": {"status": VerificationStatus.EXECUTED_AND_VERIFIED.value},
            "step-2": {"status": VerificationStatus.EXECUTION_FAILED.value},
        },
    )
    result = await service.independent_verify_recovery("tenant-1", "plan-1", report)
    assert result["all_steps_verified"] is False
    assert "step-2" in result["failed_steps"]
    assert result["cannot_claim_recovered"] is True


@pytest.mark.asyncio
async def test_independent_verify_recovery_unknown_outcome():
    service = EvidenceVerificationService()
    report = RecoveryReport(
        report_id="report-3",
        tenant_id="tenant-1",
        plan_id="plan-1",
        incident_id="inc-1",
        resource_results={
            "step-1": {"status": VerificationStatus.UNKNOWN_EXTERNAL_OUTCOME.value},
        },
    )
    result = await service.independent_verify_recovery("tenant-1", "plan-1", report)
    assert result["all_steps_verified"] is False
    assert result["rechecked_steps"][0]["independent_result"] == "MANUAL_CHECK_REQUIRED"


def test_verify_evidence_chain_empty():
    service = EvidenceVerificationService()
    result = service.verify_evidence_chain([])
    assert result["chain_valid"] is True
    assert result["evidence_count"] == 0
    assert result["gaps"] == []


def test_verify_evidence_chain_with_gaps():
    from dataclasses import replace

    service = EvidenceVerificationService()
    base_time = datetime.now(UTC)
    e1 = RecoveryEvidence(
        evidence_id="ev-1",
        action_id="act-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=None,
        correlation_id="corr-1",
        incident_id=None,
        created_at=base_time,
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    e2 = RecoveryEvidence(
        evidence_id="ev-2",
        action_id="act-2",
        tenant_id="tenant-1",
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=None,
        correlation_id="corr-1",
        incident_id=None,
        created_at=datetime.fromtimestamp(base_time.timestamp() + 7200, tz=UTC),
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    result = service.verify_evidence_chain([e1, e2])
    assert result["chain_valid"] is False
    assert len(result["gaps"]) > 0
    assert result["evidence_count"] == 2
