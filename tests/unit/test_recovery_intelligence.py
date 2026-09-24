from __future__ import annotations

import pytest

from app.domain.entities.protected_action import ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import CompensationType, RecoveryEvidence
from app.domain.services.recovery_intelligence import (
    CascadingImpactAnalysis,
    ConflictAnalysis,
    ConflictStatus,
    DependencyGraph,
    DependencyNode,
    HumanImpactAssessment,
    PlanComparisonCriterion,
    PlanMetrics,
    PlanningMode,
    PlanValidity,
    PrerequisiteCheck,
    RecoveryAlternative,
    RecoveryIntelligenceService,
    RecoveryPlanVersion,
    RecoveryStrategy,
    SafetyGateResult,
    ValidationResult,
)


class MockActionRepository:
    def __init__(self):
        self.actions: dict[str, ProtectedAction] = {}
        self.descendants: dict[str, list[ProtectedAction]] = {}

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> ProtectedAction | None:
        return self.actions.get(action_id)

    async def list_descendants(
        self, tenant_id: str, action_id: str, limit: int = 1000, offset: int = 0
    ) -> tuple[list[ProtectedAction], int]:
        desc = self.descendants.get(action_id, [])
        return desc, len(desc)


class MockEvidenceRepository:
    def __init__(self):
        self.evidence: dict[str, RecoveryEvidence] = {}

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> RecoveryEvidence | None:
        return self.evidence.get(action_id)


class MockAdapter:
    def __init__(self, conflicts=None, preconditions=None, compensation=None):
        self._conflicts = conflicts
        self._preconditions = preconditions
        self._compensation = compensation

    async def check_conflicts(self, action, evidence, current_state):
        return self._conflicts

    async def check_preconditions(self, action, current_state):
        return self._preconditions

    async def generate_compensation(self, action, evidence):
        return self._compensation


@pytest.fixture
def mock_repos():
    action_repo = MockActionRepository()
    evidence_repo = MockEvidenceRepository()
    return action_repo, evidence_repo


@pytest.fixture
def sample_action():
    return ProtectedAction(
        action_id="act-1",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="database",
        resource="table.users",
        action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )


def test_recovery_strategy_enum():
    assert RecoveryStrategy.MINIMAL_CHANGE == "minimal_change"
    assert RecoveryStrategy.MAX_SAFETY == "max_safety"
    assert RecoveryStrategy.EMERGENCY == "emergency"


def test_plan_comparison_criterion_enum():
    assert PlanComparisonCriterion.COST == "cost"
    assert PlanComparisonCriterion.SAFETY == "safety"
    assert PlanComparisonCriterion.TIME == "time"


def test_plan_validity_enum():
    assert PlanValidity.VALID == "valid"
    assert PlanValidity.INVALID_CYCLE == "invalid_cycle"
    assert PlanValidity.INVALID_PREREQUISITE == "invalid_prerequisite"
    assert PlanValidity.INVALID_CONFLICT == "invalid_conflict"
    assert PlanValidity.INVALID_BOUNDARY == "invalid_boundary"


def test_planning_mode_enum():
    assert PlanningMode.STANDARD == "standard"
    assert PlanningMode.EMERGENCY == "emergency"
    assert PlanningMode.SIMULATION_ONLY == "simulation_only"


def test_dependency_node_creation():
    node = DependencyNode(
        action_id="act-1",
        parent_action_id=None,
        resource="table.users",
        tool="database",
    )
    assert node.action_id == "act-1"
    assert node.parent_action_id is None
    assert node.resource == "table.users"
    assert node.tool == "database"


def test_dependency_graph_creation():
    node = DependencyNode(action_id="act-1", parent_action_id=None, resource="r", tool="t")
    graph = DependencyGraph(
        nodes={"act-1": node},
        roots=["act-1"],
        leaves=["act-1"],
        topological_order=["act-1"],
        reverse_topological_order=["act-1"],
    )
    assert graph.nodes["act-1"] == node
    assert graph.roots == ["act-1"]


