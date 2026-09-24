from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4
import pytest
from app.domain.entities.causal_state_types import (
    DurableExecutionStep, ConfidenceLevel, RecoveryConfidence,
    RecoveryReport, VerificationStatus,
)
from app.domain.entities.protected_action import (
    ActionStatus, ProtectedAction, Reversibility,
)
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability, CompensationType, ExecutionState,
    RecoveryAdapterType, RecoveryEvidence,
)
from app.domain.services.recovery_score_service import (
    ExecutionAssessment, RecoveryScore, RecoveryScoreService,
    VerificationAssessment,
)


class MockEvidenceRepo:
    """In-memory RecoveryEvidenceRepository."""

    def __init__(self):
        self._evidence: dict[str, RecoveryEvidence] = {}

    async def get_by_evidence_id(self, tenant_id: str, evidence_id: str):
        return self._evidence.get(evidence_id)

    async def get_by_action_id(self, tenant_id: str, action_id: str):
        for ev in self._evidence.values():
            if ev.action_id == action_id:
                return ev
        return None

    async def list_by_incident(self, tenant_id, incident_id, limit=100, offset=0):
        items = [ev for ev in self._evidence.values() if ev.incident_id == incident_id]
        return items[offset:offset + limit], len(items)

    async def list_by_root_action(self, tenant_id, root_action_id, limit=100, offset=0):
        items = [ev for ev in self._evidence.values() if ev.root_action_id == root_action_id]
        return items[offset:offset + limit], len(items)

    async def save(self, evidence):
        self._evidence[evidence.evidence_id] = evidence
        return evidence

    async def delete(self, tenant_id, evidence_id):
        self._evidence.pop(evidence_id, None)
        return True


class MockDurableExecutionRepo:
    """In-memory DurableExecutionRepository."""

    def __init__(self):
        self._steps: dict[str, DurableExecutionStep] = {}

    async def get_by_step_id(self, tenant_id, step_id):
        return self._steps.get(step_id)

    async def list_by_plan(self, tenant_id, plan_id, limit=500, offset=0):
        items = [s for s in self._steps.values() if s.plan_id == plan_id]
        items.sort(key=lambda s: s.execution_order)
        return items[offset:offset + limit], len(items)

    async def save(self, step):
        self._steps[step.step_id] = step
        return step


class MockReportRepo:
    """In-memory RecoveryReportRepository."""

    def __init__(self):
        self._reports: dict[str, RecoveryReport] = {}

    async def get_by_report_id(self, tenant_id, report_id):
        return self._reports.get(report_id)

    async def get_by_plan(self, tenant_id, plan_id):
        for r in self._reports.values():
            if r.plan_id == plan_id:
                return r
        return None

    async def get_by_incident(self, tenant_id, incident_id):
        for r in self._reports.values():
            if r.incident_id == incident_id:
                return r
        return None

    async def save(self, report):
        self._reports[report.report_id] = report
        return report


class MockConfidenceModel:
    """In-memory RecoveryConfidenceModel."""

    def __init__(self):
        self._repo = None

    async def assess_confidence(self, tenant_id, plan_id, actions, changeset=None):
        return RecoveryConfidence(
            confidence_id="mock-conf-1",
            tenant_id=tenant_id,
            plan_id=plan_id,
            level=ConfidenceLevel.HIGH_CONFIDENCE,
            before_state_available=True,
            after_state_available=True,
            current_state_available=True,
            adapter_support=True,
            version_match=True,
            drift_detected=False,
            conflict_detected=False,
            dependency_completeness=True,
            verification_capability=True,
            evidence_completeness=1.0,
            factors=["mock"],
            recommendations=["mock recommendation"],
        )


def _make_action(action_id="act-1", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE):
    return ProtectedAction(
        action_id=action_id,
        tenant_id="t1",
        actor_user_id=uuid4(),
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="test-tool",
        resource="test-resource",
        action_type="test",
        reversibility=reversibility,
    )


def _make_evidence(action_id="act-1", **kwargs):
    defaults = dict(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id="t1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        parent_action_id=None,
        root_action_id=None,
        correlation_id="corr-1",
        incident_id="inc-1",
        before_state_reference="before-ref",
        after_state_reference="after-ref",
        recovery_adapter_type=RecoveryAdapterType.HTTP_REST,
        dependency_edges=["dep-1"],
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
        state_version="v1",
        resource_version="v1",
        adapter_capability=AdapterCapability.PRODUCTION_VALIDATED,
    )
    defaults.update(kwargs)
    return RecoveryEvidence(**defaults)


