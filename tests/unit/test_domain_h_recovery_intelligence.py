from __future__ import annotations

import asyncio
import pytest

from app.domain.entities.protected_action import ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import (
    CompensationType,
    ConflictStatus,
    RecoveryEvidence,
)
from app.domain.services.recovery_intelligence import (
    BoundaryDefinition,
    CascadingImpactAnalysis,
    ConflictAnalysis,
    DependencyGraph,
    DependencyNode,
    FeasibilityReport,
    PlanComparison,
    PlanComparisonCriterion,
    PlanMetrics,
    PlanningMode,
    PrerequisiteCheck,
    RecoveryAlternative,
    RecoveryIntelligenceService,
    RecoveryStrategy,
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
    def __init__(self, evidence: dict[str, RecoveryEvidence] | None = None):
        self.evidence: dict[str, RecoveryEvidence] = evidence or {}

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


def _make_action(action_id: str, reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE, resource="table.users"):
    return ProtectedAction(
        action_id=action_id,
        tenant_id="tenant-1",
        actor_user_id="user-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        tool="database",
        resource=resource,
        action_type="update",
        reversibility=reversibility,
    )


def _make_evidence(action_id: str, before_ref="s3://bucket/before", rev=Reversibility.AUTOMATICALLY_REVERSIBLE):
    return RecoveryEvidence(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id="tenant-1",
        agent_id="agent-1",
        authority_grant_id="grant-1",
        parent_action_id=None,
        root_action_id=None,
        correlation_id="corr-1",
        incident_id=None,
        target_system="db",
        target_resource=f"table.{action_id}",
        action_type="update",
        before_state_reference=before_ref,
        after_state_reference="s3://bucket/after",
        reversibility_classification=rev,
        compensation_type=CompensationType.CUSTOM,
    )


# ---------------------------------------------------------------------------
# Feature 64 - Recovery feasibility analysis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_feasibility_feasible_plan():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1"), _make_action("act-2")]
    conflicts = [ConflictAnalysis(action_id="act-1", conflict_status=ConflictStatus.NO_CONFLICT, blocking=False)]
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=True),
               PrerequisiteCheck(action_id="act-2", satisfied=True)]
    boundaries = BoundaryDefinition(
        rollback_boundary=["act-1", "act-2"],
        compensation_boundary=["act-1", "act-2"],
        human_approval_boundary=[],
        verification_boundary=["act-1", "act-2"],
    )
    report = await service.analyze_recovery_feasibility("tenant-1", actions, conflicts, prereqs, boundaries)
    assert report.feasible is True
    assert report.feasibility_score > 0.5
    assert report.risk_level in ("low", "medium")
    assert report.recommended_strategy is not None


@pytest.mark.asyncio
async def test_analyze_feasibility_blocked_by_conflicts():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1")]
    conflicts = [ConflictAnalysis(
        action_id="act-1", conflict_status=ConflictStatus.CONCURRENT_MUTATION,
        blocking=True, resolution_hints=["coordinate with other actors"],
    )]
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=True)]
    boundaries = BoundaryDefinition()
    report = await service.analyze_recovery_feasibility("tenant-1", actions, conflicts, prereqs, boundaries)
    assert report.feasible is False
    assert any("Blocking conflict" in b for b in report.blockers)
    assert "coordinate with other actors" in report.mitigations


@pytest.mark.asyncio
async def test_analyze_feasibility_blocked_by_prerequisites():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1")]
    conflicts = []
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=False, failed_checks=["before_state_missing"])]
    boundaries = BoundaryDefinition()
    report = await service.analyze_recovery_feasibility("tenant-1", actions, conflicts, prereqs, boundaries)
    assert report.feasible is False
    assert any("Unsatisfied prerequisite" in b for b in report.blockers)


@pytest.mark.asyncio
async def test_analyze_feasibility_irreversible_actions():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1", Reversibility.IRREVERSIBLE)]
    conflicts = []
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=True)]
    boundaries = BoundaryDefinition()
    report = await service.analyze_recovery_feasibility("tenant-1", actions, conflicts, prereqs, boundaries)
    assert report.feasible is False
    assert any("Irreversible" in b for b in report.blockers)
    assert any("Manual recovery required" in m for m in report.mitigations)


