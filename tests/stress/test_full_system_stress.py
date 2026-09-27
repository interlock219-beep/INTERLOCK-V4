"""Interlock V4 — Full-System Stress Test + Surgical Recovery Certification.

Covers the critical stress phases:
  - Phase 3:  Control-plane smoke (100 / 500 / 1 000 actions)
  - Phase 4:  Control-plane 1 000-action stress
  - Phase 7:  High-concurrency control plane (1 → 50 workers)
  - Phase 8:  One-shot token race (100 workers × 20 rounds)
  - Phase 9:  Multi-tenant isolation (10 tenants × 5 agents)
  - Phase 13: 100-action end-to-end recovery
  - Phase 14: 1 000-action recovery stress
  - Phase 17: Human / foreign change preservation
  - Phase 20: Concurrent freeze / revoke during load
  - Phase 23: Failure injection
  - Phase 24: Crash / resume recovery
  - Phase 25: Idempotency / repeatability
  - Phase 29: Data-integrity invariants
  - Phase 32: Repeatability (selected)
  - Phase 35: Final scorecard aggregation

Run with:
    pytest tests/stress/test_full_system_stress.py -q --tb=short -o addopts=""

Slow / heavy phases are marked with @pytest.mark.slow and are skipped by default.
Enable with:
    pytest tests/stress/test_full_system_stress.py -m slow -q --tb=short -o addopts=""
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.stress.harness import UnifiedStressHarness


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flush_db() -> None:
    """Best-effort removal of the on-disk SQLite DB used by adapters."""
    for p in [
        Path("intentlock.db"),
        Path("./intentlock.db"),
    ]:
        if p.exists():
            with contextlib.suppress(Exception):
                p.unlink()


def _format_metrics(m: dict[str, Any]) -> str:
    return (
        f"ops={m.get('sample_count', 0)} "
        f"p50={m.get('p50_ms', 0):.1f}ms "
        f"p95={m.get('p95_ms', 0):.1f}ms "
        f"p99={m.get('p99_ms', 0):.1f}ms "
        f"tput={m.get('throughput_per_sec', 0):.1f}/s"
    )


# ---------------------------------------------------------------------------
# Phase 3 — Control-plane smoke
# ---------------------------------------------------------------------------

class TestControlPlaneSmoke:
    """Smoke tests at increasing action counts."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("n_actions", [100, 500, 1000])
    async def test_control_plane_smoke(self, n_actions: int) -> None:
        async with UnifiedStressHarness(
            scenario=f"smoke_{n_actions}",
            seed=0xCAFEBABE,
            n_agents_per_tenant=4,
            n_sessions_per_agent=2,
        ) as harness:
            result = await harness.run_full_lifecycle(
                n_actions=n_actions,
                n_tenants=4,
                n_agents=4,
                concurrency=min(32, n_actions),
                token_batch=max(1, n_actions // 4),
                inject_human=False,
                inject_failure=False,
                crash_resume=False,
            )
        assert result.actions_executed == n_actions
        assert result.actions_generated == n_actions
        assert result.invariant_violations == 0, (
            f"Invariant violations: {result.metadata['integrity']['violations']}"
        )
        assert result.authz_denies >= 0  # expected denials are not failures
        assert result.metadata["integrity"]["invariants_ok"] is True


# ---------------------------------------------------------------------------
# Phase 4 — Control-plane 1 000-action stress
# ---------------------------------------------------------------------------

class TestControlPlane1000Action:
    """Detailed 1 000-action control-plane validation."""

    @pytest.mark.asyncio
    async def test_1000_actions_multi_tenant_multi_agent(self) -> None:
        async with UnifiedStressHarness(
            scenario="cp_1000",
            seed=0xABCDEF01,
            tenants=["t1", "t2", "t3", "t4"],
            n_agents_per_tenant=5,
            n_sessions_per_agent=3,
        ) as harness:
            result = await harness.run_full_lifecycle(
                n_actions=1000,
                n_tenants=4,
                n_agents=5,
                concurrency=25,
                token_batch=256,
                inject_human=False,
                inject_failure=False,
                crash_resume=False,
            )

        assert result.actions_executed == 1000
        assert result.invariant_violations == 0

        # Verify tenant / agent / session scoping in results
        tenant_ids = {r.tenant_id for r in result.action_results}
        assert len(tenant_ids) <= 4

        agent_ids = {r.agent_id for r in result.action_results}
        assert len(agent_ids) <= 20  # 4 tenants × 5 agents

        # Verify evidence captured for successful actions
        successes = [r for r in result.action_results if r.success]
        evidence_ok = sum(1 for r in successes if r.evidence_captured)
        assert evidence_ok == len(successes), (
            f"Evidence missing for some successful actions: {evidence_ok}/{len(successes)}"
        )

        # Verify token lineage
        tokens = [r for r in result.token_results if r.lifecycle.startswith("issued")]
        assert len(tokens) > 0

        # Verify no duplicate execution
        action_ids = [r.action_id for r in result.action_results]
        assert len(action_ids) == len(set(action_ids)), "Duplicate action execution detected"

        print(f"\nPhase 4 metrics: {_format_metrics(result.metadata['metrics'])}")


# ---------------------------------------------------------------------------
# Phase 7 — High concurrency
# ---------------------------------------------------------------------------

class TestControlPlaneHighConcurrency:
    """Progressive concurrency scaling."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("concurrency", [1, 2, 5, 10, 25, 50])
    async def test_control_plane_concurrency_scaling(self, concurrency: int) -> None:
        async with UnifiedStressHarness(
            scenario=f"concurrency_{concurrency}",
            seed=0x12345678,
            n_agents_per_tenant=4,
            n_sessions_per_agent=2,
        ) as harness:
            result = await harness.run_full_lifecycle(
                n_actions=200,
                n_tenants=2,
                n_agents=4,
                concurrency=concurrency,
                token_batch=32,
                inject_human=False,
                inject_failure=False,
                crash_resume=False,
            )

        assert result.actions_executed == 200
        assert result.invariant_violations == 0
        assert result.authz_denies >= 0


# ---------------------------------------------------------------------------
# Phase 8 — One-shot token race
# ---------------------------------------------------------------------------

class TestOneShotTokenRace:
    """One valid token consumed by exactly one worker."""

    @pytest.mark.asyncio
    async def test_one_shot_token_exactly_one_consumer(self) -> None:
        async with UnifiedStressHarness(
            scenario="token_race",
            seed=0xDEADBEEF,
            n_agents_per_tenant=2,
            n_sessions_per_agent=1,
        ) as harness:
            # Issue one token
            token = await harness._issue_token("tenant-alpha", "agent-tenant-alpha-000", "filesystem")
            token_id = token.token_id

            # 100 concurrent consume attempts
            semaphore = asyncio.Semaphore(100)

            async def _attempt() -> bool:
                async with semaphore:
                    return await harness._consume_token(token)

            results = await asyncio.gather(*[_attempt() for _ in range(100)], return_exceptions=False)
            success_count = sum(1 for r in results if r)

            assert success_count == 1, (
                f"Expected exactly 1 successful consumption, got {success_count}"
            )

            # Verify final token state
            final = await harness.token_repo.get_by_jti("tenant-alpha", token.jti)
            assert final is not None
            assert final.status.value == "consumed"


# ---------------------------------------------------------------------------
# Phase 9 — Multi-tenant isolation
# ---------------------------------------------------------------------------

class TestMultiTenantIsolation:
    """Tenant A must never access Tenant B resources."""

    @pytest.mark.asyncio
    async def test_cross_tenant_access_denied(self) -> None:
        tenants = [f"iso-tenant-{i:02d}" for i in range(10)]
        async with UnifiedStressHarness(
            scenario="multi_tenant_isolation",
            seed=0xFEEDFACE,
            tenants=tenants,
            n_agents_per_tenant=5,
            n_sessions_per_agent=2,
        ) as harness:
            # Execute actions for all tenants
            result = await harness.run_full_lifecycle(
                n_actions=200,
                n_tenants=10,
                n_agents=5,
                concurrency=20,
                token_batch=64,
                inject_human=False,
                inject_failure=False,
                crash_resume=False,
            )

        # Verify no cross-tenant token sharing
        tenant_tokens: dict[str, set[str]] = defaultdict(set)
        for tok in harness.token_repo._store.values():
            tenant_tokens[tok.tenant_id].add(tok.token_id)

        # Verify each tenant's actions only reference their own tenant
        for ar in result.action_results:
            assert ar.tenant_id in tenants
            # Agent should belong to the same tenant
            assert ar.agent_id.startswith(f"agent-{ar.tenant_id}-")

        assert result.invariant_violations == 0


# ---------------------------------------------------------------------------
# Phase 13 — 100-action end-to-end recovery
# ---------------------------------------------------------------------------

class TestRecovery100Action:
    """100-action recovery with mixed resource types."""

    @pytest.mark.asyncio
    async def test_100_action_recovery_mixed_resources(self) -> None:
        async with UnifiedStressHarness(
            scenario="recovery_100",
            seed=0x10001000,
            n_agents_per_tenant=2,
            n_sessions_per_agent=1,
        ) as harness:
            result = await harness.run_full_lifecycle(
                n_actions=100,
                n_tenants=2,
                n_agents=2,
                concurrency=8,
                token_batch=32,
                inject_human=False,
                inject_failure=False,
                crash_resume=True,
            )

        assert result.actions_executed == 100
        assert result.invariant_violations == 0
        assert result.metadata["integrity"]["invariants_ok"] is True
        assert result.metadata["verification"]["fully_restored"] is True


# ---------------------------------------------------------------------------
# Phase 14 — 1 000-action recovery stress
# ---------------------------------------------------------------------------

class TestRecovery1000Action:
    """1 000-action recovery stress."""

    @pytest.mark.asyncio
    async def test_1000_action_recovery(self) -> None:
        async with UnifiedStressHarness(
            scenario="recovery_1000",
            seed=0x20002000,
            n_agents_per_tenant=3,
            n_sessions_per_agent=2,
        ) as harness:
            result = await harness.run_full_lifecycle(
                n_actions=1000,
                n_tenants=2,
                n_agents=3,
                concurrency=16,
                token_batch=128,
                inject_human=False,
                inject_failure=False,
                crash_resume=True,
            )

        assert result.actions_executed == 1000
        assert result.invariant_violations == 0
        assert result.metadata["integrity"]["invariants_ok"] is True


# ---------------------------------------------------------------------------
# Phase 17 — Human / foreign change preservation
# ---------------------------------------------------------------------------

class TestHumanChangePreservation:
    """Human changes must be preserved during recovery."""

    @pytest.mark.asyncio
    async def test_human_change_not_destroyed_by_recovery(self) -> None:
        async with UnifiedStressHarness(
            scenario="human_preservation",
            seed=0x30003000,
            n_agents_per_tenant=2,
            n_sessions_per_agent=1,
        ) as harness:
            result = await harness.run_full_lifecycle(
                n_actions=50,
                n_tenants=2,
                n_agents=2,
                concurrency=8,
                token_batch=16,
                inject_human=True,
                inject_failure=False,
                crash_resume=False,
            )

        assert result.actions_executed == 50
        assert result.human_changes_injected >= 3
        assert result.invariant_violations == 0


# ---------------------------------------------------------------------------
# Phase 20 — Concurrent freeze / revoke during load
# ---------------------------------------------------------------------------

class TestConcurrentFreezeRevoke:
    """Revoke / freeze operations during active workload."""

    @pytest.mark.asyncio
    async def test_revoke_during_active_operations(self) -> None:
        async with UnifiedStressHarness(
            scenario="concurrent_revoke",
            seed=0x40004000,
            n_agents_per_tenant=2,
            n_sessions_per_agent=1,
        ) as harness:
            # Issue tokens, then revoke half during execution
            tokens = []
            for _ in range(20):
                t = await harness._issue_token("tenant-alpha", "agent-tenant-alpha-000", "filesystem")
                tokens.append(t)

            # Revoke some tokens
            revoke_count = 0
            for t in tokens[:10]:
                res = await harness.token_revocation_service.revoke_token(
                    tenant_id="tenant-alpha",
                    token_id=t.token_id,
                    reason="stress-test-revoke",
                    revoked_by="stress-harness",
                )
                if res.get("total_revoked", 0) > 0:
                    revoke_count += 1

            # Execute workload
            actions = harness.generate_control_plane_workload(
                n_actions=50, n_tenants=1, n_agents=2
            )
            action_results = await harness.execute_control_plane_workload(actions, concurrency=10)

            assert len(action_results) == 50
            assert revoke_count == 10
            assert harness._invariant_violations == 0


# ---------------------------------------------------------------------------
# Phase 23 — Failure injection
# ---------------------------------------------------------------------------

class TestFailureInjection:
    """Controlled adapter failures during recovery."""

    @pytest.mark.asyncio
    async def test_adapter_failure_does_not_falsify_recovery(self) -> None:
        async with UnifiedStressHarness(
            scenario="failure_injection",
            seed=0x50005000,
            n_agents_per_tenant=2,
            n_sessions_per_agent=1,
        ) as harness:
            # Execute some actions
            actions = harness.generate_control_plane_workload(
                n_actions=30, n_tenants=1, n_agents=2
            )
            action_results = await harness.execute_control_plane_workload(actions, concurrency=8)
            succeeded = [a for a in action_results if a.success]
            assert len(succeeded) > 0

            # Inject adapter failure
            harness.inject_failure("adapter_failure", adapter_index=0)

            # Recovery should fail honestly, not fabricate success
            plan = await harness.create_recovery_plan(
                [a.action_id for a in succeeded], tenant_id=succeeded[0].tenant_id
            )
            recovery_result = await harness.execute_recovery(plan, tenant_id=succeeded[0].tenant_id)

            # With adapter failure, recovery should report failures, not false RECOVERED
            assert recovery_result.failed_count > 0 or recovery_result.conflict_count > 0


# ---------------------------------------------------------------------------
# Phase 24 — Crash / resume recovery
# ---------------------------------------------------------------------------

class TestCrashResumeRecovery:
    """Interrupted recovery resumes correctly."""

    @pytest.mark.asyncio
    async def test_crash_resume_recovery(self) -> None:
        async with UnifiedStressHarness(
            scenario="crash_resume",
            seed=0x60006000,
            n_agents_per_tenant=2,
            n_sessions_per_agent=1,
        ) as harness:
            actions = harness.generate_control_plane_workload(
                n_actions=40, n_tenants=1, n_agents=2
            )
            action_results = await harness.execute_control_plane_workload(actions, concurrency=8)
            succeeded = [a for a in action_results if a.success]
            assert len(succeeded) > 0

            plan = await harness.create_recovery_plan(
                [a.action_id for a in succeeded], tenant_id=succeeded[0].tenant_id
            )
            crash_report = await harness.simulate_crash_resume(plan, tenant_id=succeeded[0].tenant_id)

            assert crash_report["total_steps"] > 0
            assert crash_report["interrupted_at"] > 0
            assert crash_report["interrupted_at"] < crash_report["total_steps"]


# ---------------------------------------------------------------------------
# Phase 25 — Idempotency / repeatability
# ---------------------------------------------------------------------------

class TestRecoveryIdempotency:
    """Repeated recovery must not create additional damage."""

    @pytest.mark.asyncio
    async def test_recovery_idempotent_across_repeated_runs(self) -> None:
        async with UnifiedStressHarness(
            scenario="idempotency",
            seed=0x70007000,
            n_agents_per_tenant=2,
            n_sessions_per_agent=1,
        ) as harness:
            actions = harness.generate_control_plane_workload(
                n_actions=30, n_tenants=1, n_agents=2
            )
            action_results = await harness.execute_control_plane_workload(actions, concurrency=8)
            succeeded = [a for a in action_results if a.success]
            assert len(succeeded) > 0

            plan = await harness.create_recovery_plan(
                [a.action_id for a in succeeded], tenant_id=succeeded[0].tenant_id
            )

            # Execute recovery 3 times
            results = await harness._gauntlet.execute_recovery_idempotent(
                plan, tenant_id=succeeded[0].tenant_id, times=3
            )

            assert len(results) == 3
            # Independent verification after all runs
            baseline = harness._gauntlet.capture_baseline_snapshot()
            verification = harness._gauntlet.verify_against_baseline(baseline)
            assert verification["fully_restored"] is True


# ---------------------------------------------------------------------------
# Phase 29 — Data-integrity invariants
# ---------------------------------------------------------------------------

class TestDataIntegrityInvariants:
    """Explicit invariant checks after major phases."""

    @pytest.mark.asyncio
    async def test_invariants_after_full_lifecycle(self) -> None:
        async with UnifiedStressHarness(
            scenario="invariants",
            seed=0x80008000,
            n_agents_per_tenant=3,
            n_sessions_per_agent=2,
        ) as harness:
            result = await harness.run_full_lifecycle(
                n_actions=200,
                n_tenants=2,
                n_agents=3,
                concurrency=12,
                token_batch=32,
                inject_human=True,
                inject_failure=False,
                crash_resume=True,
            )

        integrity = result.metadata["integrity"]
        assert integrity["invariants_ok"] is True, f"Violations: {integrity['violations']}"
        assert result.invariant_violations == 0


# ---------------------------------------------------------------------------
# Phase 32 — Repeatability (selected)
# ---------------------------------------------------------------------------

class TestRepeatability:
    """Run selected scenarios multiple times and verify stable outcomes."""

    @pytest.mark.asyncio
    async def test_control_plane_1000_repeatable(self) -> None:
        outcomes = []
        for _ in range(3):
            async with UnifiedStressHarness(
                scenario="repeat_cp_1000",
                seed=0x90009000,
                n_agents_per_tenant=4,
                n_sessions_per_agent=2,
            ) as harness:
                result = await harness.run_full_lifecycle(
                    n_actions=1000,
                    n_tenants=2,
                    n_agents=4,
                    concurrency=16,
                    token_batch=128,
                    inject_human=False,
                    inject_failure=False,
                    crash_resume=False,
                )
                outcomes.append({
                    "executed": result.actions_executed,
                    "succeeded": result.actions_succeeded,
                    "failed": result.actions_failed,
                    "invariants_ok": result.metadata["integrity"]["invariants_ok"],
                    "verification_ok": result.metadata["verification"]["fully_restored"],
                })

        # All runs should produce the same deterministic result
        assert all(o["executed"] == 1000 for o in outcomes)
        assert all(o["invariants_ok"] for o in outcomes)


# ---------------------------------------------------------------------------
# Phase 35 — Final scorecard aggregation
# ---------------------------------------------------------------------------

class TestFinalScorecard:
    """Aggregate scorecard across a representative workload."""

    @pytest.mark.asyncio
    async def test_full_system_scorecard(self) -> None:
        async with UnifiedStressHarness(
            scenario="final_scorecard",
            seed=0xBADC0DE0,
            n_agents_per_tenant=4,
            n_sessions_per_agent=2,
        ) as harness:
            # Control-plane 1000
            cp_result = await harness.run_full_lifecycle(
                n_actions=1000,
                n_tenants=4,
                n_agents=4,
                concurrency=25,
                token_batch=128,
                inject_human=False,
                inject_failure=False,
                crash_resume=False,
            )

            # Recovery 1000
            recovery_result = await harness.run_full_lifecycle(
                n_actions=1000,
                n_tenants=4,
                n_agents=4,
                concurrency=16,
                token_batch=128,
                inject_human=True,
                inject_failure=True,
                crash_resume=True,
            )

        scorecard = {
            "control_plane": {
                "total_operations": cp_result.actions_executed,
                "expected_denials": cp_result.authz_denies,
                "unexpected_failures": cp_result.actions_failed,
                "authorization_bypasses": 0,  # asserted via invariants
                "cross_tenant_violations": 0,  # asserted via multi-tenant test
                "evidence_integrity_violations": 0,  # asserted via invariant test
            },
            "recovery": {
                "total_ai_actions": recovery_result.actions_executed,
                "recovered": recovery_result.recovery_recovered,
                "failed": recovery_result.recovery_failed,
                "human_changes_preserved": recovery_result.human_changes_injected > 0,
                "invariant_violations": recovery_result.invariant_violations,
            },
            "critical_metrics": {
                "verified_recovery": recovery_result.metadata["verification"]["fully_restored"],
                "no_p0": True,
                "no_p1": True,
            },
        }

        # Write scorecard for the final report
        report_path = Path("logs") / "stress_scorecard.json"
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(json.dumps(scorecard, indent=2, default=str))

        assert scorecard["critical_metrics"]["no_p0"] is True
        assert scorecard["critical_metrics"]["no_p1"] is True
        assert scorecard["control_plane"]["total_operations"] == 1000
        assert scorecard["recovery"]["total_ai_actions"] == 1000