def _make_step(step_id="step-1", plan_id="plan-1", action_id="act-1",
                execution_state=ExecutionState.SUCCEEDED.value,
                verification_passed=True):
    return DurableExecutionStep(
        step_id=step_id,
        plan_id=plan_id,
        action_id=action_id,
        execution_order=1,
        tenant_id="t1",
        execution_state=execution_state,
        verification_passed=verification_passed,
    )


@pytest.mark.asyncio
async def test_quick_score_full_recovery():
    svc = RecoveryScoreService()
    score = await svc.quick_score(
        tenant_id="t1",
        plan_id="p1",
        executed_steps=3,
        failed_steps=0,
        verified_steps=3,
        unknown_steps=0,
        evidence_count=3,
        total_actions=3,
    )
    assert score.cannot_claim_recovered is False
    assert score.execution_assessment.execution_complete is True
    assert score.verification_assessment.all_verified is True
    assert score.band == "HIGH"


@pytest.mark.asyncio
async def test_quick_score_unknown_outcome_blocks():
    svc = RecoveryScoreService()
    score = await svc.quick_score(
        tenant_id="t1",
        plan_id="p1",
        executed_steps=2,
        failed_steps=0,
        verified_steps=2,
        unknown_steps=1,
        evidence_count=2,
        total_actions=3,
    )
    assert score.cannot_claim_recovered is True
    assert score.execution_assessment.unknown_outcome_steps == 1


@pytest.mark.asyncio
async def test_quick_score_failed_steps_block():
    svc = RecoveryScoreService()
    score = await svc.quick_score(
        tenant_id="t1",
        plan_id="p1",
        executed_steps=2,
        failed_steps=1,
        verified_steps=2,
        unknown_steps=0,
        evidence_count=2,
        total_actions=3,
    )
    assert score.cannot_claim_recovered is True
    assert score.execution_assessment.failed_steps == 1


@pytest.mark.asyncio
async def test_quick_score_unverified_steps_block():
    svc = RecoveryScoreService()
    score = await svc.quick_score(
        tenant_id="t1",
        plan_id="p1",
        executed_steps=3,
        failed_steps=0,
        verified_steps=2,
        unknown_steps=0,
        evidence_count=3,
        total_actions=3,
    )
    assert score.cannot_claim_recovered is True
    assert score.verification_assessment.all_verified is False


@pytest.mark.asyncio
async def test_quick_score_irreversible_actions():
    svc = RecoveryScoreService()
    score = await svc.quick_score(
        tenant_id="t1",
        plan_id="p1",
        executed_steps=2,
        failed_steps=0,
        verified_steps=2,
        unknown_steps=0,
        evidence_count=2,
        total_actions=2,
        irreversible_count=2,
    )
    assert score.irreversibility_penalty > 0
    assert score.cannot_claim_recovered is True


@pytest.mark.asyncio
async def test_quick_score_conflict_weight():
    svc = RecoveryScoreService()
    score = await svc.quick_score(
        tenant_id="t1",
        plan_id="p1",
        executed_steps=3,
        failed_steps=0,
        verified_steps=3,
        unknown_steps=0,
        evidence_count=3,
        total_actions=3,
        conflict_count=2,
    )
    assert score.conflict_weight > 0


@pytest.mark.asyncio
async def test_quick_score_empty_actions():
    svc = RecoveryScoreService()
    score = await svc.quick_score(
        tenant_id="t1",
        plan_id="p1",
        executed_steps=0,
        failed_steps=0,
        verified_steps=0,
        unknown_steps=0,
        evidence_count=0,
        total_actions=0,
    )
    assert 0 < score.score < 1.0
    assert score.cannot_claim_recovered is True

@pytest.mark.asyncio
async def test_score_plan_all_succeeded_verified():
    svc = RecoveryScoreService()
    steps = [
        _make_step(step_id="s1", execution_state=ExecutionState.SUCCEEDED.value, verification_passed=True),
        _make_step(step_id="s2", execution_state=ExecutionState.SUCCEEDED.value, verification_passed=True),
    ]
    score = await svc.score_plan("t1", "p1", steps=steps)
    assert score.execution_assessment.execution_complete is True
    assert score.verification_assessment.all_verified is True
    assert score.cannot_claim_recovered is False


