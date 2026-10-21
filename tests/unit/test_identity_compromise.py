from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.domain.entities.agent import TrustLevel, AgentType
from app.domain.services.identity_compromise_service import IdentityCompromiseService


def _run(coro):
    return asyncio.run(coro)


def test_compromise_indicators_nonexistent_agent():
    mock_repo = AsyncMock()
    mock_repo.get_by_agent_id.return_value = None

    service = IdentityCompromiseService(mock_repo)
    indicators = _run(service.check_compromise_indicators("tenant-1", "agent-nonexistent"))

    assert len(indicators) == 0


def test_compromise_indicators_low_trust():
    fake_agent = type("Agent", (), {
        "agent_id": "agent-1",
        "agent_type": AgentType.UNKNOWN,
        "trust_level": TrustLevel.DISCOVERED,
        "description": None,
        "owner_user_id": None,
        "tenant_id": "tenant-1",
    })()

    mock_repo = AsyncMock()
    mock_repo.get_by_agent_id.return_value = fake_agent

    service = IdentityCompromiseService(mock_repo)
    indicators = _run(service.check_compromise_indicators("tenant-1", "agent-1"))

    assert len(indicators) >= 3
    types = {i.indicator_type for i in indicators}
    assert "low_trust_level" in types
    assert "unknown_agent_type" in types
    assert "missing_description" in types
    assert "unowned_agent" in types


def test_compromise_indicators_trusted_agent():
    fake_agent = type("Agent", (), {
        "agent_id": "agent-1",
        "agent_type": AgentType.SERVICE_AGENT,
        "trust_level": TrustLevel.VERIFIED,
        "description": "Test agent",
        "owner_user_id": "user-1",
        "tenant_id": "tenant-1",
    })()

    mock_repo = AsyncMock()
    mock_repo.get_by_agent_id.return_value = fake_agent

    service = IdentityCompromiseService(mock_repo)
    indicators = _run(service.check_compromise_indicators("tenant-1", "agent-1"))

    assert len(indicators) == 0


def test_compromise_summary():
    fake_agent = type("Agent", (), {
        "agent_id": "agent-1",
        "agent_type": AgentType.SERVICE_AGENT,
        "trust_level": TrustLevel.VERIFIED,
        "description": "Test agent",
        "owner_user_id": "user-1",
        "tenant_id": "tenant-1",
    })()

    mock_repo = AsyncMock()
    mock_repo.get_by_agent_id.return_value = fake_agent
    mock_repo.list_by_tenant.return_value = ([fake_agent], 1)

    service = IdentityCompromiseService(mock_repo)
    summary = _run(service.get_compromise_summary("tenant-1"))

    assert summary["total_agents"] == 1
    assert summary["agents_with_indicators"] == 0
