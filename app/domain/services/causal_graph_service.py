from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.entities.protected_action import ProtectedAction


def _get_agent_id(agent: Any) -> str | None:
    if hasattr(agent, "agent_id"):
        return agent.agent_id  # type: ignore[no-any-return]
    if isinstance(agent, dict):
        return agent.get("agent_id")
    return None


def _get_parent_agent_id(agent: Any) -> str | None:
    if hasattr(agent, "parent_agent_id"):
        return agent.parent_agent_id  # type: ignore[no-any-return]
    if isinstance(agent, dict):
        return agent.get("parent_agent_id")
    return None


class CausalGraphService:
    """Service for traversing causal graphs via parent_action_id and parent_agent_id."""

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
        self,
        tenant_id: str,
        action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]:
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
        self,
        tenant_id: str,
        action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ProtectedAction], int]:
        root = await self._action_repo.get_by_action_id(tenant_id, action_id)
        if root is None:
            raise ValueError("Action not found")
        return await self._action_repo.list_descendants(  # type: ignore[no-any-return]
            tenant_id, action_id, limit=limit, offset=offset
        )

    async def get_incident_graph(self, tenant_id: str, action_id: str) -> dict[str, Any]:
        root = await self._action_repo.get_by_action_id(tenant_id, action_id)
        if root is None:
            raise ValueError("Action not found")
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue = [root]
        while queue:
            current = queue.pop(0)
            if current.action_id in visited:
                continue
            visited.add(current.action_id)
            nodes.append({
                "action_id": current.action_id,
                "agent_id": current.agent_id,
                "tool": current.tool,
                "resource": current.resource,
                "action_type": current.action_type,
                "status": getattr(current.status, "value", current.status),
                "parent_action_id": current.parent_action_id,
                "created_at": current.created_at,
            })
            if current.parent_action_id:
                parent = await self._action_repo.get_by_action_id(
                    tenant_id, current.parent_action_id
                )
                if parent is not None and parent.action_id not in visited:
                    queue.append(parent)
                    edges.append({
                        "source": parent.action_id,
                        "target": current.action_id,
                        "relation": "parent_child",
                    })
            descendants, _ = await self._action_repo.list_descendants(
                tenant_id, current.action_id, limit=1000, offset=0
            )
            for desc in descendants:
                if desc.action_id not in visited:
                    queue.append(desc)
                    edges.append({
                        "source": current.action_id,
                        "target": desc.action_id,
                        "relation": "parent_child",
                    })
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
        raw_children = [
            _get_agent_id(a)
            for a in all_agents
            if _get_parent_agent_id(a) == agent_id
        ]
        children = [c for c in raw_children if c is not None]
        result: list[str] = list(children)
        visited: set[str] = set(children)
        queue = list(children)
        while queue:
            current = queue.pop(0)
            grandchildren = [
                gc
                for a in all_agents
                for gc in [_get_agent_id(a)]
                if _get_parent_agent_id(a) == current
                and gc is not None
                and gc not in visited
            ]
            for gc in grandchildren:
                visited.add(gc)
                result.append(gc)
                queue.append(gc)
        return result