@pytest.mark.asyncio
async def test_score_plan_mixed_states():
    svc = RecoveryScoreService()
    steps = [
        _make_step(step_id="s1", execution_state=ExecutionState.SUCCEEDED.value, verification_passed=True),
        _make_step(step_id="s2", execution_state=ExecutionState.FAILED.value, verification_passed=False),
        _make_step(step_id="s3", execution_state=ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value, verification_passed=False),
    ]
    score = await svc.score_plan("t1", "p1", steps=steps)
    assert score.execution_assessment.failed_steps == 1
    assert score.execution_assessment.unknown_outcome_steps == 1
    assert score.cannot_claim_recovered is True


@pytest.mark.asyncio
async def test_score_plan_empty():
    svc = RecoveryScoreService()
    score = await svc.score_plan("t1", "p1", steps=[])
    assert score.execution_assessment.total_steps == 0
    assert score.cannot_claim_recovered is True


@pytest.mark.asyncio
async def test_score_plan_unknown_outcome():
    svc = RecoveryScoreService()
    steps = [
        _make_step(step_id="s1", execution_state=ExecutionState.UNKNOWN_EXTERNAL_OUTCOME.value, verification_passed=False),
    ]
    score = await svc.score_plan("t1", "p1", steps=steps)
    assert score.cannot_claim_recovered is True
    assert score.execution_assessment.unknown_outcome_steps == 1

@pytest.mark.asyncio
async def test_score_plan_recovery_no_repos():
    svc = RecoveryScoreService()
    score = await svc.score_plan_recovery("t1", "p1", actions=[])
    assert score.evidence_integrity_score == 1.0
    assert score.state_certainty == 1.0
    assert score.recovery_coverage == 1.0
    assert score.conflict_weight == 0.0
    assert score.irreversibility_penalty == 0.0
    assert score.unresolved_uncertainty == 0.0
    assert score.adapter_reliability == 1.0


@pytest.mark.asyncio
async def test_score_plan_recovery_execution_repo_verified():
    exec_repo = MockDurableExecutionRepo()
    exec_repo._steps["s1"] = _make_step(
        step_id="s1", plan_id="p1", action_id="act-1",
        execution_state=ExecutionState.SUCCEEDED.value, verification_passed=True,
    )
    svc = RecoveryScoreService(execution_repository=exec_repo)
    score = await svc.score_plan_recovery("t1", "p1", actions=[])
    assert score.execution_assessment.executed_steps == 1
    assert score.verification_assessment.verified_steps == 1
    assert score.verification_assessment.all_verified is True


@pytest.mark.asyncio
async def test_score_plan_recovery_no_verification():
    exec_repo = MockDurableExecutionRepo()
    exec_repo._steps["s1"] = _make_step(
        step_id="s1", plan_id="p1", action_id="act-1",
        execution_state=ExecutionState.SUCCEEDED.value, verification_passed=False,
    )
    svc = RecoveryScoreService(execution_repository=exec_repo)
    score = await svc.score_plan_recovery("t1", "p1", actions=[])
    assert score.verification_assessment.all_verified is False
    assert score.cannot_claim_recovered is True


@pytest.mark.asyncio
async def test_score_plan_recovery_with_evidence():
    ev_repo = MockEvidenceRepo()
    ev_repo._evidence["ev-1"] = _make_evidence(
        action_id="act-1",
        before_state_reference="before",
        after_state_reference="after",
        state_version="v1",
        resource_version="v1",
        recovery_adapter_type=RecoveryAdapterType.HTTP_REST,
        dependency_edges=["dep-1"],
        adapter_capability=AdapterCapability.PRODUCTION_VALIDATED,
    )
    svc = RecoveryScoreService(evidence_repository=ev_repo)
    actions = [_make_action(action_id="act-1")]
    score = await svc.score_plan_recovery("t1", "p1", actions=actions)
    assert score.evidence_integrity_score == 1.0
    assert score.state_certainty == 1.0
    assert score.recovery_coverage == 1.0
    assert score.dependency_certainty == 1.0
    assert score.adapter_reliability == 1.0


