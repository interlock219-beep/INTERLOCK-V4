from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.entities.recovery_graph_types import (
    ConsistencyLevel,
    ConsistencyReport,
    CycleReport,
    CycleStatus,
    GraphDiff,
    GraphEdge,
    GraphNode,
    GraphNodeKind,
    GraphRelation,
    GraphSnapshot,
    RecoveryGraph,
)
from app.domain.entities.surgical_recovery_types import RecoveryEvidence
from app.domain.services.causal_graph_service import CausalGraphService
from app.domain.services.recovery_intelligence import (
    DependencyGraph,
    DependencyNode,
    RecoveryIntelligenceService,
)


@runtime_checkable
class _CausalGraphLike(Protocol):
    async def get_upstream_actions(
        self, tenant_id: str, action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[Any], int]: ...

    async def get_downstream_actions(
        self, tenant_id: str, action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[Any], int]: ...

    async def get_incident_graph(
        self, tenant_id: str, action_id: str
    ) -> dict[str, Any]: ...


class GraphIntegrationService:
    """Additive integration layer that builds tenant-scoped RecoveryGraphs.

    Bridges the three existing graph representations:

    1. ``CausalGraphService`` -- raw action parent/child + agent lineage traversal
    2. ``RecoveryIntelligenceService`` -- DependencyGraph with topological ordering
    3. ``RecoveryGraph`` types -- typed, versioned, tenant-scoped graph with
       snapshots, diffs, consistency and cycle checks

    The service is purely additive: it consumes existing repositories and
    services and produces new RecoveryGraph artifacts without modifying
    them.
    """

    def __init__(
        self,
        action_repository: Any = None,
        evidence_repository: Any = None,
        recovery_intelligence: RecoveryIntelligenceService | None = None,
        causal_graph_service: CausalGraphService | None = None,
        graph_repository: Any = None,
    ) -> None:
        self._action_repo = action_repository
        self._evidence_repo = evidence_repository
        self._intelligence = recovery_intelligence
        self._causal_graph = causal_graph_service
        self._graph_repo = graph_repository

    def _node_id(self, kind: GraphNodeKind, entity_id: str, tenant_id: str) -> str:
        return f"{kind.value}:{tenant_id}:{entity_id}"

    def _edge_id(
        self, source: str, target: str, relation: GraphRelation, tenant_id: str
    ) -> str:
        raw = f"{tenant_id}:{source}->{target}:{relation.value}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    async def build_recovery_graph_from_causal(
        self,
        tenant_id: str,
        incident_id: str,
        root_action_id: str,
    ) -> RecoveryGraph:
        """Construct a typed RecoveryGraph from the causal graph.

        Uses ``CausalGraphService.get_incident_graph`` to obtain raw
        nodes/edges, then enriches them with typed node kinds and
        edge relations.
        """
        if self._causal_graph is not None:
            raw = await self._causal_graph.get_incident_graph(tenant_id, root_action_id)
        else:
            raw = await self._build_raw_graph(tenant_id, root_action_id)

        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}

        for raw_node in raw.get("nodes", []):
            entity_id = raw_node.get("action_id", "")
            node_id = self._node_id(GraphNodeKind.ACTION, entity_id, tenant_id)
            nodes[node_id] = GraphNode(
                node_id=node_id,
                tenant_id=tenant_id,
                kind=GraphNodeKind.ACTION,
                entity_id=entity_id,
                label=raw_node.get("tool", "") + " " + raw_node.get("resource", ""),
                temporal_at=raw_node.get("created_at"),
                properties={
                    "agent_id": raw_node.get("agent_id", ""),
                    "tool": raw_node.get("tool", ""),
                    "resource": raw_node.get("resource", ""),
                    "action_type": raw_node.get("action_type", ""),
                    "status": raw_node.get("status", ""),
                    "parent_action_id": raw_node.get("parent_action_id", ""),
                },
            )

        for raw_edge in raw.get("edges", []):
            source_id = raw_edge.get("source", "")
            target_id = raw_edge.get("target", "")
            source_node = self._node_id(GraphNodeKind.ACTION, source_id, tenant_id)
            target_node = self._node_id(GraphNodeKind.ACTION, target_id, tenant_id)
            relation_str = raw_edge.get("relation", "depends_on")
            if relation_str == "parent_child":
                relation = GraphRelation.DEPENDS_ON
            else:
                relation = GraphRelation(relation_str)
            edge_id = self._edge_id(source_node, target_node, relation, tenant_id)
            edges[edge_id] = GraphEdge(
                edge_id=edge_id,
                tenant_id=tenant_id,
                source_node_id=source_node,
                target_node_id=target_node,
                relation=relation,
                properties={},
            )

        return RecoveryGraph(
            graph_id=f"g-{tenant_id}-{incident_id}-{secrets.token_hex(8)}",
            tenant_id=tenant_id,
            incident_id=incident_id,
            root_action_id=root_action_id,
            version=1,
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            metadata={
                "source": "causal_graph",
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        )

    async def _build_raw_graph(
        self, tenant_id: str, root_action_id: str
    ) -> dict[str, Any]:
        """Build a raw graph dict from the action repository directly."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: list[str] = [root_action_id]

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            action = await self._action_repo.get_by_action_id(tenant_id, current_id)
            if action is None:
                continue

            nodes.append({
                "action_id": action.action_id,
                "agent_id": action.agent_id,
                "tool": action.tool,
                "resource": action.resource,
                "action_type": action.action_type,
                "status": getattr(action.status, "value", str(action.status)),
                "parent_action_id": action.parent_action_id,
                "created_at": action.created_at,
            })

            if action.parent_action_id and action.parent_action_id not in visited:
                queue.append(action.parent_action_id)
                edges.append({
                    "source": action.parent_action_id,
                    "target": current_id,
                    "relation": "parent_child",
                })

            descendants, _ = await self._action_repo.list_descendants(
                tenant_id, current_id, limit=1000, offset=0
            )
            for desc in descendants:
                if desc.action_id not in visited:
                    queue.append(desc.action_id)
                    edges.append({
                        "source": current_id,
                        "target": desc.action_id,
                        "relation": "parent_child",
                    })

        return {"root_action_id": root_action_id, "nodes": nodes, "edges": edges}

    async def build_recovery_graph_from_dependencies(
        self,
        tenant_id: str,
        incident_id: str,
        root_action_id: str,
        dep_graph: DependencyGraph,
    ) -> RecoveryGraph:
        """Construct a RecoveryGraph from a DependencyGraph produced by
        RecoveryIntelligenceService."""
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        for action_id, node in dep_graph.nodes.items():
            node_id = self._node_id(GraphNodeKind.ACTION, action_id, tenant_id)
            nodes.append(GraphNode(
                node_id=node_id,
                tenant_id=tenant_id,
                kind=GraphNodeKind.ACTION,
                entity_id=action_id,
                label=f"{node.tool} {node.resource}",
                properties={
                    "resource": node.resource,
                    "tool": node.tool,
                    "reversibility": node.reversibility.value,
                    "depends_on": node.depends_on,
                    "children": node.children,
                },
            ))

            parent_id = node.parent_action_id
            if parent_id:
                parent_node = self._node_id(GraphNodeKind.ACTION, parent_id, tenant_id)
                edge_id = self._edge_id(parent_node, node_id, GraphRelation.DEPENDS_ON, tenant_id)
                edges.append(GraphEdge(
                    edge_id=edge_id,
                    tenant_id=tenant_id,
                    source_node_id=parent_node,
                    target_node_id=node_id,
                    relation=GraphRelation.DEPENDS_ON,
                    properties={},
                ))

            for dep_id in node.depends_on:
                dep_node = self._node_id(GraphNodeKind.ACTION, dep_id, tenant_id)
                dep_edge_id = self._edge_id(dep_node, node_id, GraphRelation.DEPENDS_ON, tenant_id)
                edges.append(GraphEdge(
                    edge_id=dep_edge_id,
                    tenant_id=tenant_id,
                    source_node_id=dep_node,
                    target_node_id=node_id,
                    relation=GraphRelation.DEPENDS_ON,
                    properties={"inferred": True},
                ))

        resource_nodes: dict[str, GraphNode] = {}
        for node in nodes:
            resource = node.properties.get("resource", "")
            if resource and resource not in resource_nodes:
                rid = self._node_id(GraphNodeKind.RESOURCE, resource, tenant_id)
                resource_nodes[resource] = GraphNode(
                    node_id=rid,
                    tenant_id=tenant_id,
                    kind=GraphNodeKind.RESOURCE,
                    entity_id=resource,
                    label=resource,
                    properties={},
                )
                r_edge_id = self._edge_id(rid, node.node_id, GraphRelation.OBSERVED_AT, tenant_id)
                edges.append(GraphEdge(
                    edge_id=r_edge_id,
                    tenant_id=tenant_id,
                    source_node_id=rid,
                    target_node_id=node.node_id,
                    relation=GraphRelation.OBSERVED_AT,
                    properties={},
                ))

        all_nodes = nodes + list(resource_nodes.values())
        graph_hash = self._compute_graph_hash(all_nodes, edges)

        return RecoveryGraph(
            graph_id=f"g-{tenant_id}-{incident_id}-{secrets.token_hex(8)}",
            tenant_id=tenant_id,
            incident_id=incident_id,
            root_action_id=root_action_id,
            version=1,
            nodes=all_nodes,
            edges=edges,
            metadata={
                "source": "dependency_graph",
                "topological_order": dep_graph.topological_order,
                "reverse_topological_order": dep_graph.reverse_topological_order,
                "cycles": dep_graph.cycles,
                "graph_hash": graph_hash,
            },
        )

    async def build_graph_with_evidence(
        self,
        tenant_id: str,
        graph: RecoveryGraph,
        evidence_list: list[RecoveryEvidence],
    ) -> RecoveryGraph:
        """Annotate an existing graph with evidence nodes and edges."""
        new_nodes = list(graph.nodes)
        new_edges = list(graph.edges)

        for ev in evidence_list:
            if not ev.evidence_id:
                continue
            ev_node_id = self._node_id(GraphNodeKind.VERIFICATION, ev.evidence_id, tenant_id)
            new_nodes.append(GraphNode(
                node_id=ev_node_id,
                tenant_id=tenant_id,
                kind=GraphNodeKind.VERIFICATION,
                entity_id=ev.evidence_id,
                label=f"evidence:{ev.target_resource}",
                properties={
                    "action_id": ev.action_id,
                    "target_system": ev.target_system,
                    "reversibility": ev.reversibility_classification.value,
                    "adapter_capability": ev.adapter_capability.value if ev.adapter_capability else "",
                },
            ))

            for action_node in graph.nodes:
                if action_node.kind == GraphNodeKind.ACTION and action_node.entity_id == ev.action_id:
                    ev_edge_id = self._edge_id(
                        ev_node_id, action_node.node_id, GraphRelation.OBSERVED_AT, tenant_id
                    )
                    new_edges.append(GraphEdge(
                        edge_id=ev_edge_id,
                        tenant_id=tenant_id,
                        source_node_id=ev_node_id,
                        target_node_id=action_node.node_id,
                        relation=GraphRelation.OBSERVED_AT,
                        properties={},
                    ))

        return RecoveryGraph(
            graph_id=graph.graph_id,
            tenant_id=graph.tenant_id,
            incident_id=graph.incident_id,
            root_action_id=graph.root_action_id,
            version=graph.version,
            nodes=new_nodes,
            edges=new_edges,
            metadata={**graph.metadata, "evidence_enriched": True},
            created_at=graph.created_at,
            updated_at=datetime.now(UTC),
        )

    def check_consistency(self, graph: RecoveryGraph) -> ConsistencyReport:
        """Check graph consistency: dangling edges, orphan nodes, duplicates."""
        issues: list[str] = []
        dangling_edges: list[str] = []
        orphan_nodes: list[str] = []
        duplicate_edges: list[str] = []
        temporal_violations: list[str] = []

        node_ids = {n.node_id for n in graph.nodes}
        edge_seen: dict[tuple[str, str, str], int] = {}

        for edge in graph.edges:
            if edge.source_node_id not in node_ids:
                dangling_edges.append(edge.edge_id)
                issues.append(f"Dangling edge {edge.edge_id}: source node missing")
            if edge.target_node_id not in node_ids:
                dangling_edges.append(edge.edge_id)
                issues.append(f"Dangling edge {edge.edge_id}: target node missing")

            key = (edge.source_node_id, edge.target_node_id, edge.relation.value)
            if key in edge_seen:
                duplicate_edges.append(edge.edge_id)
                issues.append(f"Duplicate edge: {edge.edge_id}")
            edge_seen[key] = edge_seen.get(key, 0) + 1

        for node in graph.nodes:
            if node.kind != GraphNodeKind.TENANT:
                has_edge = any(
                    e.source_node_id == node.node_id or e.target_node_id == node.node_id
                    for e in graph.edges
                )
                if not has_edge and node.kind != GraphNodeKind.RESOURCE:
                    orphan_nodes.append(node.node_id)

        if graph.nodes:
            for edge in graph.edges:
                if edge.valid_at and edge.valid_until:
                    if edge.valid_at > edge.valid_until:
                        temporal_violations.append(edge.edge_id)
                        issues.append(f"Temporal violation: {edge.edge_id}")

        return ConsistencyReport(
            report_id=f"consistency-{graph.tenant_id}-{secrets.token_hex(8)}",
            tenant_id=graph.tenant_id,
            graph_id=graph.graph_id,
            level=ConsistencyLevel.INCONSISTENT if issues else ConsistencyLevel.CONSISTENT,
            issues=issues,
            dangling_edges=dangling_edges,
            orphan_nodes=orphan_nodes,
            duplicate_edges=duplicate_edges,
            temporal_violations=temporal_violations,
        )

    def check_cycles(self, graph: RecoveryGraph) -> CycleReport:
        """Detect directed cycles in the graph using DFS."""
        adj: dict[str, list[str]] = {}
        for node in graph.nodes:
            adj.setdefault(node.node_id, [])
        for edge in graph.edges:
            adj.setdefault(edge.source_node_id, [])
            adj.setdefault(edge.target_node_id, [])
            adj[edge.source_node_id].append(edge.target_node_id)

        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycles: list[list[str]] = []
        path: list[str] = []

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for neighbor in adj.get(node_id, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            rec_stack.discard(node_id)
            path.pop()

        for node_id in list(adj.keys()):
            if node_id not in visited:
                dfs(node_id)

        return CycleReport(
            report_id=f"cycle-{graph.tenant_id}-{secrets.token_hex(8)}",
            tenant_id=graph.tenant_id,
            graph_id=graph.graph_id,
            status=CycleStatus.CYCLE_DETECTED if cycles else CycleStatus.NO_CYCLE,
            cycles=cycles,
            cycle_nodes=[n for cycle in cycles for n in cycle],
            cycle_edges=[],
            details=f"Found {len(cycles)} cycle(s)" if cycles else "No cycles detected",
        )

    def create_snapshot(self, graph: RecoveryGraph) -> GraphSnapshot:
        """Create an immutable snapshot of the graph at its current state."""
        return GraphSnapshot(
            snapshot_id=f"snap-{graph.graph_id}-{secrets.token_hex(8)}",
            tenant_id=graph.tenant_id,
            graph_id=graph.graph_id,
            version=graph.version,
            nodes=graph.nodes,
            edges=graph.edges,
            metadata={**graph.metadata, "captured_at": datetime.now(UTC).isoformat()},
        )

    def compute_diff(
        self,
        graph: RecoveryGraph,
        from_snapshot: GraphSnapshot,
        to_snapshot: GraphSnapshot,
    ) -> GraphDiff:
        """Compute the difference between two graph snapshots."""
        from_nodes = {n.node_id for n in from_snapshot.nodes}
        to_nodes = {n.node_id for n in to_snapshot.nodes}
        from_edges = {e.edge_id for e in from_snapshot.edges}
        to_edges = {e.edge_id for e in to_snapshot.edges}

        node_map_from = {n.node_id: n for n in from_snapshot.nodes}
        node_map_to = {n.node_id: n for n in to_snapshot.nodes}
        edge_map_from = {e.edge_id: e for e in from_snapshot.edges}
        edge_map_to = {e.edge_id: e for e in to_snapshot.edges}

        added_nodes = [node_map_to[nid] for nid in to_nodes - from_nodes]
        removed_nodes = [node_map_from[nid] for nid in from_nodes - to_nodes]
        changed_nodes = [
            node_map_to[nid]
            for nid in from_nodes & to_nodes
            if node_map_from[nid] != node_map_to[nid]
        ]

        added_edges = [edge_map_to[eid] for eid in to_edges - from_edges]
        removed_edges = [edge_map_from[eid] for eid in from_edges - to_edges]
        changed_edges = [
            edge_map_to[eid]
            for eid in from_edges & to_edges
            if edge_map_from[eid] != edge_map_to[eid]
        ]

        return GraphDiff(
            diff_id=f"diff-{graph.graph_id}-{from_snapshot.version}-{to_snapshot.version}-{secrets.token_hex(8)}",
            tenant_id=graph.tenant_id,
            graph_id=graph.graph_id,
            from_version=from_snapshot.version,
            to_version=to_snapshot.version,
            added_nodes=added_nodes,
            removed_nodes=removed_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
            changed_nodes=changed_nodes,
            changed_edges=changed_edges,
        )

    def enrich_with_intelligence(
        self,
        graph: RecoveryGraph,
        dep_graph: DependencyGraph,
    ) -> RecoveryGraph:
        """Enrich a graph with topological ordering from recovery intelligence."""
        metadata = dict(graph.metadata)
        metadata["topological_order"] = dep_graph.topological_order
        metadata["reverse_topological_order"] = dep_graph.reverse_topological_order
        metadata["roots"] = dep_graph.roots
        metadata["leaves"] = dep_graph.leaves
        if dep_graph.cycles:
            metadata["cycles"] = dep_graph.cycles

        return RecoveryGraph(
            graph_id=graph.graph_id,
            tenant_id=graph.tenant_id,
            incident_id=graph.incident_id,
            root_action_id=graph.root_action_id,
            version=graph.version + 1,
            nodes=graph.nodes,
            edges=graph.edges,
            metadata=metadata,
            created_at=graph.created_at,
            updated_at=datetime.now(UTC),
        )


    async def build_unified_recovery_graph(
        self,
        tenant_id: str,
        incident_id: str,
        root_action_id: str,
        dep_graph,
    ) -> RecoveryGraph:
        """Build a unified recovery/resource graph combining causal and dependency sources.

        Merges the typed nodes and edges from both the causal graph and the
        dependency graph into a single RecoveryGraph.

        Parameters
        ----------
        tenant_id : str
        incident_id : str
        root_action_id : str
        dep_graph : DependencyGraph

        Returns
        -------
        RecoveryGraph
            A unified graph with action, resource, and dependency nodes.
        """
        causal_nodes: dict[str, GraphNode] = {}
        causal_edges: dict[str, GraphEdge] = {}

        if self._causal_graph is not None:
            raw = await self._causal_graph.get_incident_graph(tenant_id, root_action_id)

            for raw_node in raw.get("nodes", []):
                entity_id = raw_node.get("action_id", "")
                node_id = self._node_id(GraphNodeKind.ACTION, entity_id, tenant_id)
                causal_nodes[node_id] = GraphNode(
                    node_id=node_id,
                    tenant_id=tenant_id,
                    kind=GraphNodeKind.ACTION,
                    entity_id=entity_id,
                    label=raw_node.get("tool", "") + " " + raw_node.get("resource", ""),
                    temporal_at=raw_node.get("created_at"),
                    properties={
                        "agent_id": raw_node.get("agent_id", ""),
                        "tool": raw_node.get("tool", ""),
                        "resource": raw_node.get("resource", ""),
                        "action_type": raw_node.get("action_type", ""),
                        "status": raw_node.get("status", ""),
                    },
                )

            for raw_edge in raw.get("edges", []):
                source_id = raw_edge.get("source", "")
                target_id = raw_edge.get("target", "")
                source_node = self._node_id(GraphNodeKind.ACTION, source_id, tenant_id)
                target_node = self._node_id(GraphNodeKind.ACTION, target_id, tenant_id)
                relation_str = raw_edge.get("relation", "depends_on")
                relation = GraphRelation.DEPENDS_ON if relation_str == "parent_child" else GraphRelation(relation_str)
                edge_id = self._edge_id(source_node, target_node, relation, tenant_id)
                causal_edges[edge_id] = GraphEdge(
                    edge_id=edge_id,
                    tenant_id=tenant_id,
                    source_node_id=source_node,
                    target_node_id=target_node,
                    relation=relation,
                    properties={},
                )

        dep_nodes: dict[str, GraphNode] = {}
        dep_edges: dict[str, GraphEdge] = {}
        for action_id, dnode in dep_graph.nodes.items():
            node_id = self._node_id(GraphNodeKind.ACTION, action_id, tenant_id)
            if node_id not in causal_nodes:
                dep_nodes[node_id] = GraphNode(
                    node_id=node_id,
                    tenant_id=tenant_id,
                    kind=GraphNodeKind.ACTION,
                    entity_id=action_id,
                    label=f"{dnode.tool} {dnode.resource}",
                    properties={
                        "resource": dnode.resource,
                        "tool": dnode.tool,
                        "reversibility": dnode.reversibility.value,
                    },
                )
            parent_id = dnode.parent_action_id
            if parent_id:
                parent_node = self._node_id(GraphNodeKind.ACTION, parent_id, tenant_id)
                eid = self._edge_id(parent_node, node_id, GraphRelation.DEPENDS_ON, tenant_id)
                if eid not in causal_edges:
                    dep_edges[eid] = GraphEdge(
                        edge_id=eid,
                        tenant_id=tenant_id,
                        source_node_id=parent_node,
                        target_node_id=node_id,
                        relation=GraphRelation.DEPENDS_ON,
                        properties={"source": "dep_graph"},
                    )
            for dep_id in dnode.depends_on:
                dep_nid = self._node_id(GraphNodeKind.ACTION, dep_id, tenant_id)
                deid = self._edge_id(dep_nid, node_id, GraphRelation.DEPENDS_ON, tenant_id)
                if deid not in causal_edges and deid not in dep_edges:
                    dep_edges[deid] = GraphEdge(
                        edge_id=deid,
                        tenant_id=tenant_id,
                        source_node_id=dep_nid,
                        target_node_id=node_id,
                        relation=GraphRelation.DEPENDS_ON,
                        properties={"source": "dep_graph", "inferred": True},
                    )

        resource_nodes: dict[str, GraphNode] = {}
        for node in list(causal_nodes.values()) + list(dep_nodes.values()):
            resource = node.properties.get("resource", "")
            if resource and resource not in resource_nodes:
                rid = self._node_id(GraphNodeKind.RESOURCE, resource, tenant_id)
                resource_nodes[resource] = GraphNode(
                    node_id=rid,
                    tenant_id=tenant_id,
                    kind=GraphNodeKind.RESOURCE,
                    entity_id=resource,
                    label=resource,
                    properties={},
                )

        all_nodes = list(causal_nodes.values()) + list(dep_nodes.values()) + list(resource_nodes.values())
        all_edges = list(causal_edges.values()) + list(dep_edges.values())
        graph_hash = self._compute_graph_hash(all_nodes, all_edges)

        return RecoveryGraph(
            graph_id=f"g-{tenant_id}-{incident_id}-{secrets.token_hex(8)}",
            tenant_id=tenant_id,
            incident_id=incident_id,
            root_action_id=root_action_id,
            version=1,
            nodes=all_nodes,
            edges=all_edges,
            metadata={
                "source": "unified",
                "causal_node_count": len(causal_nodes),
                "dep_node_count": len(dep_nodes),
                "resource_node_count": len(resource_nodes),
                "graph_hash": graph_hash,
                "topological_order": dep_graph.topological_order,
                "cycles": dep_graph.cycles,
            },
        )

    def bump_version(self, graph: RecoveryGraph, increment: int = 1) -> RecoveryGraph:
        """Return a new RecoveryGraph with an incremented version (immutable).

        Parameters
        ----------
        graph : RecoveryGraph
            Current graph to version-bump.
        increment : int
            Number of versions to advance (default 1).

        Returns
        -------
        RecoveryGraph
            New graph with updated version number.
        """
        new_version = graph.version + increment
        return RecoveryGraph(
            graph_id=graph.graph_id,
            tenant_id=graph.tenant_id,
            incident_id=graph.incident_id,
            root_action_id=graph.root_action_id,
            version=new_version,
            nodes=list(graph.nodes),
            edges=list(graph.edges),
            metadata={
                **graph.metadata,
                "previous_version": graph.version,
                "bumped_at": datetime.now(UTC).isoformat(),
            },
            created_at=graph.created_at,
            updated_at=datetime.now(UTC),
        )

    def extract_recovery_plan(self, graph: RecoveryGraph) -> dict:
        """Extract a recovery plan from graph relationships.

        Walks the graph to identify:
        - Recovery steps from root action to leaves.
        - Reverse topological order for execution.
        - Dependencies between steps.
        - Resources involved.

        Parameters
        ----------
        graph : RecoveryGraph
            Typed recovery graph.

        Returns
        -------
        dict
            Recovery plan with steps, dependencies, resources, and metadata.
        """
        from app.domain.services.recovery_intelligence import DependencyGraph, DependencyNode

        action_nodes = [n for n in graph.nodes if n.kind == GraphNodeKind.ACTION]
        resource_nodes = [n for n in graph.nodes if n.kind == GraphNodeKind.RESOURCE]
        action_node_ids = {n.node_id for n in action_nodes}

        dep_edges = [e for e in graph.edges if e.relation == GraphRelation.DEPENDS_ON]

        step_map: dict[str, dict] = {}
        for node in action_nodes:
            step_map[node.node_id] = {
                "step_id": node.node_id,
                "entity_id": node.entity_id,
                "label": node.label,
                "tool": node.properties.get("tool", ""),
                "resource": node.properties.get("resource", ""),
                "reversibility": node.properties.get("reversibility", "unknown"),
                "depends_on": [],
                "dependents": [],
            }

        for edge in dep_edges:
            if edge.source_node_id in step_map:
                step_map[edge.source_node_id]["dependents"].append(edge.target_node_id)
            if edge.target_node_id in step_map:
                step_map[edge.target_node_id]["depends_on"].append(edge.source_node_id)

        steps = list(step_map.values())
        for step in steps:
            step["depends_on"] = list(dict.fromkeys(step["depends_on"]))
            step["dependents"] = list(dict.fromkeys(step["dependents"]))

        roots = [s for s in steps if not s["depends_on"]]
        leaves = [s for s in steps if not s["dependents"]]

        reverse_steps = []
        visited_steps: set[str] = set()
        root_ns = self._node_id(GraphNodeKind.ACTION, graph.root_action_id, graph.tenant_id)
        queue = [root_ns]
        while queue:
            current = queue.pop(0)
            if current in visited_steps:
                continue
            visited_steps.add(current)
            step = step_map.get(current)
            if step:
                reverse_steps.append(step)
            for edge in dep_edges:
                if edge.source_node_id == current and edge.target_node_id not in visited_steps:
                    queue.append(edge.target_node_id)

        resources = [
            {
                "resource_id": r.node_id,
                "entity_id": r.entity_id,
                "label": r.label,
                "affected_actions": [
                    n.node_id for n in action_nodes
                    if n.properties.get("resource", "") == r.entity_id
                ],
            }
            for r in resource_nodes
        ]

        cycles = []
        cycle_report = self.check_cycles(graph)
        if cycle_report.status == CycleStatus.CYCLE_DETECTED:
            cycles = cycle_report.cycles

        consistency = self.check_consistency(graph)
        is_valid = (
            consistency.level == ConsistencyLevel.CONSISTENT
            and not cycles
        )

        return {
            "plan_id": f"plan-{graph.graph_id}-v{graph.version}",
            "graph_id": graph.graph_id,
            "version": graph.version,
            "tenant_id": graph.tenant_id,
            "incident_id": graph.incident_id,
            "root_action_id": graph.root_action_id,
            "steps": steps,
            "reverse_execution_order": [s["step_id"] for s in reverse_steps],
            "roots": [s["step_id"] for s in roots],
            "leaves": [s["step_id"] for s in leaves],
            "resources": resources,
            "total_steps": len(steps),
            "total_resources": len(resources),
            "cycles_detected": len(cycles) > 0,
            "cycles": cycles,
            "is_valid": is_valid,
            "consistency_level": consistency.level.value,
            "issues": consistency.issues,
        }


    @staticmethod
    def _compute_graph_hash(
        nodes: list[GraphNode], edges: list[GraphEdge]
    ) -> str:
        """Compute a deterministic hash of the graph structure."""
        payload = {
            "nodes": sorted([n.node_id for n in nodes]),
            "edges": sorted([
                e.source_node_id + "->" + e.target_node_id + ":" + e.relation.value
                for e in edges
            ]),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = ["GraphIntegrationService"]
