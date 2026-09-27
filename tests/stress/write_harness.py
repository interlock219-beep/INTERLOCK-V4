import os
path = r'F:\Desktop_Data_2026\Desktop\INTERLOCK V4\tests\stress\harness.py'

part7 = """

    # ------------------------------------------------------------------
    # Latency / throughput metrics
    # ------------------------------------------------------------------

    def _percentile(self, data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        k = (len(s) - 1) * (pct / 100.0)
        f = int(k)
        c = f + 1 if f + 1 < len(s) else f
        if f == c:
            return s[f]
        return s[f] + (k - f) * (s[c] - s[f])

    def compute_metrics(self, elapsed_ms: float) -> dict[str, Any]:
        all_latencies = self._action_latencies
        throughput = (
            (len(all_latencies) / (elapsed_ms / 1000.0))
            if elapsed_ms > 0
            else 0.0
        )
        return {
            "p50_ms": self._percentile(all_latencies, 50),
            "p95_ms": self._percentile(all_latencies, 95),
            "p99_ms": self._percentile(all_latencies, 99),
            "throughput_per_sec": throughput,
            "sample_count": len(all_latencies),
            "min_ms": min(all_latencies) if all_latencies else 0.0,
            "max_ms": max(all_latencies) if all_latencies else 0.0,
            "mean_ms": statistics.mean(all_latencies) if all_latencies else 0.0,
        }

    # ------------------------------------------------------------------
    # Full lifecycle runner
    # ------------------------------------------------------------------

    async def run_full_lifecycle(
        self,
        n_actions: int,
        n_tenants: int = 4,
        n_agents: int = 4,
        concurrency: int = 16,
        token_batch: int = 64,
        inject_human: bool = True,
        inject_failure: bool = False,
        crash_resume: bool = True,
    ) -> StressResult:
        \"\"\"Run the full stress lifecycle end-to-end.

        Phases:
          1. Generate control-plane workload
          2. Evaluate authorization for all actions
          3. Execute actions with concurrency
          4. Issue / consume / expire / revoke tokens
          5. Create and execute recovery plan
          6. Independent verification
          7. Inject human changes (optional)
          8. Inject failures (optional)
          9. Crash / resume (optional)
          10. Data-integrity invariant checks
        \"\"\"
        started_at = datetime.now(UTC).isoformat()
        t_global_start = time.monotonic()

        # Phase 1: generate workload
        actions = self.generate_control_plane_workload(n_actions, n_tenants, n_agents)

        # Phase 2: authorization
        await self.evaluate_authz_for_actions(actions)

        # Phase 3: execute
        action_results = await self.execute_control_plane_workload(actions, concurrency=concurrency)

        succeeded = [a for a in action_results if a.success]
        failed = [a for a in action_results if not a.success]

        # Phase 4: token lifecycle
        token_results = await self.simulate_token_lifecycle(token_batch)

        # Phase 5: recovery plan
        plan = None
        recovery_result = None
        if succeeded:
            plan = await self.create_recovery_plan(
                [a.action_id for a in succeeded],
                tenant_id=succeeded[0].tenant_id,
            )
            recovery_result = await self.execute_recovery(
                plan, tenant_id=succeeded[0].tenant_id
            )

        # Phase 6: independent verification
        baseline = self._gauntlet.capture_baseline_snapshot()
        verification = await self.verify_recovery_independently(baseline)

        # Phase 7: human changes
        if inject_human:
            for case in ("A", "B", "C"):
                rt = self._rand_choice(self.RESOURCE_TYPES)
                resource = f"{rt}:human-{uuid4().hex[:8]}"
                await self.inject_human_change(case, rt, resource)

        # Phase 8: failure injection
        if inject_failure and self._gauntlet.adapters:
            self.inject_failure("adapter_failure", adapter_index=0)

        # Phase 9: crash/resume
        crash_resume_report = None
        if crash_resume and plan is not None:
            crash_resume_report = await self.simulate_crash_resume(plan)

        # Phase 10: invariants
        integrity = await self.check_data_integrity_invariants()

        # Authz summary
        authz_decisions = [d.decision for d in self._authz_results]
        authz_allows = sum(1 for d in authz_decisions if d == "allow")
        authz_denies = sum(1 for d in authz_decisions if d == "deny")
        authz_hitls = sum(1 for d in authz_decisions if d == "require_hitl")

        # Token summary
        tokens_issued = sum(1 for r in self._token_results if r.lifecycle.startswith("issued"))
        tokens_consumed = sum(1 for r in self._token_results if "consumed" in r.lifecycle)
        tokens_expired = sum(1 for r in self._token_results if "expired" in r.lifecycle)
        tokens_revoked = sum(1 for r in self._token_results if "revoked" in r.lifecycle)

        elapsed_ms = (time.monotonic() - t_global_start) * 1000.0
        finished_at = datetime.now(UTC).isoformat()
        metrics_summary = self.compute_metrics(elapsed_ms)

        result = StressResult(
            scenario=self.scenario,
            seed=self._seed,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_ms=elapsed_ms,
            tenants=self._tenants,
            actions_generated=len(actions),
            actions_executed=len(action_results),
            actions_succeeded=len(succeeded),
            actions_failed=len(failed),
            tokens_issued=tokens_issued,
            tokens_consumed=tokens_consumed,
            tokens_expired=tokens_expired,
            tokens_revoked=tokens_revoked,
            authz_allows=authz_allows,
            authz_denies=authz_denies,
            authz_hitls=authz_hitls,
            evidence_count=len(self._gauntlet.evidence_repo._store),
            plans_created=1 if plan is not None else 0,
            plans_executed=1 if recovery_result is not None else 0,
            recovery_recovered=getattr(recovery_result, "recovered_count", 0),
            recovery_failed=getattr(recovery_result, "failed_count", 0),
            human_changes_injected=self._human_changes_injected,
            failures_injected=self._failures_injected,
            crash_resume_cycles=self._crash_resume_cycles,
            invariant_violations=integrity.get("violation_count", 0),
            latency_p50_ms=metrics_summary["p50_ms"],
            latency_p95_ms=metrics_summary["p95_ms"],
            latency_p99_ms=metrics_summary["p99_ms"],
            throughput_per_sec=metrics_summary["throughput_per_sec"],
            action_results=action_results,
            token_results=token_results,
            authz_results=self._authz_results,
            errors=[r.error for r in failed if r.error],
            metadata={
                "verification": verification,
                "crash_resume": crash_resume_report,
                "integrity": integrity,
                "metrics": metrics_summary,
            },
        )
        return result
"""

with open(path, 'a', encoding='utf-8') as f:
    f.write(part7)
print('part7 ok')