@pytest.mark.asyncio
async def test_analyze_feasibility_no_actions():
    service = RecoveryIntelligenceService()
    report = await service.analyze_recovery_feasibility("tenant-1", [], [], [], BoundaryDefinition())
    assert report.feasible is False
    assert "No actions to recover" in report.blockers
    assert report.feasibility_score == 0.0
    assert report.risk_level == "critical"


@pytest.mark.asyncio
async def test_analyze_feasibility_high_risk_recommends_max_safety():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1", Reversibility.IRREVERSIBLE),
               _make_action("act-2", Reversibility.IRREVERSIBLE)]
    conflicts = []
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=True),
               PrerequisiteCheck(action_id="act-2", satisfied=True)]
    boundaries = BoundaryDefinition()
    report = await service.analyze_recovery_feasibility("tenant-1", actions, conflicts, prereqs, boundaries)
    assert report.recommended_strategy == RecoveryStrategy.MAX_SAFETY
    assert report.risk_level in ("high", "critical")


@pytest.mark.asyncio
async def test_analyze_feasibility_medium_risk_recommends_minimal_change():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1"), _make_action("act-2")]
    conflicts = [ConflictAnalysis(action_id="act-1", conflict_status=ConflictStatus.NO_CONFLICT, blocking=False)]
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=False, failed_checks=["missing"])]
    boundaries = BoundaryDefinition()
    report = await service.analyze_recovery_feasibility("tenant-1", actions, conflicts, prereqs, boundaries)
    assert report.recommended_strategy == RecoveryStrategy.MINIMAL_CHANGE
    assert report.risk_level == "medium"


@pytest.mark.asyncio
async def test_analyze_feasibility_low_evidence_completeness():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1"), _make_action("act-2")]
    conflicts = []
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=True),
               PrerequisiteCheck(action_id="act-2", satisfied=True)]
    boundaries = BoundaryDefinition(rollback_boundary=["act-1"])
    report = await service.analyze_recovery_feasibility("tenant-1", actions, conflicts, prereqs, boundaries)
    assert any("evidence" in w.lower() for w in report.warnings)
    assert report.feasibility_score < 1.0


# ---------------------------------------------------------------------------
# Feature 65 - Dependency-aware recovery ordering
# ---------------------------------------------------------------------------

def test_compute_recovery_ordering_standard():
    node1 = DependencyNode(action_id="act-1", parent_action_id=None, children=["act-2"], depends_on=[])
    node2 = DependencyNode(action_id="act-2", parent_action_id="act-1", children=[], depends_on=["act-1"])
    graph = DependencyGraph(
        nodes={"act-1": node1, "act-2": node2},
        roots=["act-1"], leaves=["act-2"],
        topological_order=["act-1", "act-2"], reverse_topological_order=["act-2", "act-1"],
    )
    service = RecoveryIntelligenceService()
    order = service.compute_recovery_ordering(graph, mode="standard")
    assert "act-1" in order and "act-2" in order


def test_compute_recovery_ordering_roots_first():
    node1 = DependencyNode(action_id="act-1", parent_action_id=None, children=["act-2"], depends_on=[])
    node2 = DependencyNode(action_id="act-2", parent_action_id="act-1", children=[], depends_on=[])
    graph = DependencyGraph(
        nodes={"act-1": node1, "act-2": node2},
        roots=["act-1"], leaves=["act-2"],
        topological_order=["act-1", "act-2"], reverse_topological_order=["act-2", "act-1"],
    )
    service = RecoveryIntelligenceService()
    order = service.compute_recovery_ordering(graph, mode="roots_first")
    assert order.index("act-1") < order.index("act-2")


def test_compute_recovery_ordering_leaves_first():
    node1 = DependencyNode(action_id="act-1", parent_action_id=None, children=["act-2"], depends_on=[])
    node2 = DependencyNode(action_id="act-2", parent_action_id="act-1", children=[], depends_on=[])
    graph = DependencyGraph(
        nodes={"act-1": node1, "act-2": node2},
        roots=["act-1"], leaves=["act-2"],
        topological_order=["act-1", "act-2"], reverse_topological_order=["act-2", "act-1"],
    )
    service = RecoveryIntelligenceService()
    order = service.compute_recovery_ordering(graph, mode="leaves_first")
    assert order.index("act-2") < order.index("act-1")


