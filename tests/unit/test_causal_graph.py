from __future__ import annotations

import pytest

from app.domain.services.causal_graph_service import CausalGraphService


class StubActionRepo:
    def __init__(self, actions):
        self._actions = actions
        self._descendants = {}

    async def get_by_action_id(self, tenant_id, action_id):
        for a in self._actions:
            if a.action_id == action_id:
                return a
        return None

    async def list_descendants(self, tenant_id, action_id, *, limit, offset):
        return self._descendants.get(action_id, []), len(self._descendants.get(action_id, []))


class StubAgentRepo:
    def __init__(self, agents):
        self._agents = agents

    async def get_by_agent_id(self, tenant_id, agent_id):
        for a in self._agents:
            if a.get("agent_id") == agent_id:
                return a
        return None

    async def list_by_tenant(self, tenant_id, *, limit, offset):
        return self._agents, len(self._agents)


def make_action(**kwargs):
    defaults = {
        "action_id": "act-1",
        "tenant_id": "tenant-1",
        "agent_id": "agent-1",
        "tool": "tool",
        "resource": "res",
        "action_type": "read",
        "status": "allowed",
        "created_at": None,
        "parent_action_id": None,
    }
    defaults.update(kwargs)
    return type("ProtectedAction", (), defaults)()


def test_causal_graph_no_repos():
    service = CausalGraphService()
    assert service._action_repo is None
    assert service._agent_repo is None


def test_causal_graph_action_repo():
    action_repo = StubActionRepo([])
    service = CausalGraphService(action_repo)
    assert service._action_repo is action_repo


def test_causal_graph_agent_repo():
    agent_repo = StubAgentRepo([])
    service = CausalGraphService(agent_repo)
    assert service._agent_repo is agent_repo


@pytest.mark.asyncio
async def test_get_upstream_actions():
    actions = [
        make_action(action_id="act-3", parent_action_id="act-2"),
        make_action(action_id="act-2", parent_action_id="act-1"),
        make_action(action_id="act-1", parent_action_id=None),
    ]
    repo = StubActionRepo(actions)
    service = CausalGraphService(repo)
    result, total = await service.get_upstream_actions("tenant-1", "act-3", limit=100, offset=0)
    assert total == 2
    assert len(result) == 2
    assert result[0].action_id == "act-3"
    assert result[1].action_id == "act-2"


@pytest.mark.asyncio
async def test_get_upstream_actions_offset():
    actions = [
        make_action(action_id="act-3", parent_action_id="act-2"),
        make_action(action_id="act-2", parent_action_id="act-1"),
        make_action(action_id="act-1", parent_action_id=None),
    ]
    repo = StubActionRepo(actions)
    service = CausalGraphService(repo)
    result, total = await service.get_upstream_actions("tenant-1", "act-3", limit=1, offset=1)
    assert total == 2
    assert len(result) == 1
    assert result[0].action_id == "act-2"


@pytest.mark.asyncio
async def test_get_upstream_actions_missing():
    repo = StubActionRepo([])
    service = CausalGraphService(repo)
    result, total = await service.get_upstream_actions("tenant-1", "missing", limit=100, offset=0)
    assert total == 0
    assert result == []


@pytest.mark.asyncio
async def test_get_upstream_actions_cycle():
    actions = [
        make_action(action_id="act-1", parent_action_id="act-2"),
        make_action(action_id="act-2", parent_action_id="act-1"),
    ]
    repo = StubActionRepo(actions)
    service = CausalGraphService(repo)
    result, total = await service.get_upstream_actions("tenant-1", "act-1", limit=100, offset=0)
    assert total == 1


@pytest.mark.asyncio
async def test_get_downstream_actions():
    actions = [
        make_action(action_id="act-1"),
        make_action(action_id="act-2", parent_action_id="act-1"),
        make_action(action_id="act-3", parent_action_id="act-2"),
    ]
    repo = StubActionRepo(actions)
    repo._descendants["act-1"] = [make_action(action_id="act-2"), make_action(action_id="act-4")]
    service = CausalGraphService(repo)
    result, total = await service.get_downstream_actions("tenant-1", "act-1", limit=100, offset=0)
    assert total == 2


@pytest.mark.asyncio
async def test_get_downstream_actions_missing_root():
    repo = StubActionRepo([])
    service = CausalGraphService(repo)
    with pytest.raises(ValueError, match="Action not found"):
        await service.get_downstream_actions("tenant-1", "missing", limit=100, offset=0)


@pytest.mark.asyncio
async def test_get_incident_graph():
    actions = [
        make_action(action_id="act-1", parent_action_id=None),
        make_action(action_id="act-2", parent_action_id="act-1"),
    ]
    repo = StubActionRepo(actions)
    repo._descendants["act-1"] = [make_action(action_id="act-2")]
    service = CausalGraphService(repo)
    graph = await service.get_incident_graph("tenant-1", "act-1")
    assert graph["root_action_id"] == "act-1"
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1


@pytest.mark.asyncio
async def test_get_incident_graph_missing_root():
    repo = StubActionRepo([])
    service = CausalGraphService(repo)
    with pytest.raises(ValueError, match="Action not found"):
        await service.get_incident_graph("tenant-1", "missing")


@pytest.mark.asyncio
async def test_get_upstream_no_agent_repo():
    service = CausalGraphService()
    result = await service.get_upstream("tenant-1", "agent-1")
    assert result == []


@pytest.mark.asyncio
async def test_get_downstream_no_agent_repo():
    service = CausalGraphService()
    result = await service.get_downstream("tenant-1", "agent-1")
    assert result == []


@pytest.mark.asyncio
async def test_get_upstream_with_agents():
    agents = [
        {"agent_id": "agent-2", "parent_agent_id": "agent-1"},
        {"agent_id": "agent-3", "parent_agent_id": "agent-2"},
    ]
    repo = StubAgentRepo(agents)
    service = CausalGraphService(repo)
    result = await service.get_upstream("tenant-1", "agent-3")
    assert "agent-2" in result
    assert "agent-1" in result


@pytest.mark.asyncio
async def test_get_downstream_with_agents():
    agents = [
        {"agent_id": "agent-1", "parent_agent_id": None},
        {"agent_id": "agent-2", "parent_agent_id": "agent-1"},
        {"agent_id": "agent-3", "parent_agent_id": "agent-1"},
        {"agent_id": "agent-4", "parent_agent_id": "agent-2"},
    ]
    repo = StubAgentRepo(agents)
    service = CausalGraphService(repo)
    result = await service.get_downstream("tenant-1", "agent-1")
    assert "agent-2" in result
    assert "agent-3" in result
    assert "agent-4" in result
