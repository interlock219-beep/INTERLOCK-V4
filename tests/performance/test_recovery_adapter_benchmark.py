"""Interlock V5 — recovery adapter performance benchmarks.

Thresholds are calibrated from measured baselines on the development
machine (2026-10-14) with ~5x head-room over the measured p95 (sub-millisecond
scenarios use a 1 ms noise floor).  Measured p95 values are documented next to
each threshold so future regressions are visible against real numbers rather
than guessed budgets.

Measured baselines (p95): env_capture 0.124ms, env_compensate 0.020ms,
env_drift 0.010ms, registry_validate 0.032ms, hosts_capture 0.80ms,
hosts_compensate 9.0ms, config_capture 2.37ms, filesystem_capture 63.9ms,
filesystem_compensate 4.5ms, archive_capture 37.6ms, archive_compensate
22.1ms, certification_lab_full_run 654ms, orchestrator_10_steps 1.04ms.
"""

from __future__ import annotations

import hashlib
import statistics
import time
from pathlib import Path

from app.domain.entities.protected_action import ProtectedAction
from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    RecoveryAdapterType,
    RecoveryEvidence,
    Reversibility,
)
from app.domain.repositories.causal_state_repositories import enforce_write_fence
from app.domain.services.distributed_recovery_orchestrator import (
    DistributedRecoveryOrchestrator,
)
from app.domain.services.recovery_adapter_registry import RecoveryAdapterRegistry
from app.domain.services.recovery_certification_lab import RecoveryCertificationLab
from app.infrastructure.recovery.archive_recovery_adapter import ArchiveRecoveryAdapter
from app.infrastructure.recovery.certification_probes import standard_behavioral_probes
from app.infrastructure.recovery.config_recovery_adapter import ConfigRecoveryAdapter
from app.infrastructure.recovery.environment_recovery_adapter import (
    EnvironmentRecoveryAdapter,
)
from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)
from app.infrastructure.recovery.hosts_recovery_adapter import HostsRecoveryAdapter
from app.infrastructure.recovery.mock_adapter import MockRecoveryAdapter

_original = "Original certified content"
_mutated = "Modified by incident"


def _action(
    action_id: str, tool: str, resource: str, action_type: str
) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="bench-tenant",
        actor_user_id=None,
        agent_id="bench-agent",
        authority_grant_id=None,
        tool=tool,
        resource=resource,
        action_type=action_type,
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref="state:before:bench",
    )


async def _measure(fn, iterations: int) -> dict[str, float]:
    """Return mean/p95/max latency in milliseconds for *fn*."""
    for _ in range(3):  # warm-up
        await fn()
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        await fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {
        "mean_ms": statistics.fmean(samples),
        "p95_ms": samples[max(0, int(len(samples) * 0.95) - 1)],
        "max_ms": samples[-1],
    }


def _assert_budget(stats: dict[str, float], budget_ms: float, label: str) -> None:
    assert stats["p95_ms"] <= budget_ms, (
        f"{label}: p95 {stats['p95_ms']:.3f}ms exceeds budget {budget_ms}ms "
        f"(mean {stats['mean_ms']:.3f}ms, max {stats['max_ms']:.3f}ms)"
    )


async def test_environment_adapter_latency_budget():
    """env capture/compensate/drift budgets (measured p95: 0.124/0.020/0.010ms)."""
    environ: dict[str, str] = {}
    adapter = EnvironmentRecoveryAdapter(environ=environ)
    action = _action("b-env", "environment", "env:BENCH_VAR", "set_env")

    async def capture():
        await adapter.capture_recovery_evidence(
            action, execution_context={"before_value": "v"}
        )

    stats = await _measure(capture, 100)
    _assert_budget(stats, 1.0, "env_capture")

    evidence = await adapter.capture_recovery_evidence(
        action, execution_context={"before_value": "v"}
    )
    comp = await adapter.generate_compensation(action, evidence)

    async def compensate():
        environ["BENCH_VAR"] = "mutated"
        await adapter.execute_compensation(comp, evidence.idempotency_key)

    stats = await _measure(compensate, 100)
    _assert_budget(stats, 1.0, "env_compensate")

    async def drift():
        await adapter.detect_drift(action, evidence)

    stats = await _measure(drift, 100)
    _assert_budget(stats, 1.0, "env_drift")