@pytest.mark.asyncio
async def test_score_plan_recovery_with_confidence_model():
    ev_repo = MockEvidenceRepo()
    ev_repo._evidence["ev-1"] = _make_evidence(action_id="act-1")
    cm = MockConfidenceModel()
    svc = RecoveryScoreService(evidence_repository=ev_repo, confidence_model=cm)
    actions = [_make_action(action_id="act-1")]
    score = await svc.score_plan_recovery("t1", "p1", actions=actions)
    assert score.confidence is not None
    assert score.confidence.level == ConfidenceLevel.HIGH_CONFIDENCE

@pytest.mark.asyncio
async def test_score_recovery_report_no_repo():
    svc = RecoveryScoreService()
    score = await svc.score_recovery_report("t1", "r1", actions=[])
    assert score.score_metadata["plan_id"] == ""
    assert score.cannot_claim_recovered is True


@pytest.mark.asyncio
async def test_score_recovery_report_with_repo():
    report_repo = MockReportRepo()
    report = RecoveryReport(
        report_id="r1",
        tenant_id="t1",
        plan_id="p1",
        incident_id="inc-1",
    )
    report_repo._reports["r1"] = report
    svc = RecoveryScoreService(report_repository=report_repo)
    score = await svc.score_recovery_report("t1", "r1", actions=[])
    assert score.score_metadata["plan_id"] == "p1"

@pytest.mark.asyncio
async def test_should_block_unknown_outcome():
    svc = RecoveryScoreService()
    ea = ExecutionAssessment(total_steps=1, executed_steps=0, failed_steps=0,
                              blocked_steps=0, manual_steps=0,
                              unknown_outcome_steps=1, execution_rate=0.0,
                              execution_complete=False, partial_details={})
    va = VerificationAssessment(verified_steps=0, unverified_steps=0, failed_steps=0,
                                unknown_outcome_steps=1, manual_required_steps=0,
                                total_verifiable=0, verification_rate=0.0,
                                all_verified=False, verification_details={})
    assert svc._should_block_recovery_claim(ea, va, 0.0, 0.0) is True


@pytest.mark.asyncio
async def test_should_block_failed_steps():
    svc = RecoveryScoreService()
    ea = ExecutionAssessment(total_steps=1, executed_steps=0, failed_steps=1,
                              blocked_steps=0, manual_steps=0,
                              unknown_outcome_steps=0, execution_rate=0.0,
                              execution_complete=False, partial_details={})
    va = VerificationAssessment(verified_steps=0, unverified_steps=0, failed_steps=1,
                                unknown_outcome_steps=0, manual_required_steps=0,
                                total_verifiable=0, verification_rate=0.0,
                                all_verified=False, verification_details={})
    assert svc._should_block_recovery_claim(ea, va, 0.0, 0.0) is True


@pytest.mark.asyncio
async def test_should_block_blocked_steps():
    svc = RecoveryScoreService()
    ea = ExecutionAssessment(total_steps=1, executed_steps=0, failed_steps=0,
                              blocked_steps=1, manual_steps=0,
                              unknown_outcome_steps=0, execution_rate=0.0,
                              execution_complete=False, partial_details={})
    va = VerificationAssessment(verified_steps=0, unverified_steps=0, failed_steps=0,
                                unknown_outcome_steps=0, manual_required_steps=0,
                                total_verifiable=0, verification_rate=0.0,
                                all_verified=False, verification_details={})
    assert svc._should_block_recovery_claim(ea, va, 0.0, 0.0) is True


@pytest.mark.asyncio
async def test_should_block_unresolved_uncertainty():
    svc = RecoveryScoreService()
    ea = ExecutionAssessment(total_steps=1, executed_steps=1, failed_steps=0,
                              blocked_steps=0, manual_steps=0,
                              unknown_outcome_steps=0, execution_rate=1.0,
                              execution_complete=True, partial_details={})
    va = VerificationAssessment(verified_steps=1, unverified_steps=0, failed_steps=0,
                                unknown_outcome_steps=0, manual_required_steps=0,
                                total_verifiable=1, verification_rate=1.0,
                                all_verified=True, verification_details={})
    assert svc._should_block_recovery_claim(ea, va, 0.5, 0.0) is True