def test_compute_recovery_ordering_reversibility_first():
    node1 = DependencyNode(action_id="act-1", parent_action_id=None, children=[], depends_on=[],
                           reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
    node2 = DependencyNode(action_id="act-2", parent_action_id=None, children=[], depends_on=[],
                           reversibility=Reversibility.IRREVERSIBLE)
    graph = DependencyGraph(
        nodes={"act-1": node1, "act-2": node2},
        roots=["act-1", "act-2"], leaves=["act-1", "act-2"],
        topological_order=["act-1", "act-2"], reverse_topological_order=["act-2", "act-1"],
    )
    service = RecoveryIntelligenceService()
    order = service.compute_recovery_ordering(graph, mode="reversibility_first")
    assert order.index("act-1") < order.index("act-2")


def test_compute_recovery_ordering_filters_cycles():
    node1 = DependencyNode(action_id="act-1", parent_action_id=None, children=[], depends_on=["act-2"])
    node2 = DependencyNode(action_id="act-2", parent_action_id=None, children=[], depends_on=["act-1"])
    graph = DependencyGraph(
        nodes={"act-1": node1, "act-2": node2},
        roots=[], leaves=[],
        topological_order=["act-1", "act-2"], reverse_topological_order=["act-2", "act-1"],
        cycles=[["act-1", "act-2", "act-1"]],
    )
    service = RecoveryIntelligenceService()
    order = service.compute_recovery_ordering(graph, mode="standard")
    assert "act-1" not in order and "act-2" not in order


def test_compute_recovery_ordering_filters_missing_nodes():
    node1 = DependencyNode(action_id="act-1", parent_action_id=None, children=[], depends_on=[])
    graph = DependencyGraph(
        nodes={"act-1": node1},
        roots=["act-1"], leaves=["act-1"],
        topological_order=["act-1", "ghost"], reverse_topological_order=["ghost", "act-1"],
    )
    service = RecoveryIntelligenceService()
    order = service.compute_recovery_ordering(graph, mode="standard")
    assert "ghost" not in order and "act-1" in order


# ---------------------------------------------------------------------------
# Feature 66 - Recovery boundary risk analysis
# ---------------------------------------------------------------------------

def test_compute_boundary_risk_low_risk():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1"), _make_action("act-2")]
    boundaries = BoundaryDefinition(
        rollback_boundary=["act-1", "act-2"], compensation_boundary=["act-1", "act-2"],
        human_approval_boundary=[], verification_boundary=["act-1", "act-2"],
    )
    conflicts = [ConflictAnalysis(action_id="act-1", conflict_status=ConflictStatus.NO_CONFLICT, blocking=False)]
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=True),
               PrerequisiteCheck(action_id="act-2", satisfied=True)]
    result = service.compute_boundary_risk(boundaries, actions, conflicts, prereqs)
    assert result["risk_level"] == "low"
    assert result["overall_risk"] < 0.2
    assert result["details"]["blocking_conflicts"] == 0


def test_compute_boundary_risk_high_risk_blocking_conflicts():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1"), _make_action("act-2")]
    boundaries = BoundaryDefinition(
        rollback_boundary=[], compensation_boundary=[],
        human_approval_boundary=["act-1", "act-2"], verification_boundary=[],
    )
    conflicts = [
        ConflictAnalysis(action_id="act-1", conflict_status=ConflictStatus.CONCURRENT_MUTATION, blocking=True),
        ConflictAnalysis(action_id="act-2", conflict_status=ConflictStatus.NO_CONFLICT, blocking=False),
    ]
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=False),
               PrerequisiteCheck(action_id="act-2", satisfied=False)]
    result = service.compute_boundary_risk(boundaries, actions, conflicts, prereqs)
    assert result["risk_level"] in ("high", "critical")
    assert result["overall_risk"] >= 0.4
    assert result["details"]["blocking_conflicts"] == 1
    assert result["details"]["failed_prerequisites"] == 2


def test_compute_boundary_risk_critical_risk():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1")]
    boundaries = BoundaryDefinition(
        rollback_boundary=[], compensation_boundary=[],
        human_approval_boundary=["act-1"], verification_boundary=[],
    )
    conflicts = [ConflictAnalysis(action_id="act-1", conflict_status=ConflictStatus.VERSION_MISMATCH, blocking=True)]
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=False)]
    result = service.compute_boundary_risk(boundaries, actions, conflicts, prereqs)
    assert result["risk_level"] == "critical"
    assert result["overall_risk"] >= 0.7


