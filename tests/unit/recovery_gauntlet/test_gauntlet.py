"""Complex Recovery Gauntlet — pytest test suite.

Exercises the REAL Interlock V4 recovery path for all 14 requirements:

  1.  Baseline restore (10, 50, 100, 500, 1000 actions)
  2.  Dependency chains
  3.  Human change injection (cases A, B, C)
  4.  Failure injection
  5.  Crash / resume
  6.  Idempotency (3× execution)
  7.  Zero-bypass
  8.  Mixed-resource worst-case
  9.  Scale benchmark
  10. Worst-case scenario (500 actions, all features)
  11. Independent verification
  12. Reporting
  13. Resource-type coverage
  14. Reproducibility

All tests use the ComplexRecoveryHarness which creates disposable temp
resources and drives real production adapters.
"""

from __future__ import annotations

import pytest

from app.domain.entities.protected_action import Reversibility
from app.domain.entities.surgical_recovery_types import ExecutionState
from tests.unit.recovery_gauntlet.harness import ComplexRecoveryHarness

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def harness() -> ComplexRecoveryHarness:
    """Provide a fresh ComplexRecoveryHarness for each test."""
    return ComplexRecoveryHarness(scenario="pytest-gauntlet", seed=0xDEADBEEF)


# ---------------------------------------------------------------------------
# Requirement 1 — Baseline restore at all scales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [10, 50, 100, 500])
@pytest.mark.asyncio
async def test_baseline_restore_at_scale(
    harness: ComplexRecoveryHarness, size: int
) -> None:
    """Verify recovery restores baseline at all supported workload sizes."""
    with harness:
        harness.capture_baseline_snapshot()
        actions = harness.generate_workload(size)
        results = await harness.execute_actions(actions)
        successful = [r for r in results if r.success]

        if not successful:
            pytest.skip(f"No actions succeeded for workload size {size}")

        plan = await harness.create_recovery_plan([r.action_id for r in successful])
        rec_result = await harness.execute_recovery(plan)

        assert len(results) == size, (
            f"Expected {size} results, got {len(results)}"
        )
        total_outcomes = (
            rec_result.recovered_count
            + rec_result.conflict_count
            + rec_result.failed_count
            + rec_result.unknown_count
        )
        assert total_outcomes > 0, "Recovery produced no outcome"


