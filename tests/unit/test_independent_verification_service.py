from __future__ import annotations

import pytest

from app.domain.entities.causal_state_types import RecoveryReport, VerificationStatus
from app.domain.entities.independent_verification_types import (
    IndependentVerificationReport,
    IndependentVerificationResult,
    IndependentVerifier,
    IndependentVerifierRole,
    VerificationCheckType,
    VerificationOutcome,
)
from app.domain.entities.surgical_recovery_types import RecoveryEvidence, Reversibility
from app.domain.services.independent_verification_service import IndependentVerificationService


@pytest.fixture
def service():
    return IndependentVerificationService()


@pytest.fixture
def verifier():
    return IndependentVerifier(
        verifier_id="verifier-1",
        role=IndependentVerifierRole.AUTOMATED_VERIFIER,
        tenant_id="tenant-1",
    )


class TestCreateVerifier:
    def test_create_verifier_basic(self, service):
        v = service.create_verifier(
            verifier_id="v1",
            role=IndependentVerifierRole.AUTOMATED_VERIFIER,
            tenant_id="tenant-1",
        )
        assert v.verifier_id == "v1"
        assert v.role == IndependentVerifierRole.AUTOMATED_VERIFIER
        assert v.tenant_id == "tenant-1"
        assert v.credentials == {}
        assert v.delegation_chain == []

    def test_create_verifier_with_credentials(self, service):
        v = service.create_verifier(
            verifier_id="v1",
            role=IndependentVerifierRole.EXTERNAL_AUDITOR,
            tenant_id="tenant-1",
            credentials={"key": "secret"},
        )
        assert v.credentials == {"key": "secret"}

    def test_create_verifier_with_delegation(self, service):
        v = service.create_verifier(
            verifier_id="v1",
            role=IndependentVerifierRole.CROSS_TEAM_VERIFIER,
            tenant_id="tenant-1",
            delegation_chain=["team-a", "team-b"],
        )
        assert v.delegation_chain == ["team-a", "team-b"]


class TestCreateVerificationCheck:
    def test_create_check_basic(self, service):
        check = service.create_verification_check(
            check_id="check-1",
            check_type=VerificationCheckType.INTEGRITY,
            description="Test check",
            expected="ok",
            actual="ok",
            passed=True,
        )
        assert check.check_id == "check-1"
        assert check.check_type == VerificationCheckType.INTEGRITY
        assert check.passed is True
        assert check.evidence_references == []
        assert check.details == {}

    def test_create_check_with_evidence(self, service):
        check = service.create_verification_check(
            check_id="check-2",
            check_type=VerificationCheckType.STRUCTURAL,
            description="Structural check",
            expected="valid",
            actual="valid",
            passed=True,
            evidence_references=["ev-1", "ev-2"],
            details={"source": "test"},
        )
        assert check.evidence_references == ["ev-1", "ev-2"]
        assert check.details == {"source": "test"}


class TestVerifyEvidence:
    @pytest.mark.asyncio
    async def test_verify_valid_evidence(self, service):
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
        result = await service.verify_evidence(evidence)
        assert result.evidence_id == "ev-1"
        assert result.is_tampered is False
        assert result.is_missing is False

    @pytest.mark.asyncio
    async def test_verify_missing_evidence(self, service):
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
        result = await service.verify_evidence(evidence)
        assert result.is_missing is True
        assert len(result.missing_fields) > 0


class TestIndependentVerify:
    @pytest.mark.asyncio
    async def test_independent_verify_all_verified(self, service, verifier):
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
        result = await service.independent_verify("tenant-1", "plan-1", "inc-1", verifier, report)
        assert isinstance(result, IndependentVerificationResult)
        assert result.tenant_id == "tenant-1"
        assert result.plan_id == "plan-1"
        assert result.verifier.verifier_id == "verifier-1"
        assert result.outcome == VerificationOutcome.VERIFIED
        assert result.execution_verified is True
        assert result.all_checks_passed is True
        assert len(result.checks) == 2

    @pytest.mark.asyncio
    async def test_independent_verify_partial_failure(self, service, verifier):
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
        result = await service.independent_verify("tenant-1", "plan-1", "inc-1", verifier, report)
        assert result.outcome == VerificationOutcome.VERIFICATION_FAILED
        assert result.execution_verified is False
        assert result.all_checks_passed is False
        assert len(result.checks) == 2
        failed = [c for c in result.checks if not c.passed]
        assert len(failed) == 1

    @pytest.mark.asyncio
    async def test_independent_verify_unknown_outcome(self, service, verifier):
        report = RecoveryReport(
            report_id="report-3",
            tenant_id="tenant-1",
            plan_id="plan-1",
            incident_id="inc-1",
            resource_results={
                "step-1": {"status": VerificationStatus.UNKNOWN_EXTERNAL_OUTCOME.value},
            },
        )
        result = await service.independent_verify("tenant-1", "plan-1", "inc-1", verifier, report)
        assert result.outcome == VerificationOutcome.MANUAL_CHECK_REQUIRED
        for check in result.checks:
            assert check.passed is False


class TestBuildVerificationReport:
    def test_build_report_all_verified(self, service, verifier):
        r1 = IndependentVerificationResult(
            verification_id="v1",
            plan_id="plan-1",
            tenant_id="tenant-1",
            verifier=verifier,
            action_id="a1",
            outcome=VerificationOutcome.VERIFIED,
            checks=[],
        )
        r2 = IndependentVerificationResult(
            verification_id="v2",
            plan_id="plan-1",
            tenant_id="tenant-1",
            verifier=verifier,
            action_id="a2",
            outcome=VerificationOutcome.VERIFIED,
            checks=[],
        )
        report = service.build_verification_report(
            "tenant-1", "plan-1", "inc-1", verifier, [r1, r2]
        )
        assert isinstance(report, IndependentVerificationReport)
        assert report.overall_outcome == VerificationOutcome.VERIFIED
        assert len(report.results) == 2

    def test_build_report_with_failure(self, service, verifier):
        r1 = IndependentVerificationResult(
            verification_id="v1",
            plan_id="plan-1",
            tenant_id="tenant-1",
            verifier=verifier,
            action_id="a1",
            outcome=VerificationOutcome.VERIFICATION_FAILED,
            checks=[],
        )
        report = service.build_verification_report("tenant-1", "plan-1", "inc-1", verifier, [r1])
        assert report.overall_outcome == VerificationOutcome.VERIFICATION_FAILED

    def test_build_report_empty(self, service, verifier):
        report = service.build_verification_report("tenant-1", "plan-1", "inc-1", verifier, [])
        assert report.overall_outcome == VerificationOutcome.UNKNOWN


class TestComputeVerificationHash:
    def test_hash_deterministic(self, service):
        data = {"key": "value", "nested": {"a": 1}}
        h1 = service.compute_verification_hash(data)
        h2 = service.compute_verification_hash(data)
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_changes_with_data(self, service):
        h1 = service.compute_verification_hash({"a": 1})
        h2 = service.compute_verification_hash({"a": 2})
        assert h1 != h2