def test_compute_boundary_risk_no_actions():
    service = RecoveryIntelligenceService()
    result = service.compute_boundary_risk(BoundaryDefinition(), [], [], [])
    assert result["overall_risk"] == 0.0
    assert result["risk_level"] == "low"
    assert result["details"] == {}


def test_compute_boundary_risk_with_failed_prerequisites():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1"), _make_action("act-2")]
    boundaries = BoundaryDefinition(
        rollback_boundary=["act-1"], compensation_boundary=["act-1"],
        human_approval_boundary=[], verification_boundary=["act-1", "act-2"],
    )
    conflicts = []
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=False, failed_checks=["precond_failed"])]
    result = service.compute_boundary_risk(boundaries, actions, conflicts, prereqs)
    assert result["details"]["failed_prerequisites"] == 1
    assert result["details"]["prerequisite_risk"] > 0.0


# ---------------------------------------------------------------------------
# Feature 67 - Alternate recovery strategy generation (extend)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_augment_alternatives_adds_selection_explanation():
    service = RecoveryIntelligenceService()
    alt = RecoveryAlternative(
        plan_id="plan-1", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.9), affected_actions=["act-1"],
        compensation_actions=[], prerequisites=[], conflicts=[], boundaries=BoundaryDefinition(),
    )
    comparison = PlanComparison(
        alternatives=[alt], ranked_by=PlanComparisonCriterion.SAFETY,
        ranking=["plan-1"], selection="plan-1", selection_rationale="Selected plan-1 by safety",
    )
    augmented = service._augment_alternatives([alt], comparison)
    assert any("Selected as best plan" in e for e in augmented[0].explanations)


@pytest.mark.asyncio
async def test_augment_alternatives_adds_rank_explanation():
    service = RecoveryIntelligenceService()
    alt1 = RecoveryAlternative(
        plan_id="plan-1", strategy=RecoveryStrategy.MINIMAL_CHANGE, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.7), affected_actions=["act-1"],
        compensation_actions=[], prerequisites=[], conflicts=[], boundaries=BoundaryDefinition(),
    )
    alt2 = RecoveryAlternative(
        plan_id="plan-2", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.95), affected_actions=["act-1"],
        compensation_actions=[], prerequisites=[], conflicts=[], boundaries=BoundaryDefinition(),
    )
    comparison = PlanComparison(
        alternatives=[alt1, alt2], ranked_by=PlanComparisonCriterion.SAFETY,
        ranking=["plan-2", "plan-1"], selection="plan-2",
    )
    augmented = service._augment_alternatives([alt1, alt2], comparison)
    best = next(a for a in augmented if a.plan_id == "plan-2")
    assert any("Selected as best plan" in e for e in best.explanations)
    runner_up = next(a for a in augmented if a.plan_id == "plan-1")
    assert any("Ranked #2" in e for e in runner_up.explanations)