@pytest.mark.asyncio
async def test_should_not_block_clean():
    svc = RecoveryScoreService()
    ea = ExecutionAssessment(total_steps=1, executed_steps=1, failed_steps=0,
                              blocked_steps=0, manual_steps=0,
                              unknown_outcome_steps=0, execution_rate=1.0,
                              execution_complete=True, partial_details={})
    va = VerificationAssessment(verified_steps=1, unverified_steps=0, failed_steps=0,
                                unknown_outcome_steps=0, manual_required_steps=0,
                                total_verifiable=1, verification_rate=1.0,
                                all_verified=True, verification_details={})
    assert svc._should_block_recovery_claim(ea, va, 0.0, 0.0) is False


@pytest.mark.asyncio
async def test_band_thresholds():
    svc = RecoveryScoreService()
    assert svc._determine_band(0.95, False) == "HIGH"
    assert svc._determine_band(0.75, False) == "MEDIUM"
    assert svc._determine_band(0.55, False) == "LOW"
    assert svc._determine_band(0.3, False) == "INSUFFICIENT"
    assert svc._determine_band(0.95, True) == "HIGH"
    assert svc._determine_band(0.3, True) == "INSUFFICIENT"


@pytest.mark.asyncio
async def test_weighted_score():
    svc = RecoveryScoreService()
    sub_scores = {
        "evidence_completeness": 1.0,
        "state_certainty": 1.0,
        "recovery_coverage": 1.0,
        "dependency_certainty": 1.0,
        "conflict_weight": 1.0,
        "irreversibility": 1.0,
        "external_side_effects": 1.0,
        "verification_coverage": 1.0,
        "adapter_reliability": 1.0,
        "unresolved_uncertainty_penalty": 1.0,
    }
    ea = ExecutionAssessment(total_steps=1, executed_steps=1, failed_steps=0,
                              blocked_steps=0, manual_steps=0,
                              unknown_outcome_steps=0, execution_rate=1.0,
                              execution_complete=True, partial_details={})
    va = VerificationAssessment(verified_steps=1, unverified_steps=0, failed_steps=0,
                                unknown_outcome_steps=0, manual_required_steps=0,
                                total_verifiable=1, verification_rate=1.0,
                                all_verified=True, verification_details={})
    score = svc._compute_weighted_score(sub_scores, ea, va)
    assert score <= 1.0
    assert score > 0.9


@pytest.mark.asyncio
async def test_recovery_score_to_dict():
    svc = RecoveryScoreService()
    score = await svc.quick_score(
        tenant_id="t1", plan_id="p1",
        executed_steps=1, failed_steps=0, verified_steps=1,
        unknown_steps=0, evidence_count=1, total_actions=1,
    )
    d = score.to_dict()
    assert "score" in d
    assert "band" in d
    assert "execution_assessment" in d
    assert "verification_assessment" in d
    assert "confidence_level" in d
    assert "cannot_claim_recovered" in d
    assert "scored_at" in d
    assert d["score"] == score.score
    assert d["band"] == score.band
    assert d["cannot_claim_recovered"] == score.cannot_claim_recovered


@pytest.mark.asyncio
async def test_score_plan_with_evidence():
    ev_repo = MockEvidenceRepo()
    ev_repo._evidence["ev-1"] = _make_evidence(
        action_id="act-1",
        before_state_reference="before",
        after_state_reference="after",
        state_version="v1",
        resource_version="v1",
        recovery_adapter_type=RecoveryAdapterType.HTTP_REST,
        dependency_edges=["dep-1"],
        adapter_capability=AdapterCapability.PRODUCTION_VALIDATED,
    )
    exec_repo = MockDurableExecutionRepo()
    exec_repo._steps["s1"] = _make_step(
        step_id="s1", plan_id="p1", action_id="act-1",
        execution_state=ExecutionState.SUCCEEDED.value, verification_passed=True,
    )
    svc = RecoveryScoreService(evidence_repository=ev_repo, execution_repository=exec_repo)
    steps = [exec_repo._steps["s1"]]
    actions = [_make_action(action_id="act-1")]
    score = await svc.score_plan_recovery("t1", "p1", actions=actions)
    assert score.evidence_integrity_score == 1.0
    assert score.state_certainty == 1.0
    assert score.recovery_coverage == 1.0
    assert score.adapter_reliability == 1.0
    assert score.conflict_weight == 0.0
    assert score.irreversibility_penalty == 0.0
    assert score.unresolved_uncertainty == 0.0
    assert score.cannot_claim_recovered is False
