from __future__ import annotations

import json
from datetime import UTC, datetime
import dataclasses
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.domain.entities.agent import Agent, AgentStatus, AgentType, RiskClassification, TrustLevel
from app.domain.entities.authority_grant import (
    AuthorityGrant,
    AuthorityScope,
    AuthorityStatus,
)
from app.domain.entities.containment_event import (
    ContainmentEvent,
    ContainmentMode,
    ContainmentStatus,
)
from app.domain.entities.execution_token import ExecutionToken, TokenStatus
from app.domain.entities.protected_action import (
    ActionStatus,
    ProtectedAction,
)
from app.domain.services.advanced_containment_service import AdvancedContainmentService


# ------------------------------------------------------------------ #
# Stub / fake repositories                                           #
# ------------------------------------------------------------------ #

class FakeAgent:
    def __init__(self, agent_id, status=AgentStatus.ACTIVE, risk=RiskClassification.MEDIUM,
                 parent_agent_id=None, owner_user_id=None):
        self.agent_id = agent_id
        self.tenant_id = "tenant-1"
        self.status = status
        self.risk_classification = risk
        self.parent_agent_id = parent_agent_id
        self.owner_user_id = owner_user_id


class StubAgentRepo:
    def __init__(self, agents):
        self._agents = {a.agent_id: a for a in agents}
        self.status_updates = []

    async def get_by_agent_id(self, tenant_id, agent_id):
        return self._agents.get(agent_id)

    async def update_status(self, tenant_id, agent_id, status):
        self.status_updates.append((agent_id, status))
        if agent_id in self._agents:
            self._agents[agent_id].status = status

    async def list_by_tenant(self, tenant_id, *, limit, offset, status=None, agent_type=None):
        return list(self._agents.values()), len(self._agents)


class StubGrantRepo:
    def __init__(self, grants):
        self._grants = grants
        self.revoked = []

    async def list_by_grantee(self, tenant_id, grantee_id, *, limit, offset):
        result = [g for g in self._grants if g.grantee_agent_id == grantee_id]
        return result, len(result)

    async def revoke(self, tenant_id, grant_id, initiated_by):
        self.revoked.append(grant_id)
        import dataclasses
        for i, g in enumerate(self._grants):
            if g.grant_id == grant_id:
                self._grants[i] = dataclasses.replace(g, status=AuthorityStatus.REVOKED)


class StubContainmentRepo:
    def __init__(self):
        self._saved = []
        self._events = {}

    async def save(self, event):
        self._saved.append(event)
        self._events[event.containment_id] = event
        return event

    async def get_by_containment_id(self, tenant_id, containment_id):
        return self._events.get(containment_id)

    async def update_status(self, tenant_id, containment_id, status, result_details=None):
        event = self._events.get(containment_id)
        if event is not None:
            merged = {**(event.result_details or {}), **(result_details or {})}
            import dataclasses
            new_event = dataclasses.replace(event, status=status, result_details=merged)
            self._events[containment_id] = new_event
            return new_event
        return None


class StubTokenRepo:
    def __init__(self, tokens):
        self._tokens = {t.token_id: t for t in tokens}
        self.revoked = []

    async def list_by_agent(self, tenant_id, agent_id, *, status, limit, offset):
        result = [t for t in self._tokens.values()
                  if t.agent_id == agent_id and t.status == status]
        return result, len(result)

    async def revoke(self, tenant_id, token_id):
        self.revoked.append(token_id)
        if token_id in self._tokens:
            import dataclasses
            self._tokens[token_id] = dataclasses.replace(self._tokens[token_id], status=TokenStatus.REVOKED)


class StubActionRepo:
    def __init__(self, actions):
        self._actions = {a.action_id: a for a in actions}
        self.updated = []

    async def list_by_agent(self, tenant_id, agent_id, *, limit, offset):
        result = [a for a in self._actions.values() if a.agent_id == agent_id]
        return result, len(result)

    async def update_status(self, tenant_id, action_id, status):
        self.updated.append((action_id, status))
        if action_id in self._actions:
            self._actions[action_id].status = status


def make_agent(agent_id, status=AgentStatus.ACTIVE, risk=RiskClassification.MEDIUM,
               parent_agent_id=None, owner_user_id=None):
    return FakeAgent(
        agent_id=agent_id,
        status=status,
        risk=risk,
        parent_agent_id=parent_agent_id,
        owner_user_id=owner_user_id,
    )


