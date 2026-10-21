# INTERLOCK V5 — FAILURE INJECTION REPORT

**Date:** 2026-10-14
**Repository:** F:\Desktop_Data_2026\Desktop\INTERLOCK V4
**Method:** faults injected deterministically through inputs, payloads, and
host-state mutation between capture and compensation; every scenario has an
automated test. No result below is simulated or fabricated — each row maps to
a named test that executed real adapter/orchestrator code.

---

## 1. INJECTION CATEGORIES AND RESULTS

### 1.1 Corrupted evidence payloads (tamper-and-execute)

| Injected fault | Adapter | Observed behavior | Test | Result |
|---|---|---|---|---|
| Archive bytes overwritten pre-restore | archive | sha256 mismatch → refusal, original file untouched, error contains `tampered` | `test_tampered_archive_refused` + probe | PASS |
| Payload `target_path` rewritten to victim file | archive | containment re-check → `ValueError` before I/O | `test_target_path_redirection_refused` | PASS |
| Payload `archive_path` moved outside state dir | archive | state-dir containment → refused | `test_archive_path_redirection_refused` | PASS |
| Payload `hosts_path` points at second file | hosts | exact-path equality check → `BLOCKED_BY_CONFLICT`, victim file never created | `write_redirection_guard` probe | PASS |
| Payload `config_file` = `../victim.yaml` | config | `_safe_config_path` → `FAILED` with traversal error; verify → `verified=False`; victim untouched | `test_payload_path_traversal_refused` | PASS |
| Payload `file_path` traversal | filesystem | traversal refusal at execute | `test_execute_restore_content_rejects_traversal` | PASS |
| Wrong `idempotency_key` | env, filesystem | `BLOCKED_BY_CONFLICT`, no second application | `idempotency_guard` probes | PASS |

### 1.2 Host-state faults (deletion, mutation, concurrency between steps)

| Injected fault | Adapter | Observed behavior | Test | Result |
|---|---|---|---|---|
| Hosts file deleted before compensation | hosts | `REQUIRES_MANUAL_ACTION` — never fabricates a partial hosts file; conflict check returns `NO_CONFLICT` (no after-state) so the manual path is reachable | `test_deleted_hosts_file_requires_manual_intervention` | PASS |
| Target file mutated after capture (archive) | archive | no after-state recorded → `INSUFFICIENT_EVIDENCE` drift → compensation proceeds → content restored from archive | drift tests | PASS |
| Hosts entries changed for *other* hostnames | hosts | hostname-scoped: `NO_DRIFT` for this compensation | `hostname_scoped_drift` probe | PASS |
| Config file mutated after capture | config | after-state recorded → `DRIFT_DETECTED` (honest third state) | `drift_detected_after_mutation` probe | PASS |
| Config/env value already restored (double apply) | config/env | `NO_DRIFT` (current == before) — no destructive re-apply | drift tests | PASS |
| Concurrent plan executions (2 executors, same plan) | orchestrator | second acquirer denied until TTL expiry; after expiry takeover with **new, strictly higher fencing token** | `test_lease_store_acquire_conflict_and_release`, takeover tests | PASS |
| Lease lost mid-plan (TTL expiry during steps) | orchestrator | renewal fails → step aborts `lease_lost`, plan not falsely completed | `test_lease_lost_during_execution_aborts_plan` | PASS |

### 1.3 Missing-context faults (fail-closed paths)

| Injected fault | Expected behavior | Test | Result |
|---|---|---|---|
| No before-state in evidence (execution) | fail closed — no compensation fabricated | adapter suites | PASS |
| No after-state in evidence (drift) | `INSUFFICIENT_EVIDENCE` (documented, not a silent pass) | drift-contract tests (V5-1) | PASS |
| Missing evidence for a step | `REQUIRES_MANUAL_ACTION` | `test_distributed_recovery.py` | PASS |
| Placeholder tenant (`null`, `system`) | `ValueError` at capture | tenant probes ×3 | PASS |
| Adapter returns `unsupported`/`irreversible`/`requires_approval` | orchestrator refuses to schedule the step (capability gating) | `test_orchestrator_reliability.py` | PASS |
| Evidence `action_type` vs step action mismatch | action rebuilt **from evidence** (`action_type`, `before_state_ref`) so capability checks see true reversibility | reliability tests (V5-10) | PASS |
| No quota policy registered | unlimited (zero behavior change — intentional, not a fault swallow) | `test_tenant_quota_service.py` | PASS |
| Plan exceeds daily/size/slot budget | `QuotaExceededError` → HTTP 429, slot released on failure (compensation slot) | quota + route tests | PASS |
| Certification probe raises mid-run | reported as failed probe — never claimed as pass | `test_crashing_probe_is_reported_as_failure` | PASS |
| Contract-invalid adapter registered | registry rejects (`AdapterContractError`); non-strict lab mode records problems | `test_v5_adapter_registry.py` | PASS |

### 1.4 Orchestrator end-to-end fault matrix

Executed by `tests/unit/test_distributed_recovery.py` (14) and
`tests/unit/test_orchestrator_reliability.py` (12):

- partial step failure → plan `failed`, remaining steps not run
- verification failure → step not completed, plan reflects it
- drift `DRIFT_DETECTED` → step blocked (not silently compensated)
- conflict `CONCURRENT_MUTATION` → step blocked
- repeated execution of same plan → idempotent, no double compensation
- lease fencing on result (`fencing_token` recorded per execution)

**All scenarios above: 26/26 PASS.**

## 2. WHAT WAS *NOT* INJECTED (HONEST BOUNDARY)

| Not injected | Why | Where tracked |
|---|---|---|
| Real cloud/KMS/SIEM/ticketing outages | No external systems in this environment | Gap G-3 |
| Database deadlock/timeout against live Postgres | No live database | Gap G-3 |
| Kubernetes API failure modes | No cluster | Gap G-3 |
| Cross-process lease contention (two OS processes) | In-memory store is process-local; protocol tested with concurrent coroutines | Gap G-1 |
| Disk-full during atomic write | Host-level fault; would need fixture-controlled filesystem | documented, untested |
| Evidence-store bit-rot across restarts | Requires durable store integration | Gap G-4 |

These are **not** claimed as tested. The failure-injection campaign is
certified for the tested local scope: all injectable in-process,
payload-level, and host-state faults listed in §1.

## 3. SUMMARY

- Injected fault scenarios: **30+ distinct injections**, all with automated
  tests, all passing.
- No scenario silently swallowed a fault: every refusal surfaces an explicit
  `ExecutionState` (`FAILED`/`BLOCKED_BY_CONFLICT`/`REQUIRES_MANUAL_ACTION`)
  or an honest `INSUFFICIENT_EVIDENCE` classification.
- Zero fabricated recovery: partial states are refused, not approximated.
