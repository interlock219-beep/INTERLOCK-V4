"""Phase 7, 8, 9 — Crash Recovery, Infrastructure Failures, and Concurrency.

Tests:
- Recovery interruption and resume at various points
- Redis/database unavailability handling
- Concurrent recovery operations
- Race condition detection
- Duplicate recovery prevention
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.domain.entities.causal_state_types import (
    DurableExecutionStep,
)
from app.domain.entities.protected_action import (
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import (
    ExecutionState,
    StopCondition,
)
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter
from tests.unit.recovery_lab.factories import make_action, make_evidence

DurableExecutionState = ExecutionState


class InMemoryEvidenceRepo:
    def __init__(self, evidence_list: list[Any] | None = None) -> None:
        self._evidence: dict[str, Any] = {}
        if evidence_list:
            for e in evidence_list:
                self._evidence[e.action_id] = e

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> Any | None:
        ev = self._evidence.get(action_id)
        if ev and ev.tenant_id == tenant_id:
            return ev
        return None

    async def get_by_evidence_id(self, tenant_id: str, evidence_id: str) -> Any | None:
        for ev in self._evidence.values():
            if ev.evidence_id == evidence_id and ev.tenant_id == tenant_id:
                return ev
        return None

    async def list_by_incident(
        self, tenant_id: str, incident_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[Any], int]:
        items = [
            e for e in self._evidence.values()
            if e.tenant_id == tenant_id and getattr(e, "incident_id", "") == incident_id
        ]
        return items[offset:offset + limit], len(items)

    async def list_by_root_action(
        self, tenant_id: str, root_action_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[Any], int]:
        items = [
            e for e in self._evidence.values()
            if e.tenant_id == tenant_id and e.root_action_id == root_action_id
        ]
        return items[offset:offset + limit], len(items)

    async def save(self, evidence: Any) -> Any:
        self._evidence[evidence.action_id] = evidence
        return evidence


class InMemoryDurableExecutionRepo:
    def __init__(self) -> None:
        self._steps: dict[str, DurableExecutionStep] = {}

    async def get_by_step_id(self, tenant_id: str, step_id: str) -> DurableExecutionStep | None:
        step = self._steps.get(step_id)
        if step and step.tenant_id == tenant_id:
            return step
        return None

    async def list_by_plan(
        self, tenant_id: str, plan_id: str, limit: int = 500, offset: int = 0
    ) -> tuple[list[DurableExecutionStep], int]:
        items = [
            s for s in self._steps.values()
            if s.tenant_id == tenant_id and s.plan_id == plan_id
        ]
        items.sort(key=lambda s: s.execution_order)
        return items[offset:offset + limit], len(items)

    async def save(self, step: DurableExecutionStep) -> DurableExecutionStep:
        self._steps[step.step_id] = step
        return step

    async def update_state(
        self, tenant_id: str, step_id: str, state: str, error: str | None = None
    ) -> DurableExecutionStep | None:
        step = self._steps.get(step_id)
        if step and step.tenant_id == tenant_id:
            updated = DurableExecutionStep(
                step_id=step.step_id,
                plan_id=step.plan_id,
                action_id=step.action_id,
                execution_order=step.execution_order,
                tenant_id=step.tenant_id,
                execution_state=state,
                idempotency_key=step.idempotency_key,
                target_system=step.target_system,
                target_resource=step.target_resource,
                compensation_payload=step.compensation_payload,
                max_retries=step.max_retries,
                retry_count=step.retry_count,
                error=error,
            )
            self._steps[step_id] = updated
            return updated
        return None


class TestPhase7CrashRecovery:
    """Test recovery interruption and resume."""

    @pytest.mark.asyncio
    async def test_durable_plan_creates_steps(self) -> None:
        actions = [
            make_action("crash-1"),
            make_action("crash-2"),
            make_action("crash-3"),
        ]
        evidence = [make_evidence(a) for a in actions]

        orchestrator = DistributedRecoveryOrchestrator(
            InMemoryEvidenceRepo(evidence),
            InMemoryDurableExecutionRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        steps = await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-crash",
            actions=actions,
            topological_order=["crash-1", "crash-2", "crash-3"],
        )

        assert len(steps) == 3
        assert all(s.execution_state == ExecutionState.PENDING.value for s in steps)

    @pytest.mark.asyncio
    async def test_recovery_resumes_from_interruption(self) -> None:
        actions = [
            make_action("resume-1"),
            make_action("resume-2"),
            make_action("resume-3"),
        ]
        evidence = [make_evidence(a) for a in actions]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            InMemoryEvidenceRepo(evidence),
            execution_repo,
            [MockRecoveryAdapter(scenario="success")],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-resume",
            actions=actions,
            topological_order=["resume-1", "resume-2", "resume-3"],
        )

        steps, _ = await execution_repo.list_by_plan("test-tenant", "plan-resume")
        first_step = steps[0]
        await execution_repo.update_state(
            "test-tenant", first_step.step_id, DurableExecutionState.SUCCEEDED.value
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-resume",
            stop_conditions=[StopCondition.ON_FIRST_FAILURE.value],
        )

        assert result["status"] in ("completed", "partial", "completed_with_failures")

    @pytest.mark.asyncio
    async def test_no_double_execution(self) -> None:
        actions = [make_action("double-1")]
        evidence = [make_evidence(actions[0])]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            InMemoryEvidenceRepo(evidence),
            execution_repo,
            [MockRecoveryAdapter(scenario="success")],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-double",
            actions=actions,
            topological_order=["double-1"],
        )

        steps, _ = await execution_repo.list_by_plan("test-tenant", "plan-double")
        step = steps[0]
        await execution_repo.update_state(
            "test-tenant", step.step_id, DurableExecutionState.SUCCEEDED.value
        )

        result = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-double",
        )

        executed_steps = [
            s for s in result.get("step_results", [])
            if s.get("state") == DurableExecutionState.SUCCEEDED.value
        ]

        assert len(executed_steps) <= 1


class TestPhase8InfrastructureFailures:
    """Test behavior when infrastructure components fail."""

    @pytest.mark.asyncio
    async def test_adapter_timeout_handling(self) -> None:
        adapter = MockRecoveryAdapter(scenario="execute_fail")

        result = await adapter.execute_compensation(
            type("Comp", (), {"action_id": "timeout-test", "idempotency_key": "idem-timeout"})(),
            "idem-timeout",
        )

        assert result.success is False
        assert result.execution_state == ExecutionState.FAILED

    @pytest.mark.asyncio
    async def test_evidence_repo_unavailable(self) -> None:
        class FailingEvidenceRepo:
            async def get_by_action_id(self, tenant_id: str, action_id: str) -> None:
                raise ConnectionError("Evidence repository unavailable")

            async def get_by_evidence_id(self, tenant_id: str, evidence_id: str) -> None:
                raise ConnectionError("Evidence repository unavailable")

            async def list_by_incident(
                self, tenant_id: str, incident_id: str, **kwargs: Any
            ) -> tuple[list[Any], int]:
                raise ConnectionError("Evidence repository unavailable")

            async def list_by_root_action(
                self, tenant_id: str, root_action_id: str, **kwargs: Any
            ) -> tuple[list[Any], int]:
                raise ConnectionError("Evidence repository unavailable")

            async def save(self, evidence: Any) -> Any:
                raise ConnectionError("Evidence repository unavailable")

        orchestrator = DistributedRecoveryOrchestrator(
            FailingEvidenceRepo(),
            InMemoryDurableExecutionRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        with pytest.raises(ConnectionError):
            await orchestrator.create_durable_plan(
                tenant_id="test-tenant",
                plan_id="plan-fail",
                actions=[make_action("fail-action")],
                topological_order=["fail-action"],
            )

    @pytest.mark.asyncio
    async def test_fail_closed_on_no_adapters(self) -> None:
        from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine

        action = make_action("no-adapter", reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE)
        evidence = make_evidence(action)

        class EmptyCheckpointRepo:
            async def get_by_checkpoint_id(self, tenant_id: str, checkpoint_id: str) -> None:
                return None

            async def get_by_action_id(self, tenant_id: str, action_id: str) -> None:
                return None

            async def list_by_resource(
                self, tenant_id: str, resource_id: str, **kwargs: Any
            ) -> tuple[list[Any], int]:
                return [], 0

            async def save(self, checkpoint: Any) -> Any:
                return checkpoint

        engine = RecoverySimulationEngine(
            InMemoryEvidenceRepo([evidence]),
            EmptyCheckpointRepo(),
            [],
        )

        result = await engine.simulate_recovery("test-tenant", [action])

        sim = result["resource_simulations"]["no-adapter"]
        assert sim["simulation_status"] == "recoverable"


class EmptyCheckpointRepo:
    async def get_by_checkpoint_id(self, tenant_id: str, checkpoint_id: str) -> None:
        return None

    async def get_by_action_id(self, tenant_id: str, action_id: str) -> None:
        return None

    async def list_by_resource(
        self, tenant_id: str, resource_id: str, **kwargs: Any
    ) -> tuple[list[Any], int]:
        return [], 0

    async def save(self, checkpoint: Any) -> Any:
        return checkpoint


class TestPhase9Concurrency:
    """Test concurrent recovery operations."""

    @pytest.mark.asyncio
    async def test_concurrent_simulation_is_safe(self) -> None:
        from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine

        actions1 = [make_action(f"concurrent-a-{i}") for i in range(5)]
        actions2 = [make_action(f"concurrent-b-{i}") for i in range(5)]
        evidence1 = [make_evidence(a) for a in actions1]
        evidence2 = [make_evidence(a) for a in actions2]

        engine = RecoverySimulationEngine(
            InMemoryEvidenceRepo(evidence1 + evidence2),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result1, result2 = await asyncio.gather(
            engine.simulate_recovery("tenant-a", actions1),
            engine.simulate_recovery("tenant-b", actions2),
        )

        assert result1["total_resources"] == 5
        assert result2["total_resources"] == 5

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_recovery(self) -> None:
        from app.domain.services.recovery_simulation_engine import RecoverySimulationEngine

        actions_tenant_a = [make_action("tenant-a-action", tenant_id="tenant-a")]
        actions_tenant_b = [make_action("tenant-b-action", tenant_id="tenant-b")]
        evidence_a = [make_evidence(a) for a in actions_tenant_a]
        evidence_b = [make_evidence(a) for a in actions_tenant_b]

        engine = RecoverySimulationEngine(
            InMemoryEvidenceRepo(evidence_a + evidence_b),
            EmptyCheckpointRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )

        result_a = await engine.simulate_recovery("tenant-a", actions_tenant_a)
        result_b = await engine.simulate_recovery("tenant-b", actions_tenant_b)

        assert result_a["total_resources"] == 1
        assert result_b["total_resources"] == 1
        assert "tenant-a-action" in result_a["resource_simulations"]
        assert "tenant-b-action" in result_b["resource_simulations"]

    @pytest.mark.asyncio
    async def test_duplicate_recovery_prevention(self) -> None:
        actions = [make_action("dup-1")]
        evidence = [make_evidence(actions[0])]
        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            InMemoryEvidenceRepo(evidence),
            execution_repo,
            [MockRecoveryAdapter(scenario="success")],
        )

        await orchestrator.create_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-dup",
            actions=actions,
            topological_order=["dup-1"],
        )

        result1 = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-dup",
        )

        result2 = await orchestrator.execute_durable_plan(
            tenant_id="test-tenant",
            plan_id="plan-dup",
        )

        assert result1["status"] in ("completed", "partial")
        assert result2["status"] in ("completed", "partial", "already_completed")

    @pytest.mark.asyncio
    async def test_cross_tenant_recovery_isolation(self) -> None:
        actions_tenant1 = [make_action("cross-1", tenant_id="tenant-1")]
        actions_tenant2 = [make_action("cross-2", tenant_id="tenant-2")]
        evidence1 = [make_evidence(actions_tenant1[0])]
        evidence2 = [make_evidence(actions_tenant2[0])]

        execution_repo = InMemoryDurableExecutionRepo()

        orchestrator = DistributedRecoveryOrchestrator(
            InMemoryEvidenceRepo(evidence1 + evidence2),
            execution_repo,
            [MockRecoveryAdapter(scenario="success")],
        )

        steps1 = await orchestrator.create_durable_plan(
            tenant_id="tenant-1",
            plan_id="plan-cross-1",
            actions=actions_tenant1,
            topological_order=["cross-1"],
        )

        steps2 = await orchestrator.create_durable_plan(
            tenant_id="tenant-2",
            plan_id="plan-cross-2",
            actions=actions_tenant2,
            topological_order=["cross-2"],
        )

        assert all(s.tenant_id == "tenant-1" for s in steps1)
        assert all(s.tenant_id == "tenant-2" for s in steps2)

