from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.services.policy_simulation_service import (
    PolicySimulationService,
)


@pytest.fixture
def service():
    return PolicySimulationService()


@pytest.mark.asyncio
async def test_simulate_policy(service):
    policies = [
        {
            "name": "block-drop",
            "blocked_patterns": ["drop table", "truncate table"],
            "score_threshold": 0.5,
        },
    ]
    test_texts = [
        "Agent will read the database",
        "Agent will drop table users",
        "Agent will update records",
    ]
    result = service.simulate_policy(policies, test_texts)

    assert result.simulation_id.startswith("sim-")
    assert len(result.results) == 3

    drop_result = result.results[1]
    assert drop_result["results"][0]["blocked"] is True
    assert "drop table" in drop_result["results"][0]["matched_patterns"]

    read_result = result.results[0]
    assert read_result["results"][0]["blocked"] is False


@pytest.mark.asyncio
async def test_simulate_policy_block_rate(service):
    policies = [
        {
            "name": "block-all",
            "blocked_patterns": ["execute", "delete", "modify"],
            "score_threshold": 0.1,
        },
    ]
    test_texts = [
        "execute action",
        "delete record",
        "read data",
    ]
    result = service.simulate_policy(policies, test_texts)

    total_checks = 3 * 1
    blocked = sum(
        1 for r in result.results for pr in r["results"] if pr["blocked"]
    )
    assert blocked >= 2
    assert len(result.policies) == 1


@pytest.mark.asyncio
async def test_compare_policies(service):
    old_policies = [
        {
            "name": "old-policy",
            "blocked_patterns": ["drop"],
            "score_threshold": 0.5,
        },
    ]
    new_policies = [
        {
            "name": "new-policy",
            "blocked_patterns": ["drop", "delete"],
            "score_threshold": 0.5,
        },
    ]
    test_texts = [
        "drop table users",
        "delete from records",
        "read data",
    ]
    comparison = service.compare_policies(old_policies, new_policies, test_texts)

    assert comparison["change_count"] >= 1
    assert comparison["new_block_count"] >= comparison["old_block_count"]
    assert "changes" in comparison


@pytest.mark.asyncio
async def test_simulate_policy_empty_texts(service):
    result = service.simulate_policy([], [])
    assert len(result.results) == 0


def test_policy_simulation_deterministic(service):
    policies = [
        {
            "name": "test",
            "blocked_patterns": ["injection"],
            "score_threshold": 0.5,
        },
    ]
    result1 = service.simulate_policy(policies, ["test injection"])
    result2 = service.simulate_policy(policies, ["test injection"])
    assert result1.simulation_id == result2.simulation_id


@pytest.mark.asyncio
async def test_get_simulation(service):
    policies = [{"name": "test", "blocked_patterns": ["x"], "score_threshold": 0.5}]
    result = service.simulate_policy(policies, ["test"])
    retrieved = service.get_simulation(result.simulation_id)
    assert retrieved is not None
    assert retrieved.simulation_id == result.simulation_id