async def test_registry_contract_validation_latency_budget():
    """validate_contract budget (measured p95: 0.032ms)."""
    adapter = EnvironmentRecoveryAdapter(environ={})

    def check():
        result = RecoveryAdapterRegistry.validate_contract(adapter)
        assert result.ok

    for _ in range(3):
        check()
    samples = []
    for _ in range(200):
        start = time.perf_counter()
        check()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    _assert_budget(
        {
            "p95_ms": samples[int(len(samples) * 0.95) - 1],
            "mean_ms": statistics.fmean(samples),
            "max_ms": samples[-1],
        },
        1.0,
        "registry_validate_contract",
    )


async def test_hosts_adapter_latency_budget(tmp_path: Path):
    """hosts capture/compensate budgets (measured p95: 0.80/9.0ms)."""
    hosts = tmp_path / "hosts"
    hosts_bytes = b"".join(
        f"10.0.0.{i} host{i}.bench.example.com\r\n".encode() for i in range(50)
    )
    hosts.write_bytes(hosts_bytes)
    adapter = HostsRecoveryAdapter(hosts_path=hosts)
    action = _action("b-dns", "dns", "dns:host1.bench.example.com", "dns_update")

    async def capture():
        await adapter.capture_recovery_evidence(action)

    stats = await _measure(capture, 60)
    _assert_budget(stats, 4.0, "hosts_capture")

    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)

    async def compensate():
        hosts.write_bytes(hosts_bytes.replace(b"10.0.0.1", b"10.9.9.9"))
        await adapter.execute_compensation(comp, evidence.idempotency_key)

    stats = await _measure(compensate, 40)
    _assert_budget(stats, 45.0, "hosts_compensate")


async def test_config_adapter_latency_budget(tmp_path: Path):
    """config capture budget (measured p95: 2.37ms)."""
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "settings.json").write_text('{"bench": true}', encoding="utf-8")
    adapter = ConfigRecoveryAdapter(config_dir=cfg_dir)
    action = _action("b-cfg", "config", "config:settings.json", "modify")

    async def capture():
        await adapter.capture_recovery_evidence(action)

    stats = await _measure(capture, 60)
    _assert_budget(stats, 12.0, "config_capture")


async def test_filesystem_adapter_latency_budget(tmp_path: Path):
    """filesystem capture/compensate budgets (measured p95: 63.9/4.5ms).

    The capture budget is intentionally generous: default capture preserves
    metadata, ownership, ACLs and xattrs, which dominates the cost — see
    INTERLOCK_V5_BENCHMARK_REPORT.md.
    """
    base = tmp_path / "fs"
    base.mkdir()
    fs_file = base / "data.txt"
    fs_file.write_text(_original, encoding="utf-8")
    adapter = FilesystemRecoveryAdapter(base_path=base)
    action = _action("b-fs", "filesystem", "file:data.txt", "modify")

    async def capture():
        await adapter.capture_recovery_evidence(action)

    stats = await _measure(capture, 30)
    _assert_budget(stats, 320.0, "filesystem_capture")

    fs_file.write_text(_mutated, encoding="utf-8")
    evidence = await adapter.capture_recovery_evidence(
        action,
        before_snapshot={
            "exists": True,
            "content": _original,
            "hash": hashlib.sha256(_original.encode("utf-8")).hexdigest(),
            "size": len(_original.encode("utf-8")),
            "metadata": None,
        },
    )
    comp = await adapter.generate_compensation(action, evidence)

    async def compensate():
        fs_file.write_text(_mutated, encoding="utf-8")
        await adapter.execute_compensation(comp, evidence.idempotency_key)

    stats = await _measure(compensate, 40)
    _assert_budget(stats, 25.0, "filesystem_compensate")


async def test_archive_adapter_latency_budget(tmp_path: Path):
    """archive capture/compensate budgets (measured p95: 37.6/22.1ms)."""
    target = tmp_path / "artifact.txt"
    target.write_text("bench-content " * 100, encoding="utf-8")
    adapter = ArchiveRecoveryAdapter(state_dir=tmp_path / "arc-state")
    action = _action("b-arc", "archive", f"archive:{target}", "backup")

    async def capture():
        await adapter.capture_recovery_evidence(action)

    stats = await _measure(capture, 30)
    _assert_budget(stats, 200.0, "archive_capture")

    evidence = await adapter.capture_recovery_evidence(action)
    comp = await adapter.generate_compensation(action, evidence)

    async def compensate():
        target.write_text("mutated " * 100, encoding="utf-8")
        await adapter.execute_compensation(comp, evidence.idempotency_key)

    stats = await _measure(compensate, 40)
    _assert_budget(stats, 120.0, "archive_compensate")