def test_conflict_analysis():
    conflict = ConflictAnalysis(
        action_id="act-1",
        conflict_status=ConflictStatus.VERSION_MISMATCH,
        details={"version": "v2"},
        blocking=True,
        resolution_hints=["re-capture state"],
    )
    assert conflict.action_id == "act-1"
    assert conflict.conflict_status == ConflictStatus.VERSION_MISMATCH
    assert conflict.blocking is True


def test_prerequisite_check():
    prereq = PrerequisiteCheck(
        action_id="act-1",
        satisfied=False,
        failed_checks=["before_state_missing"],
        details={"reason": "missing"},
    )
    assert prereq.action_id == "act-1"
    assert prereq.satisfied is False
    assert "before_state_missing" in prereq.failed_checks


def test_plan_metrics():
    metrics = PlanMetrics(
        estimated_cost=100.0,
        estimated_time_seconds=50.0,
        collateral_damage_score=0.3,
        uncertainty_score=0.2,
        completeness_score=0.8,
        safety_score=0.9,
        human_impact_score=0.1,
    )
    assert metrics.estimated_cost == 100.0
    assert metrics.safety_score == 0.9


def test_recovery_alternative():
    metrics = PlanMetrics(safety_score=0.9)
    alt = RecoveryAlternative(
        plan_id="plan-1",
        strategy=RecoveryStrategy.MAX_SAFETY,
        topological_order=["act-1", "act-2"],
        metrics=metrics,
        affected_actions=["act-1", "act-2"],
        compensation_actions=[],
        prerequisites=[],
        conflicts=[],
        boundaries=None,
    )
    assert alt.plan_id == "plan-1"
    assert alt.strategy == RecoveryStrategy.MAX_SAFETY


def test_validation_result():
    valid = ValidationResult(validity=PlanValidity.VALID, warnings=["warn"])
    assert valid.validity == PlanValidity.VALID
    assert valid.errors == []

    invalid = ValidationResult(
        validity=PlanValidity.INVALID_PREREQUISITE,
        errors=["Unsatisfied prerequisites"],
        failed_checks=["prerequisites"],
    )
    assert invalid.validity == PlanValidity.INVALID_PREREQUISITE
    assert "Unsatisfied prerequisites" in invalid.errors


def test_safety_gate_result():
    gate = SafetyGateResult(
        gate_name="test_gate",
        passed=True,
        details={},
        blocking=True,
        remediation="fix it",
    )
    assert gate.gate_name == "test_gate"
    assert gate.passed is True
    assert gate.blocking is True


def test_human_impact_assessment():
    assessment = HumanImpactAssessment(
        action_id="act-1",
        requires_human_approval=True,
        approval_reason="manual review",
        estimated_human_time_seconds=300.0,
        affected_parties=["security"],
        notification_required=True,
    )
    assert assessment.action_id == "act-1"
    assert assessment.requires_human_approval is True


def test_cascading_impact_analysis():
    impact = CascadingImpactAnalysis(
        root_action_id="act-1",
        cascade_depth=3,
        affected_resources=["act-1", "act-2"],
        cross_system_impacts={"db": ["act-1"]},
        blast_radius_estimate=2,
        containment_options=["staged_recovery"],
    )
    assert impact.cascade_depth == 3
    assert impact.blast_radius_estimate == 2


def test_recovery_plan_version():
    from datetime import UTC, datetime

    version = RecoveryPlanVersion(
        plan_id="plan-1",
        version="v1",
        plan_hash="abc123",
        created_at=datetime.now(UTC),
        supersedes=None,
        expires_at=None,
        is_active=True,
    )
    assert version.plan_id == "plan-1"
    assert version.version == "v1"
    assert version.is_active is True


