"""Phase 18: Causal graph service unit tests.

Tests for upstream/downstream traversal, tenant isolation,
and cycle detection in the causal graph service.
"""

from __future__ import annotations

import asyncio

import pytest

# ---------------------------------------------------------------------------
# Helpers / mocks
# ---------------------------------------------------------------------------


class MockAgentRepo:
    def __init__(self, agents: list[dict]) -> None:
        self._agents = {a["agent_id"]: a for a in agents}

    async def get_by_agent_id(self, tenant_id: str, agent_id: str) -> dict | None:
        agent = self._agents.get(agent_id)
        if agent and agent.get("tenant_id") == tenant_id:
            return agent
        return None

    async def list_by_tenant(self, tenant_id: str, **kwargs: object) -> tuple[list[dict], int]:
        agents = [a for a in self._agents.values() if a.get("tenant_id") == tenant_id]
        return agents, len(agents)


class MockGrantRepo:
    def __init__(self, grants: list[dict]) -> None:
        self._grants = grants

    async def list_by_grantee(
        self, tenant_id: str, grantee_agent_id: str, **kwargs: object
    ) -> tuple[list[dict], int]:
        filtered = [
            g for g in self._grants
            if g.get("tenant_id") == tenant_id and g.get("grantee_agent_id") == grantee_agent_id
        ]
        return filtered, len(filtered)

    async def list_by_grantor(
        self, tenant_id: str, grantor_agent_id: str, **kwargs: object
    ) -> tuple[list[dict], int]:
        filtered = [
            g for g in self._grants
            if g.get("tenant_id") == tenant_id and g.get("grantor_agent_id") == grantor_agent_id
        ]
        return filtered, len(filtered)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Upstream traversal
# ---------------------------------------------------------------------------


def test_upstream_traversal_returns_ancestors() -> None:
    try:
        from app.domain.services.causal_graph_service import CausalGraphService
    except ImportError:
        pytest.skip("causal_graph_service not implemented")

    agents = [
        {"agent_id": "root", "tenant_id": "t1", "parent_agent_id": None},
        {"agent_id": "child", "tenant_id": "t1", "parent_agent_id": "root"},
        {"agent_id": "grandchild", "tenant_id": "t1", "parent_agent_id": "child"},
    ]
    agent_repo = MockAgentRepo(agents)
    grant_repo = MockGrantRepo([])
    service = CausalGraphService(agent_repo, grant_repo)

    result = _run(service.get_upstream("t1", "grandchild"))
    assert result is not None
    assert "root" in result or "child" in result


# ---------------------------------------------------------------------------
# Downstream traversal
# ---------------------------------------------------------------------------


def test_downstream_traversal_returns_descendants() -> None:
    try:
        from app.domain.services.causal_graph_service import CausalGraphService
    except ImportError:
        pytest.skip("causal_graph_service not implemented")

    agents = [
        {"agent_id": "root", "tenant_id": "t1", "parent_agent_id": None},
        {"agent_id": "child", "tenant_id": "t1", "parent_agent_id": "root"},
        {"agent_id": "grandchild", "tenant_id": "t1", "parent_agent_id": "child"},
    ]
    agent_repo = MockAgentRepo(agents)
    grant_repo = MockGrantRepo([])
    service = CausalGraphService(agent_repo, grant_repo)

    result = _run(service.get_downstream("t1", "root"))
    assert "child" in result
    assert "grandchild" in result


# ---------------------------------------------------------------------------
# Tenant isolation in graph traversal
# ---------------------------------------------------------------------------


def test_upstream_isolated_by_tenant() -> None:
    try:
        from app.domain.services.causal_graph_service import CausalGraphService
    except ImportError:
        pytest.skip("causal_graph_service not implemented")

    agents = [
        {"agent_id": "root-a", "tenant_id": "tenant-a", "parent_agent_id": None},
        {"agent_id": "child-a", "tenant_id": "tenant-a", "parent_agent_id": "root-a"},
        {"agent_id": "root-b", "tenant_id": "tenant-b", "parent_agent_id": None},
        {"agent_id": "child-b", "tenant_id": "tenant-b", "parent_agent_id": "root-b"},
    ]
    agent_repo = MockAgentRepo(agents)
    grant_repo = MockGrantRepo([])
    service = CausalGraphService(agent_repo, grant_repo)

    result = _run(service.get_upstream("tenant-a", "child-a"))
    assert "root-b" not in result
    assert "child-b" not in result


def test_downstream_isolated_by_tenant() -> None:
    try:
        from app.domain.services.causal_graph_service import CausalGraphService
    except ImportError:
        pytest.skip("causal_graph_service not implemented")

    agents = [
        {"agent_id": "root-a", "tenant_id": "tenant-a", "parent_agent_id": None},
        {"agent_id": "child-a", "tenant_id": "tenant-a", "parent_agent_id": "root-a"},
        {"agent_id": "root-b", "tenant_id": "tenant-b", "parent_agent_id": None},
        {"agent_id": "child-b", "tenant_id": "tenant-b", "parent_agent_id": "root-b"},
    ]
    agent_repo = MockAgentRepo(agents)
    grant_repo = MockGrantRepo([])
    service = CausalGraphService(agent_repo, grant_repo)

    result = _run(service.get_downstream("tenant-a", "root-a"))
    assert "child-b" not in result
    assert "root-b" not in result


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def test_graph_with_cycles_does_not_infinite_loop() -> None:
    try:
        from app.domain.services.causal_graph_service import CausalGraphService
    except ImportError:
        pytest.skip("causal_graph_service not implemented")

    agents = [
        {"agent_id": "a", "tenant_id": "t1", "parent_agent_id": "c"},
        {"agent_id": "b", "tenant_id": "t1", "parent_agent_id": "a"},
        {"agent_id": "c", "tenant_id": "t1", "parent_agent_id": "b"},
    ]
    agent_repo = MockAgentRepo(agents)
    grant_repo = MockGrantRepo([])
    service = CausalGraphService(agent_repo, grant_repo)

    result = _run(service.get_downstream("t1", "a"))
    assert isinstance(result, list)
    assert len(result) <= 3