@pytest.mark.asyncio
async def test_generate_alternatives_with_simulation_only_mode():
    action_repo = MockActionRepository()
    evidence_repo = MockEvidenceRepository()
    root = ProtectedAction(
        action_id="root", tenant_id="tenant-1", actor_user_id="user-1", agent_id="agent-1",
        authority_grant_id="grant-1", tool="db", resource="table.root", action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    action_repo.actions = {"root": root}
    action_repo.descendants = {"root": []}
    evidence_repo.evidence = {"root": _make_evidence("root")}
    service = RecoveryIntelligenceService(action_repository=action_repo, evidence_repository=evidence_repo)
    alternatives = await service.generate_alternatives("tenant-1", "root", mode=PlanningMode.SIMULATION_ONLY)
    assert len(alternatives) > 0
    for alt in alternatives:
        assert alt.provenance["mode"] == "simulation_only"


@pytest.mark.asyncio
async def test_generate_alternatives_with_emergency_mode():
    action_repo = MockActionRepository()
    evidence_repo = MockEvidenceRepository()
    root = ProtectedAction(
        action_id="root", tenant_id="tenant-1", actor_user_id="user-1", agent_id="agent-1",
        authority_grant_id="grant-1", tool="db", resource="table.root", action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
    )
    action_repo.actions = {"root": root}
    action_repo.descendants = {"root": []}
    evidence_repo.evidence = {"root": _make_evidence("root")}
    service = RecoveryIntelligenceService(action_repository=action_repo, evidence_repository=evidence_repo)
    alternatives = await service.generate_alternatives("tenant-1", "root", mode=PlanningMode.EMERGENCY)
    assert len(alternatives) > 0
    for alt in alternatives:
        assert alt.strategy == RecoveryStrategy.EMERGENCY


# ---------------------------------------------------------------------------
# Feature 68 - Recovery plan comparison with confidence/safety evidence
# ---------------------------------------------------------------------------

def test_compare_alternatives_with_evidence_basic():
    service = RecoveryIntelligenceService()
    metrics_safe = PlanMetrics(safety_score=0.9, completeness_score=0.8)
    metrics_fast = PlanMetrics(safety_score=0.5, completeness_score=0.4)
    alt_safe = RecoveryAlternative(
        plan_id="plan-safe", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=metrics_safe, affected_actions=["act-1"], compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[], boundaries=BoundaryDefinition(verification_boundary=["act-1"]),
    )
    alt_fast = RecoveryAlternative(
        plan_id="plan-fast", strategy=RecoveryStrategy.MIN_DOWNTIME, topological_order=["act-1"],
        metrics=metrics_fast, affected_actions=["act-1"], compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[], boundaries=BoundaryDefinition(verification_boundary=[]),
    )
    comparison = service.compare_alternatives_with_evidence(
        [alt_safe, alt_fast], PlanComparisonCriterion.SAFETY,
        confidence_weight=0.3, safety_weight=0.4, evidence_weight=0.3,
    )
    assert comparison.selection == "plan-safe"


def test_compare_alternatives_with_evidence_penalizes_blocking():
    service = RecoveryIntelligenceService()
    alt_ok = RecoveryAlternative(
        plan_id="plan-ok", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.8, completeness_score=0.9), affected_actions=["act-1"],
        compensation_actions=[], prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[], boundaries=BoundaryDefinition(),
    )
    alt_blocked = RecoveryAlternative(
        plan_id="plan-blocked", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.8, completeness_score=0.9), affected_actions=["act-1"],
        compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[ConflictAnalysis(action_id="act-1", conflict_status=ConflictStatus.CONCURRENT_MUTATION, blocking=True)],
        boundaries=BoundaryDefinition(),
    )
    comparison = service.compare_alternatives_with_evidence([alt_ok, alt_blocked], PlanComparisonCriterion.SAFETY)
    assert comparison.selection == "plan-ok"


def test_compare_alternatives_with_evidence_penalizes_no_verification():
    service = RecoveryIntelligenceService()
    alt_v = RecoveryAlternative(
        plan_id="plan-v", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.8, completeness_score=0.9), affected_actions=["act-1"],
        compensation_actions=[], prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[], boundaries=BoundaryDefinition(verification_boundary=["act-1"]),
    )
    alt_nv = RecoveryAlternative(
        plan_id="plan-nv", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.8, completeness_score=0.9), affected_actions=["act-1"],
        compensation_actions=[], prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[], boundaries=BoundaryDefinition(verification_boundary=[]),
    )
    comparison = service.compare_alternatives_with_evidence([alt_v, alt_nv], PlanComparisonCriterion.SAFETY)
    assert comparison.selection == "plan-v"


def test_compare_alternatives_with_evidence_empty_list():
    service = RecoveryIntelligenceService()
    comparison = service.compare_alternatives_with_evidence([])
    assert comparison.alternatives == []
    assert comparison.ranking == []
    assert comparison.selection is None


def test_compare_alternatives_with_evidence_weighted_selection():
    service = RecoveryIntelligenceService()
    metrics_a = PlanMetrics(safety_score=0.9, completeness_score=0.5)
    metrics_b = PlanMetrics(safety_score=0.6, completeness_score=0.95)
    alt_a = RecoveryAlternative(
        plan_id="plan-a", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=metrics_a, affected_actions=["act-1"], compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[], boundaries=BoundaryDefinition(verification_boundary=["act-1"]),
    )
    alt_b = RecoveryAlternative(
        plan_id="plan-b", strategy=RecoveryStrategy.MINIMAL_CHANGE, topological_order=["act-1"],
        metrics=metrics_b, affected_actions=["act-1"], compensation_actions=[],
        prerequisites=[PrerequisiteCheck(action_id="act-1", satisfied=True)],
        conflicts=[], boundaries=BoundaryDefinition(verification_boundary=["act-1"]),
    )
    comparison = service.compare_alternatives_with_evidence(
        [alt_a, alt_b], PlanComparisonCriterion.SAFETY,
        confidence_weight=0.5, safety_weight=0.25, evidence_weight=0.25,
    )
    assert comparison.selection is not None
    assert comparison.selection in ("plan-a", "plan-b")
    assert "evidence-aware" in comparison.selection_rationale