@pytest.mark.asyncio
async def test_build_dependency_graph(mock_repos):
    action_repo, evidence_repo = mock_repos

    root = ProtectedAction(
        action_id="root",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.root",
        action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    child = ProtectedAction(
        action_id="child",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.child",
        action_type="update",
        reversibility=Reversibility.CONDITIONALLY_REVERSIBLE,
        parent_action_id="root",
    )

    action_repo.actions = {"root": root, "child": child}
    action_repo.descendants = {"root": [child]}

    service = RecoveryIntelligenceService(
        action_repository=action_repo, evidence_repository=evidence_repo
    )

    graph = await service.build_dependency_graph("tenant-1", "root")

    assert "root" in graph.nodes
    assert "child" in graph.nodes
    assert graph.nodes["root"].parent_action_id is None
    assert graph.nodes["child"].parent_action_id == "root"
    assert "root" in graph.roots
    assert "child" in graph.leaves


@pytest.mark.asyncio
async def test_analyze_conflicts_no_evidence(mock_repos):
    action_repo, evidence_repo = mock_repos

    action = ProtectedAction(
        action_id="act-1",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.users",
        action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )

    service = RecoveryIntelligenceService(
        action_repository=action_repo, evidence_repository=evidence_repo
    )

    conflicts = await service.analyze_conflicts("tenant-1", [action])

    assert len(conflicts) == 1
    assert conflicts[0].action_id == "act-1"
    assert conflicts[0].conflict_status == ConflictStatus.INSUFFICIENT_EVIDENCE
    assert conflicts[0].blocking is True


@pytest.mark.asyncio
async def test_check_prerequisites_no_evidence(mock_repos):
    action_repo, evidence_repo = mock_repos

    action = ProtectedAction(
        action_id="act-1",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.users",
        action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )

    service = RecoveryIntelligenceService(
        action_repository=action_repo, evidence_repository=evidence_repo
    )

    prereqs = await service.check_prerequisites("tenant-1", [action])

    assert len(prereqs) == 1
    assert prereqs[0].action_id == "act-1"
    assert prereqs[0].satisfied is False
    assert "No recovery evidence" in prereqs[0].failed_checks


def test_define_boundaries():
    service = RecoveryIntelligenceService()

    action1 = ProtectedAction(
        action_id="act-1",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.1",
        action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    action2 = ProtectedAction(
        action_id="act-2",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.2",
        action_type="update",
        reversibility=Reversibility.CONDITIONALLY_REVERSIBLE,
    )
    action3 = ProtectedAction(
        action_id="act-3",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.3",
        action_type="update",
        reversibility=Reversibility.IRREVERSIBLE,
    )

    conflicts = []
    prereqs = [
        PrerequisiteCheck(action_id="act-1", satisfied=True),
        PrerequisiteCheck(action_id="act-2", satisfied=False, failed_checks=["missing"]),
    ]

    boundaries = service.define_boundaries([action1, action2, action3], conflicts, prereqs)

    # act-1: auto reversible, prereq satisfied -> in rollback
    assert "act-1" in boundaries.rollback_boundary
    # act-2: conditional, prereq failed -> removed from rollback
    assert "act-2" not in boundaries.rollback_boundary
    # act-3: irreversible -> never in rollback
    assert "act-3" not in boundaries.rollback_boundary

    # act-2 conditional -> requires human approval
    assert "act-2" in boundaries.human_approval_boundary
    # act-3 irreversible -> no human approval
    assert "act-3" not in boundaries.human_approval_boundary

    # act-1, act-2 verifiable (not irreversible)
    assert "act-1" in boundaries.verification_boundary
    assert "act-2" in boundaries.verification_boundary
    assert "act-3" not in boundaries.verification_boundary


def test_compute_metrics():
    service = RecoveryIntelligenceService()

    action = ProtectedAction(
        action_id="act-1",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.1",
        action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )

    boundaries = type("obj", (object,), {"human_approval_boundary": []})()

    metrics = service.compute_metrics(
        actions=[action],
        conflicts=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        boundaries=boundaries,
        strategy=RecoveryStrategy.MAX_SAFETY,
    )

    assert metrics.safety_score == 1.0
    assert metrics.completeness_score == 1.0
    assert metrics.uncertainty_score == 0.0


def test_compare_alternatives():
    service = RecoveryIntelligenceService()

    metrics1 = PlanMetrics(
        estimated_cost=100, estimated_time_seconds=50, safety_score=0.8, completeness_score=0.7
    )
    metrics2 = PlanMetrics(
        estimated_cost=80, estimated_time_seconds=40, safety_score=0.9, completeness_score=0.8
    )

    alt1 = RecoveryAlternative(
        plan_id="plan-1",
        strategy=RecoveryStrategy.MAX_SAFETY,
        topological_order=["act-1"],
        metrics=metrics1,
        affected_actions=["act-1"],
        compensation_actions=[],
        prerequisites=[],
        conflicts=[],
        boundaries=None,
    )
    alt2 = RecoveryAlternative(
        plan_id="plan-2",
        strategy=RecoveryStrategy.MIN_DOWNTIME,
        topological_order=["act-1"],
        metrics=metrics2,
        affected_actions=["act-1"],
        compensation_actions=[],
        prerequisites=[],
        conflicts=[],
        boundaries=None,
    )

    comparison = service.compare_alternatives([alt1, alt2], PlanComparisonCriterion.SAFETY)

    assert comparison.ranking == ["plan-2", "plan-1"]
    assert comparison.selection == "plan-2"


def test_select_best_plan():
    service = RecoveryIntelligenceService()

    metrics = PlanMetrics(
        estimated_cost=100, estimated_time_seconds=50, safety_score=0.8
    )
    alt = RecoveryAlternative(
        plan_id="plan-1",
        strategy=RecoveryStrategy.MAX_SAFETY,
        topological_order=["act-1"],
        metrics=metrics,
        affected_actions=["act-1"],
        compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[],
        boundaries=None,
    )

    comparison = type("obj", (object,), {"alternatives": [alt]})()

    selected = service.select_best_plan(comparison, safety_threshold=0.5)
    assert selected is not None
    assert selected.plan_id == "plan-1"

    selected_fail = service.select_best_plan(comparison, safety_threshold=0.9)
    assert selected_fail is None


def test_validate_plan():
    service = RecoveryIntelligenceService()

    metrics_valid = PlanMetrics(
        uncertainty_score=0.2, collateral_damage_score=0.3, human_impact_score=0.2
    )
    alt_valid = RecoveryAlternative(
        plan_id="plan-valid",
        strategy=RecoveryStrategy.MAX_SAFETY,
        topological_order=["act-1"],
        metrics=metrics_valid,
        affected_actions=["act-1"],
        compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[
            ConflictAnalysis(
                action_id="act-1",
                conflict_status=ConflictStatus.NO_CONFLICT,
                blocking=False,
            )
        ],
        boundaries=type("obj", (object,), {"verification_boundary": ["act-1"]})(),
    )

    result = service.validate_plan(alt_valid)
    assert result.validity == PlanValidity.VALID

    metrics_invalid = PlanMetrics(
        uncertainty_score=0.8, collateral_damage_score=0.3, human_impact_score=0.2
    )
    alt_invalid = RecoveryAlternative(
        plan_id="plan-invalid",
        strategy=RecoveryStrategy.MAX_SAFETY,
        topological_order=["act-1"],
        metrics=metrics_invalid,
        affected_actions=["act-1"],
        compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[
            ConflictAnalysis(
                action_id="act-1",
                conflict_status=ConflictStatus.NO_CONFLICT,
                blocking=False,
            )
        ],
        boundaries=type("obj", (object,), {"verification_boundary": ["act-1"]})(),
    )

    result = service.validate_plan(alt_invalid)
    assert result.validity == PlanValidity.INVALID_BOUNDARY
    assert "High uncertainty" in result.errors[0]


def test_evaluate_safety_gates():
    service = RecoveryIntelligenceService()

    metrics = PlanMetrics(
        completeness_score=1.0, collateral_damage_score=0.2, human_impact_score=0.2
    )
    alt = RecoveryAlternative(
        plan_id="plan-1",
        strategy=RecoveryStrategy.MAX_SAFETY,
        topological_order=["act-1"],
        metrics=metrics,
        affected_actions=["act-1"],
        compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[
            ConflictAnalysis(
                action_id="act-1",
                conflict_status=ConflictStatus.NO_CONFLICT,
                blocking=False,
            )
        ],
        boundaries=type("obj", (object,), {
            "human_approval_boundary": [],
            "verification_boundary": ["act-1"],
        })(),
    )

    gates = service.evaluate_safety_gates(alt)

    assert len(gates) == 6
    assert all(gate.passed for gate in gates if gate.blocking)


def test_register_plan_version():
    service = RecoveryIntelligenceService()

    pv = service.register_plan_version(
        plan_id="plan-1",
        version="v1",
        plan_hash="hash1",
    )

    assert pv.plan_id == "plan-1"
    assert pv.version == "v1"
    assert pv.plan_hash == "hash1"
    assert pv.is_active is True

    versions = service.get_plan_versions("plan-1")
    assert len(versions) == 1


def test_register_plan_version_supersedes():
    service = RecoveryIntelligenceService()

    _pv1 = service.register_plan_version("plan-1", "v1", "hash1")
    _pv2 = service.register_plan_version("plan-1", "v2", "hash2", supersedes="v1")

    versions = service.get_plan_versions("plan-1")
    assert len(versions) == 2

    # Find v1 in versions - it should have superseded_by set
    v1_in_versions = next(v for v in versions if v.version == "v1")
    v2_in_versions = next(v for v in versions if v.version == "v2")

    assert v1_in_versions.superseded_by == "v2"
    assert v2_in_versions.supersedes == "v1"


def test_get_active_version():
    from datetime import UTC, datetime, timedelta

    service = RecoveryIntelligenceService()

    _pv1 = service.register_plan_version("plan-1", "v1", "hash1")
    pv1_expired = RecoveryPlanVersion(
        plan_id="plan-1",
        version="v1-expired",
        plan_hash="hash-expired",
        created_at=datetime.now(UTC) - timedelta(days=2),
        expires_at=datetime.now(UTC) - timedelta(days=1),
        is_active=True,
    )
    service._plan_versions["plan-1"].append(pv1_expired)

    active = service.get_active_version("plan-1")
    assert active is not None
    assert active.version == "v1"


def test_analyze_cascading_impact():
    service = RecoveryIntelligenceService()

    # Create graph with proper children/depends_on - linear chain, no cycles
    node1 = DependencyNode(
        action_id="act-1",
        parent_action_id=None,
        resource="r1",
        tool="db",
        children=["act-2"],
        depends_on=[],
    )
    node2 = DependencyNode(
        action_id="act-2",
        parent_action_id="act-1",
        resource="r2",
        tool="db",
        children=[],
        depends_on=[],
    )
    graph = DependencyGraph(
        nodes={"act-1": node1, "act-2": node2},
        roots=["act-1"],
        leaves=["act-2"],
        topological_order=["act-1", "act-2"],
        reverse_topological_order=["act-2", "act-1"],
    )

    impact = service.analyze_cascading_impact(graph, "act-1")

    assert impact.root_action_id == "act-1"
    assert impact.cascade_depth >= 1
    assert "act-1" in impact.affected_resources
    assert "act-2" in impact.affected_resources
    assert impact.blast_radius_estimate == 2


def test_create_recovery_plan_from_intelligence():
    import asyncio

    action_repo = MockActionRepository()
    evidence_repo = MockEvidenceRepository()

    root = ProtectedAction(
        action_id="root",
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="db",
        resource="table.root",
        action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    action_repo.actions = {"root": root}
    action_repo.descendants = {"root": []}

    # Add evidence for the root action
    evidence = RecoveryEvidence(
        evidence_id="ev-1",
        action_id="root",
        tenant_id="tenant-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        parent_action_id=None,
        root_action_id=None,
        correlation_id="corr-1",
        incident_id=None,
        target_system="db",
        target_resource="table.root",
        action_type="update",
        before_state_reference="s3://bucket/before",
        after_state_reference="s3://bucket/after",
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
        compensation_type=CompensationType.CUSTOM,
    )
    evidence_repo.evidence = {"root": evidence}

    service = RecoveryIntelligenceService(
        action_repository=action_repo, evidence_repository=evidence_repo
    )

    async def run_test():
        from app.domain.services.recovery_intelligence import create_recovery_plan_from_intelligence

        selected, comparison, validation, gates = await create_recovery_plan_from_intelligence(
            service, "tenant-1", "root", RecoveryStrategy.MAX_SAFETY, PlanningMode.STANDARD
        )

        return selected, comparison, validation, gates

    selected, comparison, validation, gates = asyncio.run(run_test())

    assert selected is not None
    assert comparison.ranked_by == PlanComparisonCriterion.SAFETY
    assert validation.validity == PlanValidity.VALID
    assert len(gates) == 6
