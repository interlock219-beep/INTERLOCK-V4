"""Tests for production-grade configuration recovery adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.domain.entities.protected_action import ActionStatus, ProtectedAction, Reversibility
from app.domain.entities.surgical_recovery_types import ExecutionState
from app.infrastructure.recovery.config_recovery_adapter import ConfigRecoveryAdapter


def _make_config_action(
    action_id: str = "act-cfg-1",
    action_type: str = "modify",
    resource: str = "config:settings.json",
    reversibility: Reversibility = Reversibility.AUTOMATICALLY_REVERSIBLE,
    before_state_ref: str | None = "state:before:123",
    tool: str = "config",
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="test-tenant",
        agent_id="agent-test",
        actor_user_id=None,
        authority_grant_id=None,
        tool=tool,
        resource=resource,
        action_type=action_type,
        risk_score=0.5,
        policy_version="v1",
        correlation_id="corr-1",
        parent_action_id=None,
        workflow_id=None,
        reversibility=reversibility,
        before_state_ref=before_state_ref,
        after_state_ref="state:after:456",
        tool_arguments={"file": "settings.json"},
        status=ActionStatus.EXECUTED,
        decision_reason="test",
        evaluated_at=None,
        executed_at=None,
        created_at=None,
    )


class TestConfigRecoveryAdapterDeclareCapabilities:
    """Test capability declaration."""

    @pytest.mark.asyncio
    async def test_declare_capabilities(self) -> None:
        adapter = ConfigRecoveryAdapter()
        caps = await adapter.declare_capabilities()
        assert caps.adapter_name == "config_recovery"
        assert caps.can_capture_before_state is True
        assert caps.can_compensate is True
        assert caps.can_verify is True
        assert "atomic_replacement" in caps.declared_capabilities


class TestConfigRecoveryAdapterCanRecover:
    """Test can_recover classification."""

    @pytest.mark.asyncio
    async def test_can_recover_modify(self) -> None:
        adapter = ConfigRecoveryAdapter()
        action = _make_config_action(action_type="modify", before_state_ref="state:abc")
        result = await adapter.can_recover(action)
        assert result == "automatically_reversible"

    @pytest.mark.asyncio
    async def test_can_recover_irreversible(self) -> None:
        adapter = ConfigRecoveryAdapter()
        action = _make_config_action(reversibility=Reversibility.IRREVERSIBLE)
        result = await adapter.can_recover(action)
        assert result == "irreversible"


class TestConfigRecoveryAdapterExecuteCompensation:
    """Test compensation execution."""

    @pytest.mark.asyncio
    async def test_restore_config(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        original_content = json.dumps({"app_name": "myapp", "debug": False, "port": 8080}, indent=2)
        config_file.write_text(original_content)

        adapter = ConfigRecoveryAdapter(config_dir=config_dir)

        modified_content = json.dumps({"app_name": "hacked", "debug": True, "port": 9999}, indent=2)
        config_file.write_text(modified_content)

        action = _make_config_action(action_type="modify", resource="config:settings.json")
        evidence = await adapter.capture_recovery_evidence(action)

        evidence.compensation_payload["before_snapshot"] = {
            "exists": True,
            "content": original_content,
            "hash": hashlib.sha256(original_content.encode()).hexdigest(),
            "size": len(original_content),
        }

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert result.execution_state == ExecutionState.SUCCEEDED
        assert config_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_delete_config(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "new_config.yaml"
        config_file.write_text("new: config")

        adapter = ConfigRecoveryAdapter(config_dir=config_dir)
        action = _make_config_action(action_type="create", resource="config:new_config.yaml")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert not config_file.exists()

    @pytest.mark.asyncio
    async def test_restore_deleted_config(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "deleted.yaml"
        original_content = "original: config"
        config_file.write_text(original_content)

        adapter = ConfigRecoveryAdapter(config_dir=config_dir)
        action = _make_config_action(action_type="delete", resource="config:deleted.yaml")
        evidence = await adapter.capture_recovery_evidence(action)

        config_file.unlink()
        assert not config_file.exists()

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is True
        assert config_file.exists()
        assert config_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_conflict_blocks_recovery(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        original_content = json.dumps({"key": "original"}, indent=2)
        config_file.write_text(original_content)

        adapter = ConfigRecoveryAdapter(config_dir=config_dir)
        action = _make_config_action(action_type="modify", resource="config:settings.json")
        evidence = await adapter.capture_recovery_evidence(action)

        config_file.write_text(json.dumps({"key": "agent_value"}, indent=2))
        config_file.write_text(json.dumps({"key": "human_value"}, indent=2))

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

        assert result.success is False
        assert result.execution_state == ExecutionState.BLOCKED_BY_CONFLICT
        assert config_file.read_text() == json.dumps({"key": "human_value"}, indent=2)


class TestConfigRecoveryAdapterVerify:
    """Test verification."""

    @pytest.mark.asyncio
    async def test_verify_restore_config(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        original_content = json.dumps({"app_name": "myapp", "debug": False}, indent=2)
        config_file.write_text(original_content)

        adapter = ConfigRecoveryAdapter(config_dir=config_dir)
        action = _make_config_action(action_type="modify", resource="config:settings.json")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        verification = await adapter.verify(compensation)

        assert verification.verified is True

    @pytest.mark.asyncio
    async def test_verify_delete_config(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        adapter = ConfigRecoveryAdapter(config_dir=config_dir)
        action = _make_config_action(action_type="create", resource="config:created.yaml")
        evidence = await adapter.capture_recovery_evidence(action)

        compensation = await adapter.generate_compensation(action, evidence)
        verification = await adapter.verify(compensation)

        assert verification.verified is True


class TestConfigRecoveryAdapterEndToEnd:
    """End-to-end config recovery scenarios."""

    @pytest.mark.asyncio
    async def test_full_config_recovery_workflow(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "app.yaml"
        original_content = "app:\n  name: myapp\n  debug: false\n  port: 8080\n"
        config_file.write_text(original_content)

        original_hash = hashlib.sha256(config_file.read_bytes()).hexdigest()

        adapter = ConfigRecoveryAdapter(config_dir=config_dir)

        config_file.write_text("app:\n  name: hacked\n  debug: true\n  port: 9999\n")

        action = _make_config_action(
            action_id="act-e2e-cfg",
            action_type="modify",
            resource="config:app.yaml",
        )

        evidence = await adapter.capture_recovery_evidence(action)

        evidence.compensation_payload["before_snapshot"] = {
            "exists": True,
            "content": original_content,
            "hash": original_hash,
            "size": len(original_content),
        }

        impact = await adapter.simulate(action, evidence)
        assert impact.would_succeed is True

        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
        assert result.success is True

        verification = await adapter.verify(compensation)
        assert verification.verified is True
        assert config_file.read_text() == original_content