def make_grant(grant_id, grantee_id, scope=AuthorityScope.READ, status=AuthorityStatus.ACTIVE,
               delegation_depth=1):
    return AuthorityGrant(
        grant_id=grant_id,
        tenant_id="tenant-1",
        grantor_agent_id="grantor-1",
        grantee_agent_id=grantee_id,
        resource="resource",
        scope=scope,
        status=status,
        delegation_depth=delegation_depth,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def make_token(token_id, agent_id, status=TokenStatus.ACTIVE):
    return ExecutionToken(
        token_id=token_id,
        tenant_id="tenant-1",
        jti="jti-" + token_id,
        agent_id=agent_id,
        tool="tool",
        status=status,
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
    )


def make_action(action_id, agent_id, status=ActionStatus.PENDING):
    return ProtectedAction(
        action_id=action_id,
        tenant_id="tenant-1",
        actor_user_id=None,
        agent_id=agent_id,
        authority_grant_id=None,
        tool="tool",
        resource="res",
        action_type="read",
        status=status,
        decision_reason="",
        risk_score=0.0,
        created_at=datetime.now(UTC),
        evaluated_at=None,
        executed_at=None,
        parent_action_id=None,
        correlation_id=None,
        before_state_ref=None,
        after_state_ref=None,
    )


def make_service(agent=None, grants=None, tokens=None, actions=None):
    agent = agent or make_agent("agent-1")
    grants = grants or []
    tokens = tokens or []
    actions = actions or []
    agent_repo = StubAgentRepo([agent])
    grant_repo = StubGrantRepo(grants)
    containment_repo = StubContainmentRepo()
    token_repo = StubTokenRepo(tokens) if tokens is not None else None
    action_repo = StubActionRepo(actions) if actions is not None else None
    return AdvancedContainmentService(
        agent_repo, grant_repo, containment_repo,
        token_repository=token_repo,
        action_repository=action_repo,
    ), agent_repo, grant_repo, containment_repo, token_repo, action_repo


# ================================================================== #
# Feature 51 - Staged containment                                    #
# ================================================================== #

@pytest.mark.asyncio
async def test_staged_containment_full_escalation():
    agent = make_agent("agent-1")
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(agent=agent)

    result = await service.staged_containment(
        "tenant-1", "agent-1", "system", "admin",
    )
    assert result["final_stage"] == ContainmentMode.QUARANTINE.value
    assert ContainmentMode.OBSERVE.value in result["applied_stages"]
    assert ContainmentMode.RESTRICT.value in result["applied_stages"]
    assert ContainmentMode.SUSPEND.value in result["applied_stages"]
    assert ContainmentMode.QUARANTINE.value in result["applied_stages"]
    assert len(containment_repo._saved) == 4


@pytest.mark.asyncio
async def test_staged_containment_dry_run_no_status_changes():
    agent = make_agent("agent-1", status=AgentStatus.ACTIVE)
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(agent=agent)

    result = await service.staged_containment(
        "tenant-1", "agent-1", "system", "admin", dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["final_stage"] == ContainmentMode.QUARANTINE.value
    assert agent.status == AgentStatus.ACTIVE
    assert len(agent_repo.status_updates) == 0


@pytest.mark.asyncio
async def test_staged_containment_partial_stages():
    agent = make_agent("agent-1")
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(agent=agent)

    result = await service.staged_containment(
        "tenant-1", "agent-1", "system", "admin",
        start_stage=ContainmentMode.SUSPEND,
        max_stage=ContainmentMode.QUARANTINE,
    )
    assert ContainmentMode.OBSERVE.value not in result["applied_stages"]
    assert ContainmentMode.RESTRICT.value not in result["applied_stages"]
    assert ContainmentMode.SUSPEND.value in result["applied_stages"]
    assert ContainmentMode.QUARANTINE.value in result["applied_stages"]
    assert len(result["applied_stages"]) == 2


@pytest.mark.asyncio
async def test_staged_containment_applies_status_changes():
    agent = make_agent("agent-1", status=AgentStatus.ACTIVE)
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(agent=agent)

    await service.staged_containment(
        "tenant-1", "agent-1", "system", "admin",
        start_stage=ContainmentMode.RESTRICT,
        max_stage=ContainmentMode.SUSPEND,
    )
    assert AgentStatus.SUSPENDED in [s for _, s in agent_repo.status_updates]


# ================================================================== #
# Feature 52 - Blast radius scoring                                  #
# ================================================================== #

@pytest.mark.asyncio
async def test_compute_blast_radius_score_no_risk():
    agent = make_agent("agent-1", risk=RiskClassification.LOW)
    service, _, _, _, _, _ = make_service(agent=agent)

    result = await service.compute_blast_radius_score("tenant-1", "agent-1")
    assert result["agent_id"] == "agent-1"
    assert result["risk_level"] == "low"
    assert "score" in result
    assert "breakdown" in result
    assert 0.0 <= result["score"] <= 1.0


@pytest.mark.asyncio
async def test_compute_blast_radius_score_high_risk():
    agent = make_agent("agent-1", risk=RiskClassification.HIGH)
    child = make_agent("child-1", parent_agent_id="agent-1", risk=RiskClassification.CRITICAL)
    grant = make_grant("grant-1", "agent-1", scope=AuthorityScope.ADMIN, delegation_depth=4)
    service, agent_repo, grant_repo, _, _, _ = make_service(
        agent=agent, grants=[grant],
    )
    # Inject child into agent repo
    agent_repo._agents[child.agent_id] = child

    result = await service.compute_blast_radius_score("tenant-1", "agent-1")
    assert result["risk_level"] in ("high", "critical")
    assert result["score"] > 0.4
    assert result["child_agents_count"] == 1


@pytest.mark.asyncio
async def test_compute_blast_radius_score_missing_agent():
    service, _, _, _, _, _ = make_service()

    with pytest.raises(ValueError, match="Agent not found"):
        await service.compute_blast_radius_score("tenant-1", "missing")


# ================================================================== #
# Feature 53 - Containment verification                              #
# ================================================================== #

@pytest.mark.asyncio
async def test_verify_containment_all_checks_pass():
    agent = make_agent("agent-1", status=AgentStatus.QUARANTINED)
    token = make_token("tok-1", "agent-1", status=TokenStatus.REVOKED)
    action = make_action("act-1", "agent-1", status=ActionStatus.CONTAINED)
    service, agent_repo, grant_repo, containment_repo, token_repo, action_repo = make_service(
        agent=agent, tokens=[token], actions=[action],
    )

    # Pre-save a containment event
    event = ContainmentEvent(
        containment_id="cnt-existing",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.verify_containment("tenant-1", "cnt-existing", "agent-1")
    assert result["all_passed"] is True
    assert result["status"] == ContainmentStatus.COMPLETED.value
    check_names = [c["check"] for c in result["checks"]]
    assert "agent_quarantined" in check_names
    assert "all_grants_revoked" in check_names


@pytest.mark.asyncio
async def test_verify_containment_agent_not_found():
    service, _, _, _, _, _ = make_service()

    result = await service.verify_containment("tenant-1", "cnt-unknown", "missing")
    assert result["all_passed"] is False
    assert result["status"] == ContainmentStatus.FAILED.value


@pytest.mark.asyncio
async def test_verify_containment_fails_when_active_grants_exist():
    agent = make_agent("agent-1", status=AgentStatus.QUARANTINED)
    grant = make_grant("grant-1", "agent-1", status=AuthorityStatus.ACTIVE)
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(
        agent=agent, grants=[grant],
    )

    result = await service.verify_containment("tenant-1", "cnt-1", "agent-1")
    grants_check = [c for c in result["checks"] if c["check"] == "all_grants_revoked"][0]
    assert grants_check["passed"] is False


# ================================================================== #
# Feature 54 - Containment policies                                  #
# ================================================================== #

@pytest.mark.asyncio
async def test_apply_containment_policy_high_risk():
    agent = make_agent("agent-1")
    grant = make_grant("grant-1", "agent-1", scope=AuthorityScope.ADMIN)
    token = make_token("tok-1", "agent-1")
    service, agent_repo, grant_repo, containment_repo, token_repo, _ = make_service(
        agent=agent, grants=[grant], tokens=[token],
    )

    result = await service.apply_containment_policy(
        "tenant-1", "agent-1", "high_risk", "system", "admin",
    )
    assert result["success"] is True
    assert result["policy_name"] == "high_risk"
    assert result["mode"] == ContainmentMode.QUARANTINE.value
    assert "agent_quarantined" in result["actions_taken"]
    assert "grant_revoked:grant-1" in result["actions_taken"]
    assert "token_revoked:tok-1" in result["actions_taken"]


@pytest.mark.asyncio
async def test_apply_containment_policy_low_risk_no_token_revoke():
    agent = make_agent("agent-1")
    token = make_token("tok-1", "agent-1")
    service, agent_repo, grant_repo, containment_repo, token_repo, _ = make_service(
        agent=agent, tokens=[token],
    )

    result = await service.apply_containment_policy(
        "tenant-1", "agent-1", "low_risk", "system", "admin",
    )
    assert result["success"] is True
    assert result["mode"] == ContainmentMode.OBSERVE.value
    assert "agent_quarantined" not in result["actions_taken"]
    assert len(token_repo.revoked) == 0


@pytest.mark.asyncio
async def test_apply_containment_policy_unknown_raises():
    service, _, _, _, _, _ = make_service()

    with pytest.raises(ValueError, match="Unknown containment policy"):
        await service.apply_containment_policy(
            "tenant-1", "agent-1", "nonexistent", "system", "admin",
        )


@pytest.mark.asyncio
async def test_apply_containment_policy_dry_run():
    agent = make_agent("agent-1", status=AgentStatus.ACTIVE)
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(agent=agent)

    result = await service.apply_containment_policy(
        "tenant-1", "agent-1", "high_risk", "system", "admin", dry_run=True,
    )
    assert result["dry_run"] is True
    assert agent.status == AgentStatus.ACTIVE
    assert len(agent_repo.status_updates) == 0


@pytest.mark.asyncio
async def test_apply_containment_policy_missing_agent():
    service, _, _, _, _, _ = make_service()

    with pytest.raises(ValueError, match="Agent not found"):
        await service.apply_containment_policy(
            "tenant-1", "missing", "high_risk", "system", "admin",
        )


# ================================================================== #
# Feature 55 - Containment exception handling                        #
# ================================================================== #

@pytest.mark.asyncio
async def test_handle_containment_exception_success():
    agent = make_agent("agent-1")
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-failed",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.SUSPEND,
        status=ContainmentStatus.FAILED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.handle_containment_exception(
        "tenant-1", "cnt-failed", "agent-1",
        "Network timeout during token revocation",
    )
    assert result["handled"] is True
    assert result["fallback_triggered"] is True
    assert result["fallback_containment_id"] is not None
    assert AgentStatus.QUARANTINED in [s for _, s in agent_repo.status_updates]


@pytest.mark.asyncio
async def test_handle_containment_exception_no_retry():
    agent = make_agent("agent-1")
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-failed",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.SUSPEND,
        status=ContainmentStatus.FAILED,
        dry_run=True,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.handle_containment_exception(
        "tenant-1", "cnt-failed", "agent-1",
        "some error",
        retry=False,
    )
    assert result["handled"] is True
    assert result["fallback_triggered"] is False
    assert result["fallback_containment_id"] is None


@pytest.mark.asyncio
async def test_handle_containment_exception_marks_event_failed():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-failed-2",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.SUSPEND,
        status=ContainmentStatus.IN_PROGRESS,
        result_details={},
        created_at=datetime.now(UTC),
    )
    saved = await containment_repo.save(event)

    result = await service.handle_containment_exception(
        "tenant-1", "cnt-failed-2", "agent-1",
        "DB connection lost",
    )
    assert result["exception_id"] is not None
    updated = await containment_repo.get_by_containment_id("tenant-1", "cnt-failed-2")
    assert updated.result_details.get("exception_message") == "DB connection lost"


# ================================================================== #
# Feature 56 - Containment audit trail                               #
# ================================================================== #

@pytest.mark.asyncio
async def test_record_containment_audit_appends_entry():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-audit",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.record_containment_audit(
        "tenant-1", "cnt-audit", "manual_override", "admin_user",
        details={"reason": "manual review"},
    )
    assert result["recorded"] is True
    assert result["audit_id"] is not None
    assert result["action"] == "manual_override"

    updated = await containment_repo.get_by_containment_id("tenant-1", "cnt-audit")
    audit_trail = json.loads(updated.result_details.get("audit_trail", "[]"))
    assert len(audit_trail) == 1
    assert audit_trail[0]["action"] == "manual_override"
    assert audit_trail[0]["actor"] == "admin_user"


@pytest.mark.asyncio
async def test_record_containment_audit_multiple_entries():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-audit-multi",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    await service.record_containment_audit("tenant-1", "cnt-audit-multi", "action_1", "alice")
    await service.record_containment_audit("tenant-1", "cnt-audit-multi", "action_2", "bob")

    updated = await containment_repo.get_by_containment_id("tenant-1", "cnt-audit-multi")
    audit_trail = json.loads(updated.result_details.get("audit_trail", "[]"))
    assert len(audit_trail) == 2


@pytest.mark.asyncio
async def test_record_containment_audit_unknown_event():
    service, _, _, _, _, _ = make_service()

    result = await service.record_containment_audit(
        "tenant-1", "cnt-nonexistent", "some_action", "admin",
    )
    assert result["recorded"] is False
    assert result["audit_id"] is not None


# ================================================================== #
# Feature 57 - Notify affected parties                               #
# ================================================================== #

@pytest.mark.asyncio
async def test_notify_affected_parties_with_recipients():
    agent = make_agent("agent-1")
    child = make_agent("child-1", parent_agent_id="agent-1")
    service, agent_repo, grant_repo, containment_repo, _, _ = make_service(
        agent=agent,
    )
    agent_repo._agents[child.agent_id] = child

    event = ContainmentEvent(
        containment_id="cnt-notif",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        affected_agent_ids=["agent-1", "child-1"],
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.notify_affected_parties(
        "tenant-1", "cnt-notif", "agent-1",
    )
    assert result["success"] is True
    assert "child-1" in result["recipients_notified"]
    assert result["message"] == "Agent has been contained."


@pytest.mark.asyncio
async def test_notify_affected_parties_explicit_recipients():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-notif-2",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.notify_affected_parties(
        "tenant-1", "cnt-notif-2", "agent-1",
        recipients=["ops-team", "security-team"],
        message="Priority containment alert",
    )
    assert "ops-team" in result["recipients_notified"]
    assert "security-team" in result["recipients_notified"]
    assert result["message"] == "Priority containment alert"


@pytest.mark.asyncio
async def test_notify_affected_parties_updates_event():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-notif-3",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    await service.notify_affected_parties(
        "tenant-1", "cnt-notif-3", "agent-1",
        recipients=["team-a"],
    )
    updated = await containment_repo.get_by_containment_id("tenant-1", "cnt-notif-3")
    assert updated.result_details.get("notification_sent") == "true"
    assert updated.result_details.get("notification_id") is not None