async def test_certification_lab_run_latency_budget(tmp_path: Path):
    """Full certification run (5 adapters + probes), measured p95: 654ms."""
    (tmp_path / "cfg").mkdir()
    (tmp_path / "fs").mkdir()
    lab = RecoveryCertificationLab(
        [
            EnvironmentRecoveryAdapter(environ={}),
            ArchiveRecoveryAdapter(state_dir=tmp_path / "arc"),
            HostsRecoveryAdapter(hosts_path=tmp_path / "hosts"),
            ConfigRecoveryAdapter(config_dir=tmp_path / "cfg"),
            FilesystemRecoveryAdapter(base_path=tmp_path / "fs"),
        ],
        behavioral_probes=standard_behavioral_probes(),
    )

    async def run():
        report = await lab.certify_all()
        assert report.all_certified

    stats = await _measure(run, 3)
    _assert_budget(stats, 3500.0, "certification_lab_full_run")


class _EvidenceRepo:
    def __init__(self, evidence: list[RecoveryEvidence]) -> None:
        self._by_action = {e.action_id: e for e in evidence}

    async def get_by_action_id(self, tenant_id: str, action_id: str):
        ev = self._by_action.get(action_id)
        return ev if ev and ev.tenant_id == tenant_id else None


class _ExecutionRepo:
    def __init__(self) -> None:
        self._steps = {}

    async def save(self, step, expected_fencing_token=None):
        # V6 fencing contract: reject writes older than the stored fence.
        fences = getattr(self, "_fences", {})
        self._fences = fences
        enforce_write_fence(
            fences.get(step.step_id, 0), expected_fencing_token, step.step_id
        )
        if expected_fencing_token is not None:
            fences[step.step_id] = expected_fencing_token
        self._steps[step.step_id] = step
        return step

    async def list_by_plan(self, tenant_id, plan_id, limit=500, offset=0):
        items = sorted(
            [s for s in self._steps.values() if s.plan_id == plan_id],
            key=lambda s: s.execution_order,
        )
        return items[offset : offset + limit], len(items)


def _bench_evidence(action_id: str) -> RecoveryEvidence:
    return RecoveryEvidence(
        evidence_id=f"ev-{action_id}",
        action_id=action_id,
        tenant_id="bench-tenant",
        agent_id="bench",
        authority_grant_id=None,
        parent_action_id=None,
        root_action_id=action_id,
        correlation_id="c",
        incident_id="i",
        target_system="mock",
        target_resource="record:1",
        action_type="insert",
        before_state_reference="state:before:bench",
        after_state_reference=None,
        compensation_payload={"op": "restore"},
        compensation_type=CompensationType.REVERSE_OPERATION,
        recovery_adapter_type=RecoveryAdapterType.MOCK,
        idempotency_key=f"idem-{action_id}",
        dependency_edges=[],
        reversibility_classification=Reversibility.AUTOMATICALLY_REVERSIBLE,
        evidence_hash="h",
        adapter_capability=AdapterCapability.MOCK,
    )


async def test_orchestrator_plan_execution_latency_budget():
    """10-step durable plan create+execute, measured p95: 1.04ms."""
    actions = [_action(f"a{i}", "database", "record:1", "insert") for i in range(10)]
    evidence = [_bench_evidence(f"a{i}") for i in range(10)]

    async def plan_cycle():
        orch = DistributedRecoveryOrchestrator(
            _EvidenceRepo(evidence),
            _ExecutionRepo(),
            [MockRecoveryAdapter(scenario="success")],
        )
        await orch.create_durable_plan(
            "bench-tenant", "bench-plan", actions, [a.action_id for a in actions]
        )
        result = await orch.execute_durable_plan("bench-tenant", "bench-plan")
        assert result["status"] == "completed"

    stats = await _measure(plan_cycle, 20)
    _assert_budget(stats, 10.0, "orchestrator_plan_10_steps")
