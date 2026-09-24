"""Domain G Graph features 59-63 comprehensive unit tests.

Covers:
  Feature 59 - Unified recovery/resource graph (build_unified_recovery_graph)
  Feature 60 - Dependency/impact traversal (traverse_dependencies, get_impact_set)
  Feature 61 - Graph versioning with immutable versions and graph diffing
  Feature 62 - Cycle detection and consistency validation
  Feature 63 - Recovery-plan extraction from graph relationships
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.entities.recovery_graph_types import (
    ConsistencyLevel,
    CycleStatus,
    GraphEdge,
    GraphNode,
    GraphNodeKind,
    GraphRelation,
    RecoveryGraph,
)
from app.domain.entities.surgical_recovery_types import (
    CompensationType,
    RecoveryAdapterType,
    RecoveryEvidence,
    Reversibility,
)
from app.domain.services.causal_graph_service import CausalGraphService
from app.domain.services.graph_integration_service import GraphIntegrationService
from app.domain.services.recovery_intelligence import (
    DependencyGraph,
    DependencyNode,
    RecoveryIntelligenceService,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _build_acyclic_graph():
    nodes = {
        "action-1": DependencyNode(
            action_id="action-1", parent_action_id=None,
            resource="db-primary", tool="db_write",
            reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        ),
        "action-2": DependencyNode(
            action_id="action-2", parent_action_id="action-1",
            resource="cache-redis", tool="cache_delete",
            reversibility=Reversibility.MANUALLY_RECOVERABLE,
        ),
        "action-3": DependencyNode(
            action_id="action-3", parent_action_id="action-2",
            resource="queue-rabbitmq", tool="queue_publish",
            reversibility=Reversibility.CONDITIONALLY_REVERSIBLE,
        ),
    }
    dep_graph = DependencyGraph(
        nodes=nodes, roots=["action-1"], leaves=["action-3"],
        topological_order=["action-1", "action-2", "action-3"],
        reverse_topological_order=["action-3", "action-2", "action-1"],
        cycles=[],
    )
    svc = GraphIntegrationService()
    return asyncio.run(svc.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )), dep_graph


@pytest.fixture
def acyclic_graph():
    g, _ = _build_acyclic_graph()
    return g


@pytest.fixture
def dep_graph():
    nodes = {
        "action-1": DependencyNode(
            action_id="action-1", parent_action_id=None,
            resource="db-primary", tool="db_write",
            reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        ),
        "action-2": DependencyNode(
            action_id="action-2", parent_action_id="action-1",
            resource="cache-redis", tool="cache_delete",
            reversibility=Reversibility.MANUALLY_RECOVERABLE,
        ),
        "action-3": DependencyNode(
            action_id="action-3", parent_action_id="action-2",
            resource="queue-rabbitmq", tool="queue_publish",
            reversibility=Reversibility.CONDITIONALLY_REVERSIBLE,
        ),
    }
    return DependencyGraph(
        nodes=nodes, roots=["action-1"], leaves=["action-3"],
        topological_order=["action-1", "action-2", "action-3"],
        reverse_topological_order=["action-3", "action-2", "action-1"],
        cycles=[],
    )


@pytest.fixture
def service():
    return GraphIntegrationService()


@pytest.fixture
def causal_service():
    return CausalGraphService()


def _make_action_node(node_id, tenant_id="t1", entity_id=None, resource="res"):
    return GraphNode(
        node_id=node_id, tenant_id=tenant_id, kind=GraphNodeKind.ACTION,
        entity_id=entity_id or node_id, label="action " + node_id,
        properties={"resource": resource},
    )


def _make_resource_node(node_id, tenant_id="t1", entity_id=None):
    return GraphNode(
        node_id=node_id, tenant_id=tenant_id, kind=GraphNodeKind.RESOURCE,
        entity_id=entity_id or node_id, label=node_id,
    )


def _make_edge(edge_id, source, target, tenant_id="t1", relation=GraphRelation.DEPENDS_ON):
    return GraphEdge(
        edge_id=edge_id, tenant_id=tenant_id,
        source_node_id=source, target_node_id=target, relation=relation,
    )


# ===========================================================================
# Feature 59 - Unified recovery/resource graph
# ===========================================================================


@pytest.mark.asyncio
async def test_build_unified_graph_returns_recovery_graph(service, dep_graph):
    graph = await service.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    assert isinstance(graph, RecoveryGraph)


@pytest.mark.asyncio
async def test_build_unified_graph_has_correct_tenant_and_incident(service, dep_graph):
    graph = await service.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    assert graph.tenant_id == "tenant-1"
    assert graph.incident_id == "inc-1"
    assert graph.root_action_id == "action-1"
    assert graph.version == 1


@pytest.mark.asyncio
async def test_build_unified_graph_has_action_nodes(service, dep_graph):
    graph = await service.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    action_nodes = [n for n in graph.nodes if n.kind == GraphNodeKind.ACTION]
    assert len(action_nodes) == 3


@pytest.mark.asyncio
async def test_build_unified_graph_has_resource_nodes(service, dep_graph):
    graph = await service.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    resource_nodes = [n for n in graph.nodes if n.kind == GraphNodeKind.RESOURCE]
    assert len(resource_nodes) == 3
    resources = {n.entity_id for n in resource_nodes}
    assert "db-primary" in resources
    assert "cache-redis" in resources
    assert "queue-rabbitmq" in resources


@pytest.mark.asyncio
async def test_build_unified_graph_has_dep_edges(service, dep_graph):
    graph = await service.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    dep_edges = [e for e in graph.edges if e.relation == GraphRelation.DEPENDS_ON]
    assert len(dep_edges) >= 2


@pytest.mark.asyncio
async def test_build_unified_graph_no_causal_service_fallback(service, dep_graph):
    svc = GraphIntegrationService(causal_graph_service=None)
    graph = await svc.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    assert isinstance(graph, RecoveryGraph)
    assert graph.tenant_id == "tenant-1"


@pytest.mark.asyncio
async def test_build_unified_graph_metadata_source_unified(service, dep_graph):
    graph = await service.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    assert graph.metadata.get("source") == "unified"


@pytest.mark.asyncio
async def test_build_unified_graph_has_graph_id_prefix(service, dep_graph):
    graph = await service.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    assert graph.graph_id.startswith("g-tenant-1")


@pytest.mark.asyncio
async def test_build_unified_graph_has_unique_node_ids(service, dep_graph):
    graph = await service.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    node_ids = [n.node_id for n in graph.nodes]
    assert len(node_ids) == len(set(node_ids))


@pytest.mark.asyncio
async def test_build_unified_graph_causal_nodes_integrated(service, dep_graph):
    class MockCausalGraph:
        async def get_incident_graph(self, tenant_id, action_id):
            return {
                "nodes": [
                    {
                        "action_id": "action-1",
                        "agent_id": "ag-1",
                        "tool": "tool1",
                        "resource": "res-1",
                        "action_type": "read",
                        "status": "executed",
                        "parent_action_id": None,
                    },
                ],
                "edges": [],
            }

    svc = GraphIntegrationService(causal_graph_service=MockCausalGraph())
    graph = await svc.build_unified_recovery_graph(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    causal_nodes = [n for n in graph.nodes if n.properties.get("agent_id") == "ag-1"]
    assert len(causal_nodes) >= 1


# ===========================================================================
# Feature 60 - Dependency and impact traversal (CausalGraphService)
# ===========================================================================


def test_traverse_dependencies_downstream(acyclic_graph):
    svc = CausalGraphService()
    result = svc.traverse_dependencies(
        acyclic_graph, "action:tenant-1:action-1", direction="downstream"
    )
    result_ids = [n.node_id for n in result]
    assert "action:tenant-1:action-2" in result_ids
    assert "action:tenant-1:action-3" in result_ids


def test_traverse_dependencies_upstream(acyclic_graph):
    svc = CausalGraphService()
    result = svc.traverse_dependencies(
        acyclic_graph, "action:tenant-1:action-3", direction="upstream"
    )
    result_ids = [n.node_id for n in result]
    assert "action:tenant-1:action-2" in result_ids
    assert "action:tenant-1:action-1" in result_ids


def test_traverse_dependencies_invalid_direction_raises(acyclic_graph):
    svc = CausalGraphService()
    with pytest.raises(ValueError, match="direction must be"):
        svc.traverse_dependencies(
            acyclic_graph, "action:tenant-1:action-1", direction="sideways"
        )


def test_traverse_dependencies_respects_limit(acyclic_graph):
    svc = CausalGraphService()
    result = svc.traverse_dependencies(
        acyclic_graph, "action:tenant-1:action-1", direction="downstream", limit=1
    )
    assert len(result) <= 1


def test_traverse_dependencies_start_node_excluded(acyclic_graph):
    svc = CausalGraphService()
    result = svc.traverse_dependencies(
        acyclic_graph, "action:tenant-1:action-1", direction="downstream"
    )
    assert all(n.node_id != "action:tenant-1:action-1" for n in result)


def test_traverse_dependencies_missing_start_returns_empty(acyclic_graph):
    svc = CausalGraphService()
    result = svc.traverse_dependencies(
        acyclic_graph, "nonexistent-node", direction="downstream"
    )
    assert result == []


def test_get_impact_set_returns_affected_nodes(acyclic_graph):
    svc = CausalGraphService()
    changed = ["action:tenant-1:action-1"]
    result = svc.get_impact_set(acyclic_graph, changed)
    result_ids = [n.node_id for n in result]
    assert "action:tenant-1:action-2" in result_ids
    assert "action:tenant-1:action-3" in result_ids


def test_get_impact_set_excludes_seed_nodes(acyclic_graph):
    svc = CausalGraphService()
    changed = ["action:tenant-1:action-1"]
    result = svc.get_impact_set(acyclic_graph, changed)
    assert all(n.node_id not in changed for n in result)


def test_get_impact_set_multiple_changed_nodes(acyclic_graph):
    svc = CausalGraphService()
    changed = ["action:tenant-1:action-1", "action:tenant-1:action-2"]
    result = svc.get_impact_set(acyclic_graph, changed)
    result_ids = [n.node_id for n in result]
    assert "action:tenant-1:action-3" in result_ids
    assert "action:tenant-1:action-1" not in result_ids


def test_get_impact_set_empty_on_leaf_node(acyclic_graph):
    svc = CausalGraphService()
    changed = ["action:tenant-1:action-3"]
    result = svc.get_impact_set(acyclic_graph, changed)
    assert result == []


def test_get_impact_set_respects_limit():
    svc = CausalGraphService()
    nodes = {}
    edges = []
    prev = "n0"
    for i in range(1, 20):
        nid = "n" + str(i)
        nodes[nid] = _make_action_node(nid, tenant_id="t1", entity_id=nid)
        edges.append(_make_edge("e" + str(i), prev, nid, tenant_id="t1"))
        prev = nid
    g = RecoveryGraph(
        graph_id="g-long", tenant_id="t1", incident_id="inc",
        root_action_id="n0", version=1, nodes=list(nodes.values()), edges=edges,
    )
    result = svc.get_impact_set(g, ["n0"], limit=5)
    assert len(result) <= 5


def test_get_impact_set_no_duplicates():
    svc = CausalGraphService()
    n1 = _make_action_node("a", tenant_id="t1", entity_id="a")
    n2 = _make_action_node("b", tenant_id="t1", entity_id="b")
    e1 = _make_edge("e1", "a", "b", tenant_id="t1")
    e2 = _make_edge("e2", "b", "a", tenant_id="t1")
    g = RecoveryGraph(
        graph_id="g-diamond", tenant_id="t1", incident_id="inc",
        root_action_id="a", version=1, nodes=[n1, n2], edges=[e1, e2],
    )
    result = svc.get_impact_set(g, ["a"])
    result_ids = [n.node_id for n in result]
    assert len(result_ids) == len(set(result_ids))


# ===========================================================================
# Feature 61 - Graph versioning with immutable versions and graph diffing
# ===========================================================================


@pytest.mark.asyncio
async def test_create_snapshot_captures_nodes(acyclic_graph):
    svc = GraphIntegrationService()
    snap = svc.create_snapshot(acyclic_graph)
    assert len(snap.nodes) == len(acyclic_graph.nodes)


@pytest.mark.asyncio
async def test_snapshot_records_version(acyclic_graph):
    svc = GraphIntegrationService()
    bumped = svc.bump_version(acyclic_graph, increment=4)
    snap = svc.create_snapshot(bumped)
    assert snap.version == acyclic_graph.version + 4


@pytest.mark.asyncio
async def test_bump_version_returns_new_instance(acyclic_graph):
    svc = GraphIntegrationService()
    bumped = svc.bump_version(acyclic_graph, increment=2)
    assert bumped is not acyclic_graph
    assert bumped.version == acyclic_graph.version + 2


@pytest.mark.asyncio
async def test_bump_version_preserves_original(acyclic_graph):
    svc = GraphIntegrationService()
    original_version = acyclic_graph.version
    svc.bump_version(acyclic_graph, increment=5)
    assert acyclic_graph.version == original_version


@pytest.mark.asyncio
async def test_bump_version_increments_by_one_by_default(acyclic_graph):
    svc = GraphIntegrationService()
    bumped = svc.bump_version(acyclic_graph)
    assert bumped.version == acyclic_graph.version + 1


@pytest.mark.asyncio
async def test_bump_version_records_previous_version(acyclic_graph):
    svc = GraphIntegrationService()
    bumped = svc.bump_version(acyclic_graph, increment=1)
    assert bumped.metadata.get("previous_version") == acyclic_graph.version


@pytest.mark.asyncio
async def test_bump_version_updates_timestamp(acyclic_graph):
    svc = GraphIntegrationService()
    before = datetime.now(UTC)
    bumped = svc.bump_version(acyclic_graph)
    assert bumped.updated_at >= before


@pytest.mark.asyncio
async def test_compute_diff_added_nodes(acyclic_graph):
    svc = GraphIntegrationService()
    n1 = _make_action_node("n1", tenant_id="t1", entity_id="n1")
    n2 = _make_action_node("n2", tenant_id="t1", entity_id="n2")
    g1 = RecoveryGraph(
        graph_id="g", tenant_id="t1", incident_id="inc",
        root_action_id="n1", version=1, nodes=[n1], edges=[],
    )
    g2 = RecoveryGraph(
        graph_id="g", tenant_id="t1", incident_id="inc",
        root_action_id="n1", version=2, nodes=[n1, n2], edges=[],
    )
    snap1 = svc.create_snapshot(g1)
    snap2 = svc.create_snapshot(g2)
    diff = svc.compute_diff(acyclic_graph, snap1, snap2)
    assert len(diff.added_nodes) == 1
    assert diff.added_nodes[0].node_id == "n2"


@pytest.mark.asyncio
async def test_compute_diff_removed_nodes(acyclic_graph):
    svc = GraphIntegrationService()
    n1 = _make_action_node("n1", tenant_id="t1", entity_id="n1")
    n2 = _make_action_node("n2", tenant_id="t1", entity_id="n2")
    g1 = RecoveryGraph(
        graph_id="g", tenant_id="t1", incident_id="inc",
        root_action_id="n1", version=1, nodes=[n1, n2], edges=[],
    )
    g2 = RecoveryGraph(
        graph_id="g", tenant_id="t1", incident_id="inc",
        root_action_id="n1", version=2, nodes=[n1], edges=[],
    )
    snap1 = svc.create_snapshot(g1)
    snap2 = svc.create_snapshot(g2)
    diff = svc.compute_diff(acyclic_graph, snap1, snap2)
    assert len(diff.removed_nodes) == 1
    assert diff.removed_nodes[0].node_id == "n2"


@pytest.mark.asyncio
async def test_compute_diff_no_changes(acyclic_graph):
    svc = GraphIntegrationService()
    snap1 = svc.create_snapshot(acyclic_graph)
    snap2 = svc.create_snapshot(acyclic_graph)
    diff = svc.compute_diff(acyclic_graph, snap1, snap2)
    assert len(diff.added_nodes) == 0
    assert len(diff.removed_nodes) == 0
    assert len(diff.changed_nodes) == 0


@pytest.mark.asyncio
async def test_compute_diff_records_versions(acyclic_graph):
    svc = GraphIntegrationService()
    n1 = _make_action_node("n1", tenant_id="t1", entity_id="n1")
    n2 = _make_action_node("n2", tenant_id="t1", entity_id="n2")
    g1 = RecoveryGraph(
        graph_id="g", tenant_id="t1", incident_id="inc",
        root_action_id="n1", version=1, nodes=[n1], edges=[],
    )
    g2 = RecoveryGraph(
        graph_id="g", tenant_id="t1", incident_id="inc",
        root_action_id="n1", version=2, nodes=[n1, n2], edges=[],
    )
    snap1 = svc.create_snapshot(g1)
    snap2 = svc.create_snapshot(g2)
    diff = svc.compute_diff(acyclic_graph, snap1, snap2)
    assert diff.from_version == snap1.version
    assert diff.to_version == snap2.version


@pytest.mark.asyncio
async def test_snapshot_has_snapshot_id_prefix(acyclic_graph):
    svc = GraphIntegrationService()
    snap = svc.create_snapshot(acyclic_graph)
    assert snap.snapshot_id.startswith("snap-")


# ===========================================================================
# Feature 62 - Cycle detection and consistency validation
# ===========================================================================


@pytest.mark.asyncio
async def test_check_cycles_no_cycle_acyclic(acyclic_graph):
    svc = GraphIntegrationService()
    report = svc.check_cycles(acyclic_graph)
    assert report.status == CycleStatus.NO_CYCLE
    assert len(report.cycles) == 0


@pytest.mark.asyncio
async def test_check_cycles_detects_simple_cycle():
    svc = GraphIntegrationService()
    n1 = _make_action_node("a", tenant_id="t1", entity_id="a")
    n2 = _make_action_node("b", tenant_id="t1", entity_id="b")
    n3 = _make_action_node("c", tenant_id="t1", entity_id="c")
    e1 = _make_edge("e1", "a", "b", tenant_id="t1")
    e2 = _make_edge("e2", "b", "c", tenant_id="t1")
    e3 = _make_edge("e3", "c", "a", tenant_id="t1")
    g = RecoveryGraph(
        graph_id="g-cycle", tenant_id="t1", incident_id="inc",
        root_action_id="a", version=1, nodes=[n1, n2, n3], edges=[e1, e2, e3],
    )
    report = svc.check_cycles(g)
    assert report.status == CycleStatus.CYCLE_DETECTED
    assert len(report.cycles) >= 1


@pytest.mark.asyncio
async def test_check_cycles_detects_self_loop():
    svc = GraphIntegrationService()
    n1 = _make_action_node("a", tenant_id="t1", entity_id="a")
    e1 = _make_edge("e1", "a", "a", tenant_id="t1")
    g = RecoveryGraph(
        graph_id="g-self", tenant_id="t1", incident_id="inc",
        root_action_id="a", version=1, nodes=[n1], edges=[e1],
    )
    report = svc.check_cycles(g)
    assert report.status == CycleStatus.CYCLE_DETECTED


@pytest.mark.asyncio
async def test_check_cycles_report_has_cycle_nodes():
    svc = GraphIntegrationService()
    n1 = _make_action_node("a", tenant_id="t1", entity_id="a")
    n2 = _make_action_node("b", tenant_id="t1", entity_id="b")
    e1 = _make_edge("e1", "a", "b", tenant_id="t1")
    e2 = _make_edge("e2", "b", "a", tenant_id="t1")
    g = RecoveryGraph(
        graph_id="g-c2", tenant_id="t1", incident_id="inc",
        root_action_id="a", version=1, nodes=[n1, n2], edges=[e1, e2],
    )
    report = svc.check_cycles(g)
    assert "a" in report.cycle_nodes or "b" in report.cycle_nodes


@pytest.mark.asyncio
async def test_check_consistency_dangling_edges():
    svc = GraphIntegrationService()
    n1 = _make_action_node("n1", tenant_id="t1", entity_id="n1")
    dangling = _make_edge("dangling", "missing-src", "missing-tgt", tenant_id="t1")
    g = RecoveryGraph(
        graph_id="g-dang", tenant_id="t1", incident_id="inc",
        root_action_id="n1", version=1, nodes=[n1], edges=[dangling],
    )
    report = svc.check_consistency(g)
    assert report.level == ConsistencyLevel.INCONSISTENT
    assert len(report.dangling_edges) >= 1


@pytest.mark.asyncio
async def test_check_consistency_orphan_action_node():
    svc = GraphIntegrationService()
    n1 = _make_action_node("lonely", tenant_id="t1", entity_id="lonely")
    g = RecoveryGraph(
        graph_id="g-orphan", tenant_id="t1", incident_id="inc",
        root_action_id="lonely", version=1, nodes=[n1], edges=[],
    )
    report = svc.check_consistency(g)
    assert "lonely" in report.orphan_nodes


@pytest.mark.asyncio
async def test_check_consistency_duplicate_edges():
    svc = GraphIntegrationService()
    n1 = _make_action_node("a", tenant_id="t1", entity_id="a")
    n2 = _make_action_node("b", tenant_id="t1", entity_id="b")
    e1 = _make_edge("e1", "a", "b", tenant_id="t1")
    e2 = _make_edge("e2", "a", "b", tenant_id="t1")
    g = RecoveryGraph(
        graph_id="g-dup", tenant_id="t1", incident_id="inc",
        root_action_id="a", version=1, nodes=[n1, n2], edges=[e1, e2],
    )
    report = svc.check_consistency(g)
    assert len(report.duplicate_edges) >= 1


@pytest.mark.asyncio
async def test_check_consistency_no_issues_clean_graph(acyclic_graph):
    svc = GraphIntegrationService()
    report = svc.check_consistency(acyclic_graph)
    assert report.level == ConsistencyLevel.CONSISTENT
    assert len(report.issues) == 0


@pytest.mark.asyncio
async def test_check_consistency_temporal_violation():
    svc = GraphIntegrationService()
    now = datetime.now(UTC)
    past = datetime(2020, 1, 1, tzinfo=UTC)
    n1 = _make_action_node("a", tenant_id="t1", entity_id="a")
    n2 = _make_action_node("b", tenant_id="t1", entity_id="b")
    e1 = GraphEdge(
        edge_id="e1", tenant_id="t1",
        source_node_id="a", target_node_id="b",
        relation=GraphRelation.DEPENDS_ON,
        valid_at=now, valid_until=past,
    )
    g = RecoveryGraph(
        graph_id="g-temp", tenant_id="t1", incident_id="inc",
        root_action_id="a", version=1, nodes=[n1, n2], edges=[e1],
    )
    report = svc.check_consistency(g)
    assert len(report.temporal_violations) >= 1


@pytest.mark.asyncio
async def test_check_cycles_report_has_graph_id(acyclic_graph):
    svc = GraphIntegrationService()
    report = svc.check_cycles(acyclic_graph)
    assert report.graph_id == acyclic_graph.graph_id


@pytest.mark.asyncio
async def test_check_consistency_report_has_graph_id(acyclic_graph):
    svc = GraphIntegrationService()
    report = svc.check_consistency(acyclic_graph)
    assert report.graph_id == acyclic_graph.graph_id


# ===========================================================================
# Feature 63 - Recovery-plan extraction from graph relationships
# ===========================================================================


@pytest.mark.asyncio
async def test_extract_recovery_plan_returns_dict(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert isinstance(plan, dict)


@pytest.mark.asyncio
async def test_extract_recovery_plan_has_steps(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert "steps" in plan
    assert len(plan["steps"]) >= 1


@pytest.mark.asyncio
async def test_extract_recovery_plan_identifies_roots(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert "roots" in plan
    assert "action:tenant-1:action-1" in plan["roots"]


@pytest.mark.asyncio
async def test_extract_recovery_plan_identifies_leaves(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert "leaves" in plan
    assert "action:tenant-1:action-3" in plan["leaves"]


@pytest.mark.asyncio
async def test_extract_recovery_plan_includes_resources(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert "resources" in plan
    assert plan["total_resources"] >= 1


@pytest.mark.asyncio
async def test_extract_recovery_plan_valid_when_consistent(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert plan["is_valid"] is True
    assert plan["cycles_detected"] is False


@pytest.mark.asyncio
async def test_extract_recovery_plan_invalid_with_cycles():
    svc = GraphIntegrationService()
    n1 = _make_action_node("a", tenant_id="t1", entity_id="a")
    n2 = _make_action_node("b", tenant_id="t1", entity_id="b")
    e1 = _make_edge("e1", "a", "b", tenant_id="t1")
    e2 = _make_edge("e2", "b", "a", tenant_id="t1")
    g = RecoveryGraph(
        graph_id="g-plan-cycle", tenant_id="t1", incident_id="inc",
        root_action_id="a", version=1, nodes=[n1, n2], edges=[e1, e2],
    )
    plan = svc.extract_recovery_plan(g)
    assert plan["is_valid"] is False
    assert plan["cycles_detected"] is True
    assert len(plan["cycles"]) >= 1


@pytest.mark.asyncio
async def test_extract_recovery_plan_has_plan_id(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert "plan_id" in plan
    assert acyclic_graph.graph_id in plan["plan_id"]


@pytest.mark.asyncio
async def test_extract_recovery_plan_reverse_order(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert "reverse_execution_order" in plan
    assert len(plan["reverse_execution_order"]) >= 1


@pytest.mark.asyncio
async def test_extract_recovery_plan_steps_have_depends_on(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    action_steps = [s for s in plan["steps"] if s["entity_id"] == "action-2"]
    assert len(action_steps) == 1
    assert "action:tenant-1:action-1" in action_steps[0]["depends_on"]


@pytest.mark.asyncio
async def test_extract_recovery_plan_metadata(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    assert plan["tenant_id"] == "tenant-1"
    assert plan["incident_id"] == "inc-1"
    assert plan["total_steps"] == len(plan["steps"])


@pytest.mark.asyncio
async def test_extract_recovery_plan_total_steps_matches(acyclic_graph):
    svc = GraphIntegrationService()
    plan = svc.extract_recovery_plan(acyclic_graph)
    action_step_count = len([s for s in plan["steps"] if s["tool"]])
    assert action_step_count >= 1