# ================================================================== #
# Feature 58 - Recovery coordination                                  #
# ================================================================== #

@pytest.mark.asyncio
async def test_coordinate_recovery_after_completed_containment():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-rec",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.coordinate_recovery(
        "tenant-1", "cnt-rec", "agent-1",
        recovery_plan_id="plan-1",
    )
    assert result["status"] == "initiated"
    assert result["recovery_id"] is not None
    assert result["recovery_plan_id"] == "plan-1"
    assert len(result["next_steps"]) > 0


@pytest.mark.asyncio
async def test_coordinate_recovery_skips_incomplete_containment():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-rec-pending",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.IN_PROGRESS,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.coordinate_recovery(
        "tenant-1", "cnt-rec-pending", "agent-1",
    )
    assert result["status"] == "skipped"
    assert result["reason"] == "Containment not yet completed"


@pytest.mark.asyncio
async def test_coordinate_recovery_dry_run():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-rec-dr",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    result = await service.coordinate_recovery(
        "tenant-1", "cnt-rec-dr", "agent-1",
        dry_run=True,
    )
    assert result["status"] == "planned"
    assert result["dry_run"] is True
    assert result["recovery_plan_id"] is None


@pytest.mark.asyncio
async def test_coordinate_recovery_updates_event_details():
    agent = make_agent("agent-1")
    service, _, _, containment_repo, _, _ = make_service(agent=agent)

    event = ContainmentEvent(
        containment_id="cnt-rec-upd",
        tenant_id="tenant-1",
        target_agent_id="agent-1",
        target_authority_id=None,
        mode=ContainmentMode.QUARANTINE,
        status=ContainmentStatus.COMPLETED,
        result_details={},
        created_at=datetime.now(UTC),
    )
    await containment_repo.save(event)

    await service.coordinate_recovery(
        "tenant-1", "cnt-rec-upd", "agent-1",
        recovery_plan_id="plan-abc",
    )
    updated = await containment_repo.get_by_containment_id("tenant-1", "cnt-rec-upd")
    assert updated.result_details.get("recovery_coordinated") == "true"
    assert updated.result_details.get("recovery_plan_id") == "plan-abc"
