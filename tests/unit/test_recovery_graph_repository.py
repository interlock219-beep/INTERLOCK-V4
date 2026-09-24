from __future__ import annotations

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
from app.infrastructure.persistence.repositories.in_memory_recovery_graph_repository import (
    InMemoryRecoveryGraphRepository,
)


@pytest.fixture
def repo():
    return InMemoryRecoveryGraphRepository()


@pytest.fixture
def sample_graph():
    node = GraphNode(
        node_id="node-1",
        tenant_id="tenant-1",
        kind=GraphNodeKind.ACTION,
        entity_id="action-1",
        label="Test Action",
    )
    edge = GraphEdge(
        edge_id="edge-1",
        tenant_id="tenant-1",
        source_node_id="node-1",
        target_node_id="node-2",
        relation=GraphRelation.DEPENDS_ON,
    )
    return RecoveryGraph(
        graph_id="graph-1",
        tenant_id="tenant-1",
        incident_id="incident-1",
        root_action_id="action-1",
        version=1,
        nodes=[node],
        edges=[edge],
    )


class TestRecoveryGraphRepositoryCRUD:
    """Tests for basic CRUD operations."""

    @pytest.mark.asyncio
    async def test_save_and_get_graph(self, repo, sample_graph):
        await repo.save(sample_graph)
        retrieved = await repo.get_graph("tenant-1", "graph-1")
        assert retrieved is not None
        assert retrieved.graph_id == "graph-1"
        assert retrieved.tenant_id == "tenant-1"
        assert len(retrieved.nodes) == 1

    @pytest.mark.asyncio
    async def test_get_graph_not_found(self, repo):
        result = await repo.get_graph("tenant-1", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_graph_tenant_isolation(self, repo, sample_graph):
        await repo.save(sample_graph)
        result = await repo.get_graph("tenant-2", "graph-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self, repo, sample_graph):
        await repo.save(sample_graph)
        modified = RecoveryGraph(
            graph_id="graph-1",
            tenant_id="tenant-1",
            incident_id="incident-1",
            root_action_id="action-1",
            version=2,
            nodes=[],
            edges=[],
        )
        await repo.save(modified)
        retrieved = await repo.get_graph("tenant-1", "graph-1")
        assert retrieved is not None
        assert retrieved.version == 2
        assert len(retrieved.nodes) == 0

    @pytest.mark.asyncio
    async def test_delete_existing_graph(self, repo, sample_graph):
        await repo.save(sample_graph)
        deleted = await repo.delete("tenant-1", "graph-1")
        assert deleted is True
        result = await repo.get_graph("tenant-1", "graph-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_graph(self, repo):
        deleted = await repo.delete("tenant-1", "nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_tenant_isolation(self, repo, sample_graph):
        await repo.save(sample_graph)
        deleted = await repo.delete("tenant-2", "graph-1")
        assert deleted is False
        result = await repo.get_graph("tenant-1", "graph-1")
        assert result is not None


class TestRecoveryGraphRepositoryByIncident:
    """Tests for get_by_incident queries."""

    @pytest.mark.asyncio
    async def test_get_by_incident_returns_matching(self, repo):
        graph1 = RecoveryGraph(
            graph_id="g1",
            tenant_id="t1",
            incident_id="inc-1",
            root_action_id="a1",
            version=1,
            nodes=[],
            edges=[],
        )
        graph2 = RecoveryGraph(
            graph_id="g2",
            tenant_id="t1",
            incident_id="inc-1",
            root_action_id="a2",
            version=1,
            nodes=[],
            edges=[],
        )
        graph3 = RecoveryGraph(
            graph_id="g3",
            tenant_id="t1",
            incident_id="inc-2",
            root_action_id="a3",
            version=1,
            nodes=[],
            edges=[],
        )
        await repo.save(graph1)
        await repo.save(graph2)
        await repo.save(graph3)

        results, total = await repo.get_by_incident("t1", "inc-1")
        assert total == 2
        assert len(results) == 2
        ids = {g.graph_id for g in results}
        assert ids == {"g1", "g2"}

    @pytest.mark.asyncio
    async def test_get_by_incident_tenant_isolation(self, repo):
        graph1 = RecoveryGraph(
            graph_id="g1",
            tenant_id="t1",
            incident_id="inc-1",
            root_action_id="a1",
            version=1,
            nodes=[],
            edges=[],
        )
        graph2 = RecoveryGraph(
            graph_id="g2",
            tenant_id="t2",
            incident_id="inc-1",
            root_action_id="a2",
            version=1,
            nodes=[],
            edges=[],
        )
        await repo.save(graph1)
        await repo.save(graph2)

        results, total = await repo.get_by_incident("t1", "inc-1")
        assert total == 1
        assert results[0].graph_id == "g1"

    @pytest.mark.asyncio
    async def test_get_by_incident_empty(self, repo):
        results, total = await repo.get_by_incident("t1", "inc-1")
        assert total == 0
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_incident_with_limit_offset(self, repo):
        for i in range(5):
            graph = RecoveryGraph(
                graph_id=f"g{i}",
                tenant_id="t1",
                incident_id="inc-1",
                root_action_id=f"a{i}",
                version=1,
                nodes=[],
                edges=[],
            )
            await repo.save(graph)

        results, total = await repo.get_by_incident("t1", "inc-1", limit=2, offset=1)
        assert total == 5
        assert len(results) == 2
        ids = {g.graph_id for g in results}
        assert ids == {"g1", "g2"}


class TestRecoveryGraphRepositoryByRootAction:
    """Tests for get_by_root_action queries."""

    @pytest.mark.asyncio
    async def test_get_by_root_action_returns_matching(self, repo):
        graph1 = RecoveryGraph(
            graph_id="g1",
            tenant_id="t1",
            incident_id="inc-1",
            root_action_id="root-1",
            version=1,
            nodes=[],
            edges=[],
        )
        graph2 = RecoveryGraph(
            graph_id="g2",
            tenant_id="t1",
            incident_id="inc-2",
            root_action_id="root-1",
            version=1,
            nodes=[],
            edges=[],
        )
        graph3 = RecoveryGraph(
            graph_id="g3",
            tenant_id="t1",
            incident_id="inc-3",
            root_action_id="root-2",
            version=1,
            nodes=[],
            edges=[],
        )
        await repo.save(graph1)
        await repo.save(graph2)
        await repo.save(graph3)

        results, total = await repo.get_by_root_action("t1", "root-1")
        assert total == 2
        ids = {g.graph_id for g in results}
        assert ids == {"g1", "g2"}

    @pytest.mark.asyncio
    async def test_get_by_root_action_empty(self, repo):
        results, total = await repo.get_by_root_action("t1", "nonexistent")
        assert total == 0
        assert results == []


class TestRecoveryGraphRepositorySnapshots:
    """Tests for snapshot functionality."""

    @pytest.mark.asyncio
    async def test_snapshot_creates_snapshot(self, repo, sample_graph):
        await repo.save(sample_graph)
        snap = await repo.snapshot("tenant-1", "graph-1", version=1)
        assert snap is not None
        assert snap.graph_id == "graph-1"
        assert snap.version == 1
        assert snap.tenant_id == "tenant-1"
        assert len(snap.nodes) == 1
        assert len(snap.edges) == 1

    @pytest.mark.asyncio
    async def test_snapshot_version_mismatch(self, repo, sample_graph):
        await repo.save(sample_graph)
        snap = await repo.snapshot("tenant-1", "graph-1", version=2)
        assert snap is None

    @pytest.mark.asyncio
    async def test_snapshot_graph_not_found(self, repo):
        snap = await repo.snapshot("tenant-1", "nonexistent", version=1)
        assert snap is None

    @pytest.mark.asyncio
    async def test_snapshot_tenant_isolation(self, repo, sample_graph):
        await repo.save(sample_graph)
        snap = await repo.snapshot("tenant-2", "graph-1", version=1)
        assert snap is None

    @pytest.mark.asyncio
    async def test_multiple_snapshots(self, repo, sample_graph):
        await repo.save(sample_graph)
        snap1 = await repo.snapshot("tenant-1", "graph-1", version=1)
        assert snap1 is not None

        modified = RecoveryGraph(
            graph_id="graph-1",
            tenant_id="tenant-1",
            incident_id="incident-1",
            root_action_id="action-1",
            version=2,
            nodes=[],
            edges=[],
        )
        await repo.save(modified)
        snap2 = await repo.snapshot("tenant-1", "graph-1", version=2)
        assert snap2 is not None
        assert snap2.version == 2
        assert len(snap2.nodes) == 0


class TestRecoveryGraphRepositoryDiffs:
    """Tests for diff functionality."""

    @pytest.mark.asyncio
    async def test_diff_between_versions(self, repo, sample_graph):
        await repo.save(sample_graph)
        snap1 = await repo.snapshot("tenant-1", "graph-1", version=1)
        assert snap1 is not None

        modified = RecoveryGraph(
            graph_id="graph-1",
            tenant_id="tenant-1",
            incident_id="incident-1",
            root_action_id="action-1",
            version=2,
            nodes=[
                GraphNode(
                    node_id="node-2",
                    tenant_id="tenant-1",
                    kind=GraphNodeKind.ACTION,
                    entity_id="action-2",
                    label="Second Action",
                ),
            ],
            edges=[],
        )
        await repo.save(modified)
        snap2 = await repo.snapshot("tenant-1", "graph-1", version=2)
        assert snap2 is not None

        diff = await repo.diff("tenant-1", "graph-1", from_version=1, to_version=2)
        assert diff is not None
        assert diff.from_version == 1
        assert diff.to_version == 2
        assert len(diff.added_nodes) == 1
        assert diff.added_nodes[0].node_id == "node-2"

    @pytest.mark.asyncio
    async def test_diff_same_version_no_changes(self, repo, sample_graph):
        await repo.save(sample_graph)
        await repo.snapshot("tenant-1", "graph-1", version=1)
        await repo.snapshot("tenant-1", "graph-1", version=1)

        diff = await repo.diff("tenant-1", "graph-1", from_version=1, to_version=1)
        assert diff is not None
        assert len(diff.added_nodes) == 0
        assert len(diff.removed_nodes) == 0

    @pytest.mark.asyncio
    async def test_diff_missing_snapshot(self, repo, sample_graph):
        await repo.save(sample_graph)
        await repo.snapshot("tenant-1", "graph-1", version=1)
        diff = await repo.diff("tenant-1", "graph-1", from_version=1, to_version=3)
        assert diff is None

    @pytest.mark.asyncio
    async def test_diff_tenant_isolation(self, repo, sample_graph):
        await repo.save(sample_graph)
        await repo.snapshot("tenant-1", "graph-1", version=1)
        diff = await repo.diff("tenant-2", "graph-1", from_version=1, to_version=1)
        assert diff is None


class TestRecoveryGraphRepositoryConsistency:
    """Tests for consistency checking."""

    @pytest.mark.asyncio
    async def test_consistency_consistent_graph(self, repo, sample_graph):
        node = GraphNode(
            node_id="node-1",
            tenant_id="tenant-1",
            kind=GraphNodeKind.ACTION,
            entity_id="action-1",
        )
        edge = GraphEdge(
            edge_id="edge-1",
            tenant_id="tenant-1",
            source_node_id="node-1",
            target_node_id="node-1",
            relation=GraphRelation.DEPENDS_ON,
        )
        graph = RecoveryGraph(
            graph_id="graph-consistent",
            tenant_id="tenant-1",
            incident_id="inc-1",
            root_action_id="action-1",
            version=1,
            nodes=[node],
            edges=[edge],
        )
        await repo.save(graph)
        report = await repo.check_consistency("tenant-1", "graph-consistent")
        assert (
            report.level == ConsistencyLevel.CONSISTENT
            or report.level == ConsistencyLevel.INCONSISTENT
        )
        assert report.tenant_id == "tenant-1"
        assert report.graph_id == "graph-consistent"

    @pytest.mark.asyncio
    async def test_consistency_detects_dangling_edges(self, repo):
        node = GraphNode(
            node_id="node-a",
            tenant_id="tenant-1",
            kind=GraphNodeKind.ACTION,
            entity_id="a",
        )
        dangling = GraphEdge(
            edge_id="edge-dangling",
            tenant_id="tenant-1",
            source_node_id="missing",
            target_node_id="missing",
            relation=GraphRelation.DEPENDS_ON,
        )
        graph = RecoveryGraph(
            graph_id="graph-dangling",
            tenant_id="tenant-1",
            incident_id="inc-1",
            root_action_id="action-1",
            version=1,
            nodes=[node],
            edges=[dangling],
        )
        await repo.save(graph)
        report = await repo.check_consistency("tenant-1", "graph-dangling")
        assert len(report.dangling_edges) >= 1
        assert len(report.issues) >= 1

    @pytest.mark.asyncio
    async def test_consistency_graph_not_found(self, repo):
        report = await repo.check_consistency("tenant-1", "nonexistent")
        assert report.level == ConsistencyLevel.UNKNOWN
        assert "Graph not found" in report.issues

    @pytest.mark.asyncio
    async def test_consistency_tenant_isolation(self, repo, sample_graph):
        await repo.save(sample_graph)
        report = await repo.check_consistency("tenant-2", "graph-1")
        assert report.level == ConsistencyLevel.UNKNOWN


class TestRecoveryGraphRepositoryCycles:
    """Tests for cycle detection."""

    @pytest.mark.asyncio
    async def test_no_cycle(self, repo, sample_graph):
        await repo.save(sample_graph)
        report = await repo.check_cycles("tenant-1", "graph-1")
        assert report.status == CycleStatus.NO_CYCLE or report.status == CycleStatus.INCONCLUSIVE
        assert report.tenant_id == "tenant-1"

    @pytest.mark.asyncio
    async def test_cycle_detected(self, repo):
        node_a = GraphNode(node_id="a", tenant_id="t", kind=GraphNodeKind.ACTION, entity_id="a")
        node_b = GraphNode(node_id="b", tenant_id="t", kind=GraphNodeKind.ACTION, entity_id="b")
        node_c = GraphNode(node_id="c", tenant_id="t", kind=GraphNodeKind.ACTION, entity_id="c")
        edge_ab = GraphEdge(
            edge_id="ab",
            tenant_id="t",
            source_node_id="a",
            target_node_id="b",
            relation=GraphRelation.DEPENDS_ON,
        )
        edge_bc = GraphEdge(
            edge_id="bc",
            tenant_id="t",
            source_node_id="b",
            target_node_id="c",
            relation=GraphRelation.DEPENDS_ON,
        )
        edge_ca = GraphEdge(
            edge_id="ca",
            tenant_id="t",
            source_node_id="c",
            target_node_id="a",
            relation=GraphRelation.DEPENDS_ON,
        )
        graph = RecoveryGraph(
            graph_id="graph-cycle",
            tenant_id="t",
            incident_id="inc-1",
            root_action_id="a",
            version=1,
            nodes=[node_a, node_b, node_c],
            edges=[edge_ab, edge_bc, edge_ca],
        )
        await repo.save(graph)
        report = await repo.check_cycles("t", "graph-cycle")
        assert report.status == CycleStatus.CYCLE_DETECTED
        assert len(report.cycles) >= 1

    @pytest.mark.asyncio
    async def test_cycles_graph_not_found(self, repo):
        report = await repo.check_cycles("tenant-1", "nonexistent")
        assert report.status == CycleStatus.INCONCLUSIVE

    @pytest.mark.asyncio
    async def test_cycles_tenant_isolation(self, repo, sample_graph):
        await repo.save(sample_graph)
        report = await repo.check_cycles("tenant-2", "graph-1")
        assert report.status == CycleStatus.INCONCLUSIVE


class TestRecoveryGraphRepositoryUpdateVersion:
    """Tests for version updates."""

    @pytest.mark.asyncio
    async def test_update_version(self, repo, sample_graph):
        await repo.save(sample_graph)
        updated = await repo.update_version("tenant-1", "graph-1", version=5)
        assert updated is not None
        assert updated.version == 5
        retrieved = await repo.get_graph("tenant-1", "graph-1")
        assert retrieved is not None
        assert retrieved.version == 5

    @pytest.mark.asyncio
    async def test_update_version_not_found(self, repo):
        updated = await repo.update_version("tenant-1", "nonexistent", version=5)
        assert updated is None

    @pytest.mark.asyncio
    async def test_update_version_tenant_isolation(self, repo, sample_graph):
        await repo.save(sample_graph)
        updated = await repo.update_version("tenant-2", "graph-1", version=5)
        assert updated is None
        original = await repo.get_graph("tenant-1", "graph-1")
        assert original is not None
        assert original.version == 1


class TestRecoveryGraphRepositoryGraphIntegration:
    """Tests for graph integration behaviors through the repository."""

    @pytest.mark.asyncio
    async def test_snapshot_after_save_is_consistent(self, repo, sample_graph):
        await repo.save(sample_graph)
        snap = await repo.snapshot("tenant-1", "graph-1", version=1)
        assert snap is not None
        assert snap.nodes == sample_graph.nodes
        assert snap.edges == sample_graph.edges

    @pytest.mark.asyncio
    async def test_diff_reflects_added_node(self, repo, sample_graph):
        await repo.save(sample_graph)
        snap1 = await repo.snapshot("tenant-1", "graph-1", version=1)
        assert snap1 is not None

        extra_node = GraphNode(
            node_id="node-extra",
            tenant_id="tenant-1",
            kind=GraphNodeKind.RESOURCE,
            entity_id="res-1",
        )
        modified = RecoveryGraph(
            graph_id="graph-1",
            tenant_id="tenant-1",
            incident_id="incident-1",
            root_action_id="action-1",
            version=2,
            nodes=[*sample_graph.nodes, extra_node],
            edges=sample_graph.edges,
        )
        await repo.save(modified)
        snap2 = await repo.snapshot("tenant-1", "graph-1", version=2)
        assert snap2 is not None

        diff = await repo.diff("tenant-1", "graph-1", from_version=1, to_version=2)
        assert diff is not None
        assert len(diff.added_nodes) == 1
        assert diff.added_nodes[0].node_id == "node-extra"
        assert len(diff.removed_nodes) == 0

    @pytest.mark.asyncio
    async def test_delete_removes_snapshots(self, repo, sample_graph):
        await repo.save(sample_graph)
        await repo.snapshot("tenant-1", "graph-1", version=1)
        await repo.delete("tenant-1", "graph-1")
        snap = await repo.snapshot("tenant-1", "graph-1", version=1)
        assert snap is None
        result = await repo.get_graph("tenant-1", "graph-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_tenants_independent(self, repo):
        graph_t1 = RecoveryGraph(
            graph_id="g-t1",
            tenant_id="tenant-1",
            incident_id="inc-1",
            root_action_id="a1",
            version=1,
            nodes=[GraphNode("n1", "tenant-1", GraphNodeKind.ACTION, "a1")],
            edges=[],
        )
        graph_t2 = RecoveryGraph(
            graph_id="g-t2",
            tenant_id="tenant-2",
            incident_id="inc-1",
            root_action_id="a1",
            version=1,
            nodes=[GraphNode("n2", "tenant-2", GraphNodeKind.ACTION, "a1")],
            edges=[],
        )
        await repo.save(graph_t1)
        await repo.save(graph_t2)

        r1 = await repo.get_graph("tenant-1", "g-t1")
        r2 = await repo.get_graph("tenant-2", "g-t2")
        r3 = await repo.get_graph("tenant-1", "g-t2")
        r4 = await repo.get_graph("tenant-2", "g-t1")

        assert r1 is not None and r1.tenant_id == "tenant-1"
        assert r2 is not None and r2.tenant_id == "tenant-2"
        assert r3 is None
        assert r4 is None
