# INTERLOCK V5 — RECOVERY ENGINE ROADMAP

**Date:** 2026-10-14
**Repository:** F:\Desktop_Data_2026\Desktop\INTERLOCK V4
**Branch:** master (HEAD 145a3d9; all V5 work uncommitted)
**Scope:** `app/`, `sdk/`, `tests/`, `alembic/`

---

## 1. PURPOSE

This roadmap defines the V5 recovery-engine workstreams that evolve Interlock
V4 into Interlock V5, the completion status of each workstream, and the
evidence backing each status claim. It is the controlling document for the V5
campaign; the remaining seven V5 documents are referenced from it as
workstream deliverables.

## 2. WORKSTREAMS AND STATUS

| # | Workstream | Status | Primary deliverable |
|---|-----------|--------|---------------------|
| 1 | Zero unexplained test failures (baseline 33) | **Complete** | `INTERLOCK_V5_RECOVERY_CORRECTNESS_REPORT.md` §1 |
| 2 | Adapter contract + capability registry | **Complete** | `app/domain/services/recovery_adapter_registry.py` + `tests/unit/test_v5_adapter_registry.py` (15 tests) |
| 3 | New resource adapters (environment, archive, DNS hosts) | **Complete for tested local scope** | `app/infrastructure/recovery/{environment,archive,hosts}_recovery_adapter.py` + 41 unit tests |
| 4 | Security hardening + containment | **Complete for tested local scope** | `INTERLOCK_V5_SECURITY_AND_CONTAINMENT_REPORT.md` |
| 5 | Distributed orchestrator reliability (leases, fencing, capability gating) | **Complete for single-process scope; multi-instance externally validated** | `app/domain/services/distributed_recovery_orchestrator.py` + `tests/unit/test_orchestrator_reliability.py` (12 tests) |
| 6 | Evidence / verification unification | **Complete** | `INTERLOCK_V5_RECOVERY_CORRECTNESS_REPORT.md` §3 |
| 7 | Tenant recovery quotas | **Complete (opt-in)** | `app/domain/services/tenant_quota_service.py` + `tests/unit/test_tenant_quota_service.py` (12 tests) |
| 8 | Certification lab (contract battery + behavioral probes) | **Complete** | `app/domain/services/recovery_certification_lab.py`, `app/infrastructure/recovery/certification_probes.py` + 8 tests |
| 9 | Benchmarks with measured budgets | **Complete for the tested machine** | `tests/performance/test_recovery_adapter_benchmark.py` (8 tests) + `INTERLOCK_V5_BENCHMARK_REPORT.md` |
| 10 | Failure-injection campaign | **Complete for injectable local faults; live-external injection pending** | `INTERLOCK_V5_FAILURE_INJECTION_REPORT.md` |
| 11 | Production gap documentation | **Complete** | `INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md` |
| 12 | Implementation changelog | **Complete** | `INTERLOCK_V5_IMPLEMENTATION_CHANGELOG.md` |

## 3. ARCHITECTURE OF THE V5 RECOVERY FRAMEWORK

```
ProtectedAction execution
        │
        ▼
RecoveryEvidence capture ────► RecoveryAdapterRegistry (contract validation,
        │                      capability declarations, resource selection)
        ▼
RecoveryPlan / DurableExecutionStep
        │
        ▼
DistributedRecoveryOrchestrator
  ├─ PlanLease (TTL + fencing token + expiry takeover) ─ single executor
  ├─ Capability gating (explicit-refusal verdicts cannot claim a step)
  ├─ Drift gate (NO_DRIFT / INSUFFICIENT_EVIDENCE pass; rest block)
  ├─ Conflict gate (concurrent mutation blocks)
  └─ Independent verification after each compensation
        │
        ▼
TenantQuotaService (plan budget / per-plan actions / concurrent slots)
        │
        ▼
RecoveryCertificationLab ──► capability matrix + benchmark budgets
```

## 4. DESIGN RULES (V5)

1. **Fail closed.** Missing evidence, unknown history (when required),
   authorization failures, idempotency mismatches, and contract violations
   never silently succeed.
2. **Drift must not block legitimate compensation.** When no after-state was
   recorded, a deviation from the before-state is classified
   `INSUFFICIENT_EVIDENCE`, which the orchestrator allows through; the
   adapter's own authorization and conflict gates still apply.
3. **Evidence cannot redirect writes.** Every adapter validates that payload
   paths stay inside configured/recorded roots at execution time
   (defense-in-depth against a tampered evidence store).
4. **Claims must be testable.** Adapters claim
   `PRODUCTION_VALIDATED` only for the scope actually exercised locally;
   external integrations are reported as awaiting external validation, never
   as certified.
5. **Quotas are opt-in.** A tenant without a registered policy is unlimited,
   so existing installations keep their behavior byte-for-byte.

## 5. EVIDENCE SUMMARY

- New V5 test files (8): 96 tests — registry 15, environment 15, archive 13,
  hosts 13, orchestrator reliability 12, tenant quota 12, certification lab 8,
  benchmarks 8 — plus 2 additive regression tests on existing files
  (config payload traversal, stress CWD restore).
- Baseline: 33 pre-existing failures (commit `c738c44`) — all reproduced,
  root-caused, fixed, and regression-tested (details in the correctness
  report §1; exact baseline failure list preserved in
  `$env:TEMP\baseline_tests.txt`).
- Final verification runs (2026-10-14/15, one process per scope):
  - `tests/unit tests/integration`: **2659 passed, 2 skipped, 0 failed**
    (15m53s) — skips are environment-bound (key manager unavailable;
    symlinks require admin on Windows).
  - `tests/stress`: **45 passed, 0 failed** (22m22s, includes the new
    V5-13 CWD-leak regression test).
  - Full suite (`tests`, all directories): **0 failed** — authoritative
    numbers in the final status report.
- Existing suites touched by V5 wiring re-run green:
  `test_distributed_recovery.py` 14/14, `test_surgical_recovery_pipeline.py` +
  `test_surgical_recovery_routes.py` 41/41, config suites 50/50, quota/
  planning tests green, benchmarks 8/8.

## 6. WHAT THIS ROADMAP EXPLICITLY DOES NOT CLAIM

- No live cloud, Vault/KMS, SIEM, ticketing, Postgres, or Kubernetes
  integration was executed; those adapters/paths are implemented where
  feasible and marked **external validation required**.
- No multi-instance lease store or distributed quota counter was exercised
  against a shared coordinator (Redis/Postgres); the protocol and in-memory
  reference implementation are tested, deployment backing is a gap item.
- Benchmark numbers are specific to the development machine and are
  budgets, not guarantees, for other hardware.

See `INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md` for the full gap register.
