from __future__ import annotations

import secrets
from datetime import UTC, datetime

from app.domain.entities.recovery_graph_types import (
    ConsistencyLevel,
    ConsistencyReport,
    CycleReport,
    CycleStatus,
    GraphDiff,
    GraphSnapshot,
    RecoveryGraph,
)
from app.domain.repositories.recovery_graph_repository import RecoveryGraphRepository
from app.domain.services.graph_integration_service import GraphIntegrationService


class InMemoryRecoveryGraphRepository(RecoveryGraphRepository):
    """In-memory implementation of :class:RecoveryGraphRepository.

    Tenant-scoped: all reads and writes are validated against the
    tenant_id on the stored entity. Suitable for unit tests and
    single-process deployments.
    """

    def __init__(self) -> None:
        self._graphs: dict[str, RecoveryGraph] = {}
        self._snapshots: dict[str, dict[int, GraphSnapshot]] = {}
        self._graph_integration = GraphIntegrationService()

    async def get_graph(self, tenant_id: str, graph_id: str) -> RecoveryGraph | None:
        graph = self._graphs.get(graph_id)
        if graph is not None and graph.tenant_id == tenant_id:
            return graph
        return None

    async def get_by_incident(
        self,
        tenant_id: str,
        incident_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryGraph], int]:
        matches = [
            g
            for g in self._graphs.values()
            if g.tenant_id == tenant_id and g.incident_id == incident_id
        ]
        total = len(matches)
        page = matches[offset : offset + limit]
        return page, total

    async def get_by_root_action(
        self,
        tenant_id: str,
        root_action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryGraph], int]:
        matches = [
            g
            for g in self._graphs.values()
            if g.tenant_id == tenant_id and g.root_action_id == root_action_id
        ]
        total = len(matches)
        page = matches[offset : offset + limit]
        return page, total

    async def save(self, graph: RecoveryGraph) -> RecoveryGraph:
        self._graphs[graph.graph_id] = graph
        return graph

    async def update_version(
        self,
        tenant_id: str,
        graph_id: str,
        version: int,
    ) -> RecoveryGraph | None:
        graph = self._graphs.get(graph_id)
        if graph is None or graph.tenant_id != tenant_id:
            return None
        updated = RecoveryGraph(
            graph_id=graph.graph_id,
            tenant_id=graph.tenant_id,
            incident_id=graph.incident_id,
            root_action_id=graph.root_action_id,
            version=version,
            nodes=graph.nodes,
            edges=graph.edges,
            metadata=graph.metadata,
            created_at=graph.created_at,
            updated_at=datetime.now(UTC),
        )
        self._graphs[graph_id] = updated
        return updated

    async def snapshot(
        self,
        tenant_id: str,
        graph_id: str,
        version: int,
    ) -> GraphSnapshot | None:
        graph = self._graphs.get(graph_id)
        if graph is None or graph.tenant_id != tenant_id:
            return None
        if graph.version != version:
            return None
        if graph_id not in self._snapshots:
            self._snapshots[graph_id] = {}
        snap = GraphSnapshot(
            snapshot_id=f"snap-{graph_id}-{version}-{secrets.token_hex(8)}",
            tenant_id=tenant_id,
            graph_id=graph_id,
            version=version,
            nodes=list(graph.nodes),
            edges=list(graph.edges),
            metadata={**graph.metadata, "captured_at": datetime.now(UTC).isoformat()},
        )
        self._snapshots[graph_id][version] = snap
        return snap

    async def diff(
        self,
        tenant_id: str,
        graph_id: str,
        from_version: int,
        to_version: int,
    ) -> GraphDiff | None:
        snapshots = self._snapshots.get(graph_id, {})
        from_snap = snapshots.get(from_version)
        to_snap = snapshots.get(to_version)
        if from_snap is None or to_snap is None:
            return None
        if from_snap.tenant_id != tenant_id or to_snap.tenant_id != tenant_id:
            return None
        graph = self._graphs.get(graph_id)
        if graph is None or graph.tenant_id != tenant_id:
            return None
        return self._graph_integration.compute_diff(graph, from_snap, to_snap)

    async def check_consistency(self, tenant_id: str, graph_id: str) -> ConsistencyReport:
        graph = self._graphs.get(graph_id)
        if graph is None or graph.tenant_id != tenant_id:
            return ConsistencyReport(
                report_id=f"consistency-{graph_id}-{secrets.token_hex(8)}",
                tenant_id=tenant_id,
                graph_id=graph_id,
                level=ConsistencyLevel.UNKNOWN,
                issues=["Graph not found"],
            )
        return self._graph_integration.check_consistency(graph)

    async def check_cycles(self, tenant_id: str, graph_id: str) -> CycleReport:
        graph = self._graphs.get(graph_id)
        if graph is None or graph.tenant_id != tenant_id:
            return CycleReport(
                report_id=f"cycle-{graph_id}-{secrets.token_hex(8)}",
                tenant_id=tenant_id,
                graph_id=graph_id,
                status=CycleStatus.INCONCLUSIVE,
                details="Graph not found",
            )
        return self._graph_integration.check_cycles(graph)

    async def delete(self, tenant_id: str, graph_id: str) -> bool:
        graph = self._graphs.get(graph_id)
        if graph is None or graph.tenant_id != tenant_id:
            return False
        del self._graphs[graph_id]
        if graph_id in self._snapshots:
            del self._snapshots[graph_id]
        return True


__all__ = ["InMemoryRecoveryGraphRepository"]