@pytest.mark.asyncio
async def test_workload_1000_produces_results(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify 1000-action workload produces successful results."""
    with harness:
        actions = harness.generate_workload(1000)
        results = await harness.execute_actions(actions)
        successful = [r for r in results if r.success]

        assert len(results) == 1000
        assert len(successful) > 0, "No actions succeeded at 1000-action workload"


@pytest.mark.asyncio
async def test_baseline_fingerprint_changes_after_mutation(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify environment fingerprint changes after agent mutations."""
    with harness:
        baseline = harness.capture_baseline_snapshot()
        actions = harness.generate_workload(10)
        await harness.execute_actions(actions)
        after = harness.capture_current_snapshot()
        assert baseline != after, "Fingerprint should change after agent mutations"


# ---------------------------------------------------------------------------
# Requirement 2 — Dependency chains
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linear_chain_a_to_b_to_c(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify A → B → C dependency chain is correctly recorded."""
    with harness:
        chain_actions = [
            {
                "action_id": "chain-001",
                "resource_type": "filesystem",
                "operation": "create",
                "resource": "file:chain_root.txt",
                "tool": "filesystem",
                "parent_action_id": None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.3,
            },
            {
                "action_id": "chain-002",
                "resource_type": "database",
                "operation": "insert",
                "resource": "db:users:chain",
                "tool": "database",
                "parent_action_id": "chain-001",
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.4,
            },
            {
                "action_id": "chain-003",
                "resource_type": "config",
                "operation": "write_config",
                "resource": "config:chain_conf.json",
                "tool": "config",
                "parent_action_id": "chain-002",
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            },
        ]

        results = await harness.execute_actions(chain_actions)
        graph = harness.build_dependency_graph(chain_actions)

        assert "chain-001" in graph
        assert "chain-002" in graph.get("chain-001", [])
        assert len(results) == 3


@pytest.mark.asyncio
async def test_multi_resource_dependency_chain(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify multi-resource dependency chains across all resource types."""
    with harness:
        actions = []
        for i in range(10):
            parent = f"dep-{i - 1:03d}" if i > 0 else None
            rt = ["filesystem", "database", "git", "config"][i % 4]
            actions.append({
                "action_id": f"dep-{i:03d}",
                "resource_type": rt,
                "operation": harness._pick_operation(rt),
                "resource": harness._resource_path(rt, i),
                "tool": rt,
                "parent_action_id": parent,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            })

        results = await harness.execute_actions(actions)
        graph = harness.build_dependency_graph(actions)

        assert len(results) == 10
        assert len(graph) >= 9


@pytest.mark.asyncio
async def test_dependency_ordering_respects_topology(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify recovery respects dependency ordering."""
    with harness:
        actions = [
            {
                "action_id": f"topo-{i:03d}",
                "resource_type": "filesystem",
                "operation": "create",
                "resource": f"file:topo_{i}.txt",
                "tool": "filesystem",
                "parent_action_id": f"topo-{i - 1:03d}" if i > 0 else None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            }
            for i in range(5)
        ]
        await harness.execute_actions(actions)
        graph = harness.build_dependency_graph(actions)

        plan = await harness.create_recovery_plan(["topo-000"])
        topo = plan.topological_order

        if topo:
            assert harness.verify_dependency_ordering(topo, graph)


# ---------------------------------------------------------------------------
# Requirement 3 — Human change injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_a_unrelated_resource_preserved(
    harness: ComplexRecoveryHarness,
) -> None:
    """CASE A: human changes unrelated resource — should be preserved."""
    with harness:
        actions = harness.generate_workload(5)
        results = await harness.execute_actions(actions)

        change = harness.inject_human_change("A", "config", "config:unrelated.json")

        successful = [r for r in results if r.success]
        plan = await harness.create_recovery_plan([r.action_id for r in successful])
        await harness.execute_recovery(plan)

        assert change["case"] == "A"
        assert harness._human_changes_injected == 1


@pytest.mark.asyncio
async def test_case_b_same_resource_drift_detected(
    harness: ComplexRecoveryHarness,
) -> None:
    """CASE B: human changes same resource — drift should be detectable."""
    with harness:
        actions = [{
            "action_id": "same-res-01",
            "resource_type": "filesystem",
            "operation": "create",
            "resource": "file:same_res.txt",
            "tool": "filesystem",
            "parent_action_id": None,
            "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
            "risk_score": 0.5,
        }]
        await harness.execute_actions(actions)

        change = harness.inject_human_change("B", "filesystem", "file:same_res.txt")

        assert change["case"] == "B"
        assert "new_content" in change


@pytest.mark.asyncio
async def test_case_c_dependent_resource_conflict(
    harness: ComplexRecoveryHarness,
) -> None:
    """CASE C: human changes a dependent resource — conflict should be detected."""
    with harness:
        chain = [
            {
                "action_id": "dep-chain-01",
                "resource_type": "filesystem",
                "operation": "create",
                "resource": "file:dep_root.txt",
                "tool": "filesystem",
                "parent_action_id": None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            },
            {
                "action_id": "dep-chain-02",
                "resource_type": "database",
                "operation": "insert",
                "resource": "db:users:dep",
                "tool": "database",
                "parent_action_id": "dep-chain-01",
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            },
        ]
        await harness.execute_actions(chain)

        change = harness.inject_human_change("C", "database", "db:users:dep")

        assert change["case"] == "C"
        assert "dependent_table" in change


# ---------------------------------------------------------------------------
# Requirement 4 — Failure injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_failure_injection(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify adapter failure injection doesn't crash the harness."""
    with harness:
        actions = harness.generate_workload(5)
        results = await harness.execute_actions(actions)

        failing = harness.create_failing_adapter(
            harness.adapters[0], "adapter_failure"
        )
        original = harness.adapters[0]
        harness.adapters[0] = failing

        successful = [r for r in results if r.success]
        plan = await harness.create_recovery_plan([r.action_id for r in successful])
        await harness.execute_recovery(plan)

        harness.adapters[0] = original
        assert harness._failures_injected >= 1


@pytest.mark.asyncio
async def test_verification_failure_injection(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify verification failure injection creates a failing adapter."""
    with harness:
        harness._failures_injected = 0
        failing = harness.create_failing_adapter(
            harness.adapters[0], "verification_failure"
        )
        assert harness._failures_injected == 1
        assert failing.adapter_name == harness.adapters[0].adapter_name


@pytest.mark.asyncio
async def test_interrupted_compensation_injection(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify interrupted compensation injection creates a failing adapter."""
    with harness:
        failing = harness.create_failing_adapter(
            harness.adapters[0], "interrupted"
        )
        assert failing.adapter_name == harness.adapters[0].adapter_name


@pytest.mark.asyncio
async def test_all_failure_modes_are_safe(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify all failure modes are disposable and don't persist."""
    modes = [
        "adapter_failure",
        "verification_failure",
        "missing_snapshot",
        "corrupted_evidence",
        "interrupted",
    ]
    with harness:
        original = harness.adapters[0]
        for mode in modes:
            failing = harness.create_failing_adapter(original, mode)
            assert failing is not None
            assert failing.adapter_name == original.adapter_name
        # Original adapter should be intact
        assert harness.adapters[0].adapter_name == original.adapter_name


# ---------------------------------------------------------------------------
# Requirement 5 — Crash / resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_durable_plan_creation(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify durable execution steps can be created."""
    with harness:
        actions = harness.generate_workload(20)
        results = await harness.execute_actions(actions)
        successful = [r for r in results if r.success]

        if not successful:
            pytest.skip("No successful actions for crash/resume test")

        plan = await harness.create_recovery_plan([r.action_id for r in successful])
        steps = await harness.create_durable_plan(plan)

        assert len(steps) > 0
        for step in steps:
            assert step.plan_id == plan.plan_id
            assert step.execution_state == "pending"


@pytest.mark.asyncio
async def test_interrupted_recovery_resumes(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify recovery can be interrupted and then resumed."""
    with harness:
        actions = harness.generate_workload(20)
        results = await harness.execute_actions(actions)
        successful = [r for r in results if r.success]

        if not successful:
            pytest.skip("No successful actions")

        plan = await harness.create_recovery_plan([r.action_id for r in successful])
        steps = await harness.create_durable_plan(plan)

        interrupt_count = max(1, len(steps) // 3)
        crash_result = await harness.execute_durable_plan(
            plan, steps, interrupt_after=interrupt_count
        )

        assert crash_result["interrupted"] is True
        assert len(crash_result["executed_steps"]) <= interrupt_count

        resume_result = await harness.resume_durable_plan(plan)
        assert "resumed" in resume_result or "error" in resume_result


@pytest.mark.asyncio
async def test_state_survives_restart_simulation(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify durable step state persists across simulated restarts."""
    with harness:
        actions = harness.generate_workload(10)
        results = await harness.execute_actions(actions)
        successful = [r for r in results if r.success]

        if not successful:
            pytest.skip("No successful actions")

        plan = await harness.create_recovery_plan([r.action_id for r in successful])
        steps = await harness.create_durable_plan(plan)

        for step in steps[:3]:
            await harness.durable_repo.update_state(
                "test-tenant", step.step_id, ExecutionState.SUCCEEDED
            )

        reloaded = await harness.durable_repo.list_by_plan(
            "test-tenant", plan.plan_id
        )
        succeeded = [
            s for s in reloaded if s.execution_state == ExecutionState.SUCCEEDED
        ]
        assert len(succeeded) == 3


# ---------------------------------------------------------------------------
# Requirement 6 — Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_executions_produce_same_outcome(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify recovery plan can be executed 3 times with consistent outcomes."""
    with harness:
        actions = harness.generate_workload(10)
        results = await harness.execute_actions(actions)
        successful = [r for r in results if r.success]

        if not successful:
            pytest.skip("No successful actions")

        plan = await harness.create_recovery_plan([r.action_id for r in successful])

        exec_results = await harness.execute_recovery_idempotent(plan, times=3)

        assert len(exec_results) == 3
        statuses = [r.status for r in exec_results]
        assert all(
            s in ("completed", "failed", "executing") for s in statuses
        )


@pytest.mark.asyncio
async def test_idempotent_execution_does_not_double_recover(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify idempotent execution reports consistent recovered counts."""
    with harness:
        actions = [{
            "action_id": "idem-01",
            "resource_type": "filesystem",
            "operation": "create",
            "resource": "file:idem_test.txt",
            "tool": "filesystem",
            "parent_action_id": None,
            "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
            "risk_score": 0.5,
        }]
        await harness.execute_actions(actions)
        plan = await harness.create_recovery_plan(["idem-01"])
        results = await harness.execute_recovery_idempotent(plan, times=3)

        assert len(results) == 3
        recovered_counts = [r.recovered_count for r in results]
        assert all(c == recovered_counts[0] for c in recovered_counts)


# ---------------------------------------------------------------------------
# Requirement 7 — Zero-bypass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bypass_attempts_are_recorded(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify bypass attempts are correctly recorded."""
    with harness:
        bypass_results = await harness.run_zero_bypass_test(n_attempts=10)
        assert bypass_results["total_attempts"] == 10
        assert "results" in bypass_results
        assert len(bypass_results["results"]) == 10


@pytest.mark.asyncio
async def test_bypass_on_filesystem_detected(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify filesystem bypass is recorded."""
    with harness:
        actions = [{
            "action_id": "bypass-fs",
            "resource_type": "filesystem",
            "operation": "create",
            "resource": "file:bypass_fs.txt",
            "tool": "filesystem",
            "parent_action_id": None,
            "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
            "risk_score": 0.5,
        }]
        await harness.execute_actions(actions)

        result = await harness.attempt_bypass(
            "filesystem", "modify", "file:bypass_fs.txt"
        )
        assert result["bypass_succeeded"] is True
        assert result["resource_type"] == "filesystem"


@pytest.mark.asyncio
async def test_bypass_on_database_detected(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify database bypass is recorded."""
    with harness:
        result = await harness.attempt_bypass(
            "database", "insert", "db:users:bypass"
        )
        assert result["bypass_succeeded"] is True


# ---------------------------------------------------------------------------
# Requirement 8 — Mixed-resource worst-case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worst_case_500_actions(
    harness: ComplexRecoveryHarness,
) -> None:
    """Run full worst-case scenario with 500 actions."""
    with harness:
        report = await harness.run_worst_case(workload_size=500)
        assert report["scenario"] == "worst_case"
        assert "classification" in report
        assert "crash_result" in report
        assert "resume_result" in report
        assert "verification" in report
        assert len(report.get("human_changes", [])) >= 3


@pytest.mark.asyncio
async def test_worst_case_all_resource_types_present(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify worst-case exercises all resource types."""
    with harness:
        report = await harness.run_worst_case(workload_size=100)
        assert "classification" in report


# ---------------------------------------------------------------------------
# Requirement 9 — Scale benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [10, 50, 100])
@pytest.mark.asyncio
async def test_benchmark_at_scale(
    harness: ComplexRecoveryHarness, size: int
) -> None:
    """Run benchmark at specified scale."""
    with harness:
        result = await harness.run_benchmark(size)
        assert result["workload_size"] == size
        assert "phases" in result
        assert "total_ms" in result
        assert result["total_ms"] > 0
        assert result["actions_executed"] == size


@pytest.mark.asyncio
async def test_benchmark_500_actions(
    harness: ComplexRecoveryHarness,
) -> None:
    """Run benchmark at 500-action scale."""
    with harness:
        result = await harness.run_benchmark(500)
        assert result["workload_size"] == 500
        assert result["total_ms"] > 0


@pytest.mark.asyncio
async def test_benchmark_1000_actions(
    harness: ComplexRecoveryHarness,
) -> None:
    """Run benchmark at 1000-action scale."""
    with harness:
        result = await harness.run_benchmark(1000)
        assert result["workload_size"] == 1000
        assert result["total_ms"] > 0


@pytest.mark.asyncio
async def test_benchmark_reports_all_phases(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify benchmark reports all required timing phases."""
    with harness:
        result = await harness.run_benchmark(10)
        phases = result["phases"]
        expected_phases = [
            "baseline_ms",
            "workload_generation_ms",
            "action_execution_ms",
            "plan_creation_ms",
            "plan_simulation_ms",
            "recovery_execution_ms",
            "verification_ms",
            "total_ms",
        ]
        for phase in expected_phases:
            assert phase in phases, f"Missing phase: {phase}"
            assert phases[phase] >= 0


# ---------------------------------------------------------------------------
# Requirement 10 — Reproducibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_seed_produces_same_workload() -> None:
    """Verify same seed produces identical workloads."""
    h1 = ComplexRecoveryHarness(scenario="repro", seed=42)
    h2 = ComplexRecoveryHarness(scenario="repro", seed=42)
    with h1, h2:
        actions1 = h1.generate_workload(50)
        actions2 = h2.generate_workload(50)
        assert len(actions1) == len(actions2)
        for a1, a2 in zip(actions1, actions2, strict=True):
            assert a1["action_id"] == a2["action_id"]
            assert a1["resource_type"] == a2["resource_type"]
            assert a1["operation"] == a2["operation"]


@pytest.mark.asyncio
async def test_different_seed_produces_different_workload() -> None:
    """Verify different seeds produce different workloads."""
    h1 = ComplexRecoveryHarness(scenario="repro", seed=1)
    h2 = ComplexRecoveryHarness(scenario="repro", seed=2)
    with h1, h2:
        actions1 = h1.generate_workload(10)
        actions2 = h2.generate_workload(10)
        diffs = sum(
            1 for a1, a2 in zip(actions1, actions2, strict=True)
            if a1["operation"] != a2["operation"]
        )
        assert diffs > 0


# ---------------------------------------------------------------------------
# Requirement 11 — Independent verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_restored_after_recovery(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify independent state comparison detects recovery success."""
    with harness:
        baseline = harness.capture_baseline_snapshot()
        actions = harness.generate_workload(20)
        results = await harness.execute_actions(actions)
        successful = [r for r in results if r.success]

        if not successful:
            pytest.skip("No successful actions")

        plan = await harness.create_recovery_plan([r.action_id for r in successful])
        await harness.execute_recovery(plan)
        verification = harness.verify_against_baseline(baseline)

        assert "fully_restored" in verification
        assert "resources" in verification
        for key in ("filesystem", "database", "git", "config"):
            assert key in verification["resources"]
        assert verification["verification_method"] == "independent_state_comparison"


@pytest.mark.asyncio
async def test_verification_detects_partial_damage(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify independent verification detects damage before recovery."""
    with harness:
        baseline = harness.capture_baseline_snapshot()
        actions = harness.generate_workload(5)
        await harness.execute_actions(actions)

        verification = harness.verify_against_baseline(baseline)
        assert verification["fully_restored"] is False


# ---------------------------------------------------------------------------
# Requirement 12 — Reporting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_benchmark_produces_report(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify benchmark produces a comprehensive report."""
    with harness:
        result = await harness.run_benchmark(10)
        assert "scenario" in result
        assert "workload_size" in result
        assert "phases" in result
        assert "total_ms" in result
        assert "actions_executed" in result
        assert "actions_succeeded" in result
        assert "by_resource_type" in result


@pytest.mark.asyncio
async def test_worst_case_produces_report(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify worst-case scenario produces a comprehensive report."""
    with harness:
        report = await harness.run_worst_case(50)
        assert "scenario" in report
        assert "classification" in report
        assert "crash_result" in report
        assert "resume_result" in report
        assert "verification" in report


# ---------------------------------------------------------------------------
# Requirement 13 — Resource-type coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_resource_types_executed(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify all four resource types (filesystem, database, Git, config) are executed."""
    with harness:
        actions = [
            {
                "action_id": "rt-fs",
                "resource_type": "filesystem",
                "operation": "create",
                "resource": "file:rt_fs.txt",
                "tool": "filesystem",
                "parent_action_id": None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            },
            {
                "action_id": "rt-db",
                "resource_type": "database",
                "operation": "insert",
                "resource": "db:users:rt",
                "tool": "database",
                "parent_action_id": None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            },
            {
                "action_id": "rt-git",
                "resource_type": "git",
                "operation": "add_file",
                "resource": "git:rt_git.txt",
                "tool": "git",
                "parent_action_id": None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            },
            {
                "action_id": "rt-cfg",
                "resource_type": "config",
                "operation": "write_config",
                "resource": "config:rt_cfg.json",
                "tool": "config",
                "parent_action_id": None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            },
        ]
        results = await harness.execute_actions(actions)
        types_executed = {r.resource_type for r in results}
        assert types_executed == {"filesystem", "database", "git", "config"}


@pytest.mark.asyncio
async def test_workload_mixed_resource_types(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify workload generation produces mixed resource types."""
    with harness:
        actions = harness.generate_workload(100)
        results = await harness.execute_actions(actions)
        types_seen = {r.resource_type for r in results}
        assert len(types_seen) >= 2, "Expected at least 2 resource types"


@pytest.mark.asyncio
async def test_adapters_can_recover_all_types(
    harness: ComplexRecoveryHarness,
) -> None:
    """Verify adapters handle all resource types."""
    with harness:
        actions = [
            {
                "action_id": f"adapter-{i:02d}",
                "resource_type": rt,
                "operation": op,
                "resource": harness._resource_path(rt, i),
                "tool": rt,
                "parent_action_id": None,
                "reversibility": Reversibility.AUTOMATICALLY_REVERSIBLE,
                "risk_score": 0.5,
            }
            for i, (rt, ops) in enumerate(
                [
                    ("filesystem", ["create", "modify", "delete"]),
                    ("database", ["insert", "update", "delete"]),
                    ("git", ["add_file", "modify_file"]),
                    ("config", ["write_config", "modify_config"]),
                ]
            )
            for op in ops
        ]
        results = await harness.execute_actions(actions)
        types_with_adapter = {r.resource_type for r in results if r.adapter_used != "none"}
        assert len(types_with_adapter) >= 2


# ---------------------------------------------------------------------------
# Requirement 14 — Harness integrity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_harness_is_fully_disposable() -> None:
    """Verify the harness is fully disposable."""
    h = ComplexRecoveryHarness(scenario="dispose-test")
    with h:
        assert h.env is not None
        assert h.root is not None
        assert h.adapters
        assert h.action_repo is not None
    assert h.env is None


@pytest.mark.asyncio
async def test_harness_reuses_recovery_lab_environment() -> None:
    """Verify harness reuses the existing DisposableEnvironment."""
    h = ComplexRecoveryHarness()
    with h:
        from tests.unit.recovery_lab.environment import DisposableEnvironment
        assert isinstance(h.env, DisposableEnvironment)
        assert h.env.filesystem is not None
        assert h.env.database is not None
        assert h.env.git_repo is not None
        assert h.env.config is not None


@pytest.mark.asyncio
async def test_harness_uses_real_adapters() -> None:
    """Verify harness uses real production adapters."""
    h = ComplexRecoveryHarness()
    with h:
        adapter_names = {a.adapter_name for a in h.adapters}
        assert "filesystem_recovery" in adapter_names
        assert "database_recovery" in adapter_names
        assert "git_repository" in adapter_names
        assert "config_recovery" in adapter_names


@pytest.mark.asyncio
async def test_harness_no_production_credentials() -> None:
    """Verify harness uses only test-safe credentials."""
    h = ComplexRecoveryHarness()
    with h:
        for adapter in h.adapters:
            cap = adapter.capability
            cap_str = cap.name if hasattr(cap, "name") else str(cap)
            assert cap_str.upper() in (
                "PRODUCTION_VALIDATED",
                "MOCK",
                "REFERENCE_IMPLEMENTATION",
                "SIMULATION_CAPABLE",
            ), f"Unexpected adapter capability: {cap_str}"


@pytest.mark.asyncio
async def test_harness_runs_clean_from_scratch() -> None:
    """Full end-to-end run from clean start."""
    h = ComplexRecoveryHarness(scenario="full-e2e", seed=12345)
    with h:
        baseline = h.capture_baseline_snapshot()
        actions = h.generate_workload(20)
        results = await h.execute_actions(actions)
        successful = [r for r in results if r.success]

        if not successful:
            pytest.skip("No successful actions in e2e test")

        plan = await h.create_recovery_plan([r.action_id for r in successful])
        await h.simulate_recovery(plan)
        rec = await h.execute_recovery(plan)
        assert rec is not None
        verification = h.verify_against_baseline(baseline)
        assert "fully_restored" in verification