# ---------------------------------------------------------------------------
# Integration / cross-feature tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feasibility_integration_with_graph():
    action_repo = MockActionRepository()
    evidence_repo = MockEvidenceRepository()
    root = ProtectedAction(
        action_id="root", tenant_id="tenant-1", actor_user_id="user-1", agent_id="agent-1",
        authority_grant_id="grant-1", tool="db", resource="table.root", action_type="update",
        reversibility=Reversibility.CONDITIONALLY_REVERSIBLE,
    )
    child = ProtectedAction(
        action_id="child", tenant_id="tenant-1", actor_user_id="user-1", agent_id="agent-1",
        authority_grant_id="grant-1", tool="db", resource="table.child", action_type="update",
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE, parent_action_id="root",
    )
    action_repo.actions = {"root": root, "child": child}
    action_repo.descendants = {"root": [child]}
    evidence_repo.evidence = {"root": _make_evidence("root"), "child": _make_evidence("child")}
    service = RecoveryIntelligenceService(action_repository=action_repo, evidence_repository=evidence_repo)
    graph = await service.build_dependency_graph("tenant-1", "root")
    order = service.compute_recovery_ordering(graph, mode="standard")
    assert "root" in order and "child" in order


def test_compute_recovery_ordering_empty_graph():
    graph = DependencyGraph(nodes={}, roots=[], leaves=[], topological_order=[], reverse_topological_order=[])
    service = RecoveryIntelligenceService()
    order = service.compute_recovery_ordering(graph)
    assert order == []


def test_feasibility_report_risk_level_mapping():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1")]
    conflicts = []
    prereqs = [PrerequisiteCheck(action_id="act-1", satisfied=True)]
    boundaries = BoundaryDefinition(rollback_boundary=["act-1"])
    loop = asyncio.new_event_loop()
    try:
        report = loop.run_until_complete(
            service.analyze_recovery_feasibility("tenant-1", actions, conflicts, prereqs, boundaries)
        )
    finally:
        loop.close()
    assert report.risk_level in ("low", "medium", "high", "critical")
    assert 0.0 <= report.feasibility_score <= 1.0


def test_boundary_risk_details_keys():
    service = RecoveryIntelligenceService()
    actions = [_make_action("act-1")]
    boundaries = BoundaryDefinition(rollback_boundary=["act-1"])
    result = service.compute_boundary_risk(boundaries, actions, [], [])
    expected_keys = {"overall_risk", "risk_level", "details"}
    assert expected_keys.issubset(result.keys())
    detail_keys = {"rollback_risk", "compensation_risk", "conflict_risk", "prerequisite_risk"}
    assert detail_keys.issubset(result["details"].keys())


def test_augment_alternatives_no_selection():
    service = RecoveryIntelligenceService()
    alt = RecoveryAlternative(
        plan_id="plan-1", strategy=RecoveryStrategy.MINIMAL_CHANGE, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.7), affected_actions=["act-1"],
        compensation_actions=[], prerequisites=[], conflicts=[], boundaries=BoundaryDefinition(),
    )
    comparison = PlanComparison(
        alternatives=[alt], ranked_by=PlanComparisonCriterion.SAFETY,
        ranking=["plan-1"], selection=None,
    )
    augmented = service._augment_alternatives([alt], comparison)
    assert any("Ranked #1" in e for e in augmented[0].explanations)


def test_compare_alternatives_with_evidence_single_alternative():
    service = RecoveryIntelligenceService()
    alt = RecoveryAlternative(
        plan_id="plan-1", strategy=RecoveryStrategy.MAX_SAFETY, topological_order=["act-1"],
        metrics=PlanMetrics(safety_score=0.8), affected_actions=["act-1"],
        compensation_actions=[], prerequisites=[], conflicts=[], boundaries=BoundaryDefinition(),
    )
    comparison = service.compare_alternatives_with_evidence([alt])
    assert comparison.selection == "plan-1"
    assert comparison.ranking == ["plan-1"]