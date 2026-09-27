from __future__ import annotations

from typing import Any

from app.domain.entities.agent import Agent
from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.recovery_graph_types import (
    GraphNode,
    GraphRelation,
    RecoveryGraph,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.protected_action_repository import (
    ProtectedActionRepository,
)


def _get_agent_id(agent: Agent | dict[str, Any]) -> str | None:
    if hasattr(agent, "agent_id"):
        return agent.agent_id
    if isinstance(agent, dict):
        return agent.get("agent_id")
    return None


def _get_parent_agent_id(agent: Agent | dict[str, Any]) -> str | None:
    if hasattr(agent, "parent_agent_id"):
        return agent.parent_agent_id
    if isinstance(agent, dict):
        return agent.get("parent_agent_id")
    return None


class CausalGraphService:
    """Service for traversing causal graphs.

    Supports parent/child traversal and typed RecoveryGraph
    dependency and impact traversal (Feature 60).
    """

    _action_repo: ProtectedActionRepository | None
    _agent_repo: AgentRepository | None
    _grant_repo: Any

    def __init__(self, *repos: Any) -> None:
        if repos and hasattr(repos[0], "get_by_action_id"):
            self._action_repo = repos[0]
            self._agent_repo = repos[1] if len(repos) > 1 else None
            self._grant_repo = repos[2] if len(repos) > 2 else None
        elif repos and hasattr(repos[0], "get_by_agent_id"):
            self._agent_repo = repos[0]
            self._grant_repo = repos[1] if len(repos) > 1 else None
            self._action_repo = None
        else:
            self._action_repo = None
            self._agent_repo = None
            self._grant_repo = None

    async def get_upstream_actions(
        self, tenant_id: str, action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[ProtectedAction], int]:
        assert self._action_repo is not None
        current_id = action_id
        collected: list[ProtectedAction] = []
        seen: set[str] = set()
        while current_id and len(collected) < limit + offset:
            if current_id in seen:
                break
            seen.add(current_id)
            action = await self._action_repo.get_by_action_id(tenant_id, current_id)
            if action is None:
                break
            if (
                action.parent_action_id
                and action.parent_action_id not in seen
                and len(collected) < limit + offset
            ):
                collected.append(action)
                current_id = action.parent_action_id
            else:
                break
        total = len(collected)
        return collected[offset : offset + limit], total

    async def get_downstream_actions(
        self, tenant_id: str, action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[ProtectedAction], int]:
        assert self._action_repo is not None
        root = await self._action_repo.get_by_action_id(tenant_id, action_id)
        if root is None:
            raise ValueError("Action not found")
        return await self._action_repo.list_descendants(
            tenant_id, action_id, limit=limit, offset=offset
        )

    async def get_incident_graph(self, tenant_id: str, action_id: str) -> dict[str, Any]:
        assert self._action_repo is not None
        root = await self._action_repo.get_by_action_id(tenant_id, action_id)
        if root is None:
            raise ValueError("Action not found")
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: list[Any] = [root]
        while queue:
            current = queue.pop(0)
            if current.action_id in visited:
                continue
            visited.add(current.action_id)
            nodes.append(
                {
                    "action_id": current.action_id,
                    "agent_id": current.agent_id,
                    "tool": current.tool,
                    "resource": current.resource,
                    "action_type": current.action_type,
                    "status": getattr(current.status, "value", current.status),
                    "parent_action_id": current.parent_action_id,
                    "created_at": current.created_at,
                }
            )
            if current.parent_action_id:
                parent = await self._action_repo.get_by_action_id(
                    tenant_id, current.parent_action_id
                )
                if parent is not None and parent.action_id not in visited:
                    queue.append(parent)
                    edges.append(
                        {
                            "source": parent.action_id,
                            "target": current.action_id,
                            "relation": "parent_child",
                        }
                    )
            descendants, _ = await self._action_repo.list_descendants(
                tenant_id, current.action_id, limit=1000, offset=0
            )
            for desc in descendants:
                if desc.action_id not in visited:
                    queue.append(desc)
                    edges.append(
                        {
                            "source": current.action_id,
                            "target": desc.action_id,
                            "relation": "parent_child",
                        }
                    )
        return {
            "root_action_id": action_id,
            "nodes": nodes,
            "edges": edges,
        }

    async def get_upstream(self, tenant_id: str, agent_id: str) -> list[str]:
        if self._agent_repo is None:
            return []
        current_id = agent_id
        collected: list[str] = []
        seen: set[str] = set()
        while current_id:
            if current_id in seen:
                break
            seen.add(current_id)
            agent = await self._agent_repo.get_by_agent_id(tenant_id, current_id)
            if agent is None:
                break
            parent_id = _get_parent_agent_id(agent)
            if parent_id and parent_id not in seen:
                collected.append(parent_id)
            current_id = parent_id or ""
        return collected

    async def get_downstream(self, tenant_id: str, agent_id: str) -> list[str]:
        if self._agent_repo is None:
            return []
        all_agents, _ = await self._agent_repo.list_by_tenant(tenant_id, limit=1000, offset=0)
        raw_children: list[str | None] = [
            _get_agent_id(a) for a in all_agents if _get_parent_agent_id(a) == agent_id
        ]
        children = [c for c in raw_children if c is not None]
        result: list[str] = list(children)
        visited: set[str] = set(children)
        queue: list[str] = list(children)
        while queue:
            current = queue.pop(0)
            grandchildren: list[str] = []
            for a in all_agents:
                gc = _get_agent_id(a)
                if gc is not None and _get_parent_agent_id(a) == current and gc not in visited:
                    grandchildren.append(gc)
            for gc in grandchildren:
                visited.add(gc)
                result.append(gc)
                queue.append(gc)
        return result

    def traverse_dependencies(
        self,
        graph: RecoveryGraph,
        start_node_id: str,
        direction: str = "downstream",
        limit: int = 100,
    ) -> list[GraphNode]:
        """Traverse DEPENDS_ON edges in the typed RecoveryGraph.

        Args:
          graph: RecoveryGraph to traverse.
          start_node_id: Node to start traversal from.
          direction: "downstream" for dependents, "upstream" for dependencies.
          limit: Maximum nodes to return.

        Returns list[GraphNode] reachable via DEPENDS_ON edges.
        """
        if direction not in ("upstream", "downstream"):
            raise ValueError(f"direction must be upstream or downstream, got {direction!r}")
        adj: dict[str, list[str]] = {}
        for graph_node in graph.nodes:
            adj.setdefault(graph_node.node_id, [])
        for edge in graph.edges:
            if edge.relation == GraphRelation.DEPENDS_ON:
                if direction == "downstream":
                    adj.setdefault(edge.source_node_id, [])
                    adj[edge.source_node_id].append(edge.target_node_id)
                else:
                    adj.setdefault(edge.target_node_id, [])
                    adj[edge.target_node_id].append(edge.source_node_id)
        visited: set[str] = set()
        result: list[GraphNode] = []
        queue: list[str] = [start_node_id]
        visited.add(start_node_id)
        node_map: dict[str, GraphNode] = {n.node_id: n for n in graph.nodes}
        while queue and len(result) < limit:
            current = queue.pop(0)
            found_node: GraphNode | None = node_map.get(current)
            if found_node is not None and current != start_node_id:
                result.append(found_node)
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return result

    def get_impact_set(
        self, graph: RecoveryGraph, changed_node_ids: list[str], limit: int = 200
    ) -> list[GraphNode]:
        """Compute nodes transitively impacted by changes.

        Walks DEPENDS_ON edges downstream from changed_node_ids.

        Args:
          graph: RecoveryGraph.
          changed_node_ids: Nodes whose change is being assessed.
          limit: Maximum impacted nodes to return.

        Returns list[GraphNode] of affected nodes (seed excluded).
        """
        adj: dict[str, list[str]] = {}
        for graph_node in graph.nodes:
            adj.setdefault(graph_node.node_id, [])
        for edge in graph.edges:
            if edge.relation == GraphRelation.DEPENDS_ON:
                adj.setdefault(edge.source_node_id, [])
                adj[edge.source_node_id].append(edge.target_node_id)
        visited: set[str] = set()
        result: list[GraphNode] = []
        node_map: dict[str, GraphNode] = {n.node_id: n for n in graph.nodes}
        queue: list[str] = list(changed_node_ids)
        while queue and len(result) < limit:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            found_node: GraphNode | None = node_map.get(current)
            if found_node is not None and current not in changed_node_ids:
                result.append(found_node)
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        return result


__all__ = ["CausalGraphService"]
