from __future__ import annotations

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
    Reversibility,
    RecoveryEvidence,
    CompensationType,
    RecoveryAdapterType,
)
from app.domain.services.graph_integration_service import GraphIntegrationService
from app.domain.services.recovery_intelligence import (
    DependencyGraph,
    DependencyNode,
    RecoveryIntelligenceService,
)


@pytest.fixture
def service():
    return GraphIntegrationService()


@pytest.fixture
def dep_graph():
    nodes = {
        "action-1": DependencyNode(
            action_id="action-1",
            parent_action_id=None,
            resource="resource-1",
            tool="read_tool",
            reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        ),
        "action-2": DependencyNode(
            action_id="action-2",
            parent_action_id="action-1",
            resource="resource-2",
            tool="write_tool",
            reversibility=Reversibility.MANUALLY_RECOVERABLE,
        ),
    }
    return DependencyGraph(
        nodes=nodes,
        roots=["action-1"],
        leaves=["action-2"],
        topological_order=["action-1", "action-2"],
        reverse_topological_order=["action-2", "action-1"],
        cycles=[],
    )


@pytest.mark.asyncio
async def test_build_recovery_graph_from_dependencies(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    assert graph.tenant_id == "tenant-1"
    assert graph.incident_id == "inc-1"
    assert graph.root_action_id == "action-1"
    assert graph.version == 1
    assert len(graph.nodes) >= 2
    assert len(graph.edges) >= 1


@pytest.mark.asyncio
async def test_build_recovery_graph_from_dependencies_has_resource_nodes(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    resource_nodes = [n for n in graph.nodes if n.kind == GraphNodeKind.RESOURCE]
    assert len(resource_nodes) == 2
    assert any(n.entity_id == "resource-1" for n in resource_nodes)
    assert any(n.entity_id == "resource-2" for n in resource_nodes)


@pytest.mark.asyncio
async def test_build_recovery_graph_from_dependencies_has_edges(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    edges = graph.edges
    assert len(edges) > 0
    dep_edges = [e for e in edges if e.relation == GraphRelation.DEPENDS_ON]
    assert len(dep_edges) >= 1


@pytest.mark.asyncio
async def test_build_recovery_graph_from_causal_raw(service):
    class MockCausalGraph:
        async def get_incident_graph(self, tenant_id: str, action_id: str) -> dict[str, Any]:
            return {
                "nodes": [
                    {
                        "action_id": "action-1",
                        "agent_id": "agent-1",
                        "tool": "read_tool",
                        "resource": "resource-1",
                        "action_type": "read",
                        "status": "executed",
                        "parent_action_id": "",
                    },
                    {
                        "action_id": "action-2",
                        "agent_id": "agent-1",
                        "tool": "write_tool",
                        "resource": "resource-2",
                        "action_type": "write",
                        "status": "executed",
                        "parent_action_id": "action-1",
                    },
                ],
                "edges": [
                    {"source": "action-1", "target": "action-2", "relation": "parent_child"},
                ],
            }

    svc = GraphIntegrationService(causal_graph_service=MockCausalGraph())
    graph = await svc.build_recovery_graph_from_causal("tenant-1", "inc-1", "action-1")

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert graph.metadata["source"] == "causal_graph"


@pytest.mark.asyncio
async def test_check_consistency_no_issues(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    report = service.check_consistency(graph)

    assert report.level == ConsistencyLevel.CONSISTENT
    assert len(report.issues) == 0
    assert len(report.dangling_edges) == 0
    assert len(report.duplicate_edges) == 0


@pytest.mark.asyncio
async def test_check_consistency_detects_dangling_edges(service):
    node_a = GraphNode(
        node_id="node-a", tenant_id="tenant-1", kind=GraphNodeKind.ACTION,
        entity_id="a", label="Node A",
    )
    node_b = GraphNode(
        node_id="node-b", tenant_id="tenant-1", kind=GraphNodeKind.ACTION,
        entity_id="b", label="Node B",
    )
    dangling_edge = GraphEdge(
        edge_id="edge-dangling",
        tenant_id="tenant-1",
        source_node_id="nonexistent-source",
        target_node_id="nonexistent-target",
        relation=GraphRelation.DEPENDS_ON,
    )

    graph = RecoveryGraph(
        graph_id="g-1",
        tenant_id="tenant-1",
        incident_id="inc-1",
        root_action_id="action-1",
        version=1,
        nodes=[node_a, node_b],
        edges=[dangling_edge],
    )

    report = service.check_consistency(graph)

    assert report.level == ConsistencyLevel.INCONSISTENT
    assert len(report.dangling_edges) >= 1
    assert len(report.issues) >= 1


@pytest.mark.asyncio
async def test_check_cycles_no_cycle(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    report = service.check_cycles(graph)

    assert report.status == CycleStatus.NO_CYCLE
    assert len(report.cycles) == 0


@pytest.mark.asyncio
async def test_check_cycles_detects_cycle(service):
    node_a = GraphNode(node_id="a", tenant_id="t", kind=GraphNodeKind.ACTION, entity_id="a")
    node_b = GraphNode(node_id="b", tenant_id="t", kind=GraphNodeKind.ACTION, entity_id="b")
    node_c = GraphNode(node_id="c", tenant_id="t", kind=GraphNodeKind.ACTION, entity_id="c")

    edge_ab = GraphEdge(edge_id="ab", tenant_id="t", source_node_id="a", target_node_id="b", relation=GraphRelation.DEPENDS_ON)
    edge_bc = GraphEdge(edge_id="bc", tenant_id="t", source_node_id="b", target_node_id="c", relation=GraphRelation.DEPENDS_ON)
    edge_ca = GraphEdge(edge_id="ca", tenant_id="t", source_node_id="c", target_node_id="a", relation=GraphRelation.DEPENDS_ON)

    graph = RecoveryGraph(
        graph_id="g-1",
        tenant_id="t",
        incident_id="inc-1",
        root_action_id="a",
        version=1,
        nodes=[node_a, node_b, node_c],
        edges=[edge_ab, edge_bc, edge_ca],
    )

    report = service.check_cycles(graph)

    assert report.status == CycleStatus.CYCLE_DETECTED
    assert len(report.cycles) >= 1


@pytest.mark.asyncio
async def test_create_snapshot(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    snapshot = service.create_snapshot(graph)

    assert snapshot.tenant_id == "tenant-1"
    assert snapshot.graph_id == graph.graph_id
    assert snapshot.version == graph.version
    assert len(snapshot.nodes) == len(graph.nodes)


@pytest.mark.asyncio
async def test_compute_diff(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    snap1 = service.create_snapshot(graph)

    snap2 = service.create_snapshot(graph)

    diff = service.compute_diff(graph, snap1, snap2)

    assert diff.from_version == snap1.version
    assert diff.to_version == snap2.version
    assert len(diff.added_nodes) == 0
    assert len(diff.removed_nodes) == 0


@pytest.mark.asyncio
async def test_build_graph_with_evidence(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    evidence = RecoveryEvidence(
        evidence_id="ev-1",
        action_id="action-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id="action-1",
        correlation_id="corr-1",
        incident_id="inc-1",
        target_resource="resource-1",
        target_system="system-1",
    )

    enriched = await service.build_graph_with_evidence("tenant-1", graph, [evidence])

    verification_nodes = [n for n in enriched.nodes if n.kind == GraphNodeKind.VERIFICATION]
    assert len(verification_nodes) == 1
    assert enriched.metadata.get("evidence_enriched") is True


@pytest.mark.asyncio
async def test_enrich_with_intelligence(service, dep_graph):
    graph = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )

    enriched = service.enrich_with_intelligence(graph, dep_graph)

    assert enriched.version == graph.version + 1
    assert "topological_order" in enriched.metadata
    assert enriched.metadata["topological_order"] == dep_graph.topological_order


@pytest.mark.asyncio
async def test_compute_graph_hash_deterministic(service, dep_graph):
    graph1 = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-1", "action-1", dep_graph
    )
    graph2 = await service.build_recovery_graph_from_dependencies(
        "tenant-1", "inc-2", "action-1", dep_graph
    )

    hash1 = service._compute_graph_hash(graph1.nodes, graph1.edges)
    hash2 = service._compute_graph_hash(graph2.nodes, graph2.edges)

    assert hash1 == hash2


@pytest.mark.asyncio
async def test_build_recovery_graph_from_causal_with_adapter():
    class MockCausalGraph:
        async def get_incident_graph(self, tenant_id: str, action_id: str) -> dict[str, Any]:
            return {
                "nodes": [
                    {"action_id": "a1", "agent_id": "ag1", "tool": "tool1", "resource": "res1",
                     "action_type": "read", "status": "executed", "parent_action_id": None},
                ],
                "edges": [],
            }

    svc = GraphIntegrationService(causal_graph_service=MockCausalGraph())
    graph = await svc.build_recovery_graph_from_causal("tenant-1", "inc-1", "a1")

    assert graph.graph_id.startswith("g-tenant-1")
    assert len(graph.nodes) == 1
    assert len(graph.edges) == 0
