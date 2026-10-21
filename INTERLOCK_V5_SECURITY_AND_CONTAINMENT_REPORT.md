# INTERLOCK V5 — SECURITY AND CONTAINMENT REPORT

**Date:** 2026-10-14
**Repository:** F:\Desktop_Data_2026\Desktop\INTERLOCK V4
**Scope:** recovery adapters, evidence pipeline, orchestrator, quotas, routes

---

## 1. THREAT MODEL (RECOVERY PATH)

The V5 recovery engine treats the following as attacker-influencable:

| Surface | Attacker capability assumed |
|---|---|
| Compensation payloads | Full read/write of stored evidence payloads (tamper `target_path`, `hosts_path`, `archive_path`, `config_file`, `config_dir`, `idempotency_key`, tenant fields) |
| Protected action inputs | Control `resource`, `tool`, `action_type`, `before_state_ref`, `tool_arguments` |
| Agent/user identity | Supply `tenant_id`, `agent_id` including placeholder values (`null`, `system`) |
| Host state | Files deleted/modified between capture and compensation; concurrent writers |
| Drift inputs | Craft `current_state` dicts passed to `detect_drift`/`check_conflicts` |

Out of scope for local testing (registered in `INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md`): compromise of the evidence store itself to forge *hashes consistently* (integrity relies on store-level access control + hash chain), and live external services.

## 2. CONTROLS — LAYER BY LAYER

### 2.1 Identity & authorization (fail closed)

| Control | Implementation | Test evidence |
|---|---|---|
| Tenant isolation on capture | `_verify_tenant_isolation` in every adapter — refuses missing/placeholder (`null`, `system`) tenants with `ValueError` | env/archive/hosts "tenant_isolation_guard" probes; adapter unit suites |
| Tenant binding on evidence | `RecoveryEvidence.tenant_id` required; repos filter by tenant | verification + surgical suites |
| Authorization before compensation | `_verify_compensation_authorization` — missing authorization context or non-executable action → `BLOCKED_BY_CONFLICT` (never partial execution) | base-recovery tests + adapter suites |
| Cross-tenant grants | Cross-tenant authority grants → **DENY** | `test_advanced_authorization.py` (baseline fix) |
| HTTP layer | `QuotaExceededError` → 429; recovery routes require auth context | route/integration suites |

### 2.2 Input validation (deny by default)

| Adapter | Rule | Failure |
|---|---|---|
| environment | Variable name must match `[A-Za-z_][A-Za-z0-9_]*`; no `=`, NUL, newline (`extract_var_name`) | `ValueError` |
| environment | Capture refuses vars outside configured `allowed_prefixes` (empty set = deny all) | `ValueError` — V5 fix (V5-7) |
| archive | Target/archive must be absolute, no NUL, not a filesystem root, inside `allowed_roots` (when configured) | `ValueError` |
| hosts | Hostname charset: letters/digits/dots/hyphens only; no space, `/`, `#`, NUL (`extract_hostname`) | `ValueError` |
| config | `config_file` from resource: no `..`, no NUL (`_extract_config_file`) | `ValueError` |
| filesystem | `_resolve_file_path` rejects `..` traversal relative to `base_path` | `ValueError` (V4 + V5 regression tests) |

### 2.3 Execution-time containment (defense in depth against tampered payloads)

A tampered evidence store must not be able to redirect a write. Each adapter
re-validates payload paths **at execute time**, independent of what capture
recorded:

| Adapter | Execute-time re-validation | Test evidence |
|---|---|---|
| archive | Archive file must resolve inside the adapter's state directory **and** target must satisfy `allowed_roots` — checked in `_restore_archive` **before** opening | `test_target_path_redirection_refused`, `test_archive_path_redirection_refused` (V5-4) |
| hosts | Payload `hosts_path` must equal the configured hosts file exactly | `test_write_direction_refused` / hosts probe `write_redirection_guard` |
| config | `_safe_config_path`: rejects NUL/absolute/drive-relative/`..`; resolved path must be strictly inside `config_dir` — used by restore/delete/restore-deleted/verify | `test_payload_path_traversal_refused` (V5-9) |
| filesystem | Payload `file_path` traversal rejected at execute | `test_execute_restore_content_rejects_traversal` |
| git | `_resolve_payload_path` applied to every `_execute_*` operation and `verify`: rejects absolute/drive/root-anchored/NUL/`..` payload paths and any escape via symlinks (`Path.resolve` containment); drift/conflict raise through `_resolve_resource_path` instead of trusting the join | `tests/unit/test_git_repository_adapter.py` tamper-payload battery (V5-16, RED→GREEN this run) |

**Documented residual:** `config_dir` itself comes from the payload (production
flow constructs `ConfigRecoveryAdapter()` without a directory; capture records
it). Containment *within* that directory is enforced; substitution of the
directory as a whole assumes evidence-store compromise — registered as gap
G-6 (recommendation: construct the adapter with a configured `config_dir` in
deployments, or sign payloads).

### 2.4 Atomicity & idempotency

- All file writes go through temp-file + `os.replace` (atomic on same volume).
- `idempotency_key` mismatch on compensation → `BLOCKED_BY_CONFLICT`, never a
  second application (probes: env, filesystem — `idempotency_guard`).
- Durable orchestrator steps are idempotent by `step_id`; plan execution is
  fenced by monotonic `fencing_token` lease (V5-11: tombstones keep tokens
  strictly increasing per plan).

### 2.5 Evidence integrity & redaction

- Results/details expose **hashes only** for restored values (env
  `value_redaction` probe asserts the raw value never appears in
  `CompensationResult.details`, `error`, or `before_state_reference`).
- Tampered snapshot content is detected: archive verifies sha256 of archive
  bytes before extraction → refusal (`tampered_snapshot_refusal` probe,
  "tampered" in error).
- Drift/conflict comparisons are hash-based (config/filesystem) or
  line/hostname-scoped (hosts) — no raw secret material in drift details.

### 2.6 Orchestrator gates (ordered, fail-closed)

Per step: capability gate (explicit-refusal verdicts cannot claim a step) →
evidence lookup (missing → `REQUIRES_MANUAL_ACTION`) → drift gate
(`DRIFT_DETECTED`/`RESOURCE_MISSING`/error block; `NO_DRIFT`/
`INSUFFICIENT_EVIDENCE` pass) → conflict gate (concurrent mutation blocks) →
compensation (authorization + idempotency inside adapter) → **independent
verification** (unverified → step not completed). Lease loss mid-plan aborts
with `lease_lost` (another executor may have taken over).

### 2.7 Quota & abuse resistance

- Quotas bound plan creation rate, per-plan action count, and concurrent
  compensations per tenant — resource-exhaustion control on recovery paths
  (`QuotaExceededError` → HTTP 429, retry window surfaced).
- Process-local counters only — multi-instance deployments need a shared
  backend (gap G-2).

### 2.8 Transport/route layer

- Surgical recovery routes: auth-required, tenant-scoped; quota errors mapped
  to 429 (create + execute); no exception detail leakage (messages are
  generic at HTTP boundary).
- `AUTHORIZATION_REQUIRE_TENANT` honored (test env sets `false`; production
  defaults enforced by Settings validation).

## 3. ADVERSARIAL TEST INVENTORY

| Attack | Test |
|---|---|
| Placeholder tenant capture | env/archive/hosts tenant probes; adapter suites |
| Env var-name injection (`env:A=B`) | `var_name_injection_guard` probe |
| Env var outside allowed prefixes | `test_allowed_prefixes_deny_by_default` |
| Archive target redirection | `test_target_path_redirection_refused` |
| Archive path redirection | `test_archive_path_redirection_refused` |
| Archive path traversal / root escape / NUL | `test_path_guards_reject_bad_targets` |
| Archive tampered content | `test_tampered_archive_refused` + `tampered_snapshot_refusal` probe |
| Hosts hostname injection | `hostname_injection_guard` probe |
| Hosts file write redirection | `write_redirection_guard` probe |
| Config payload traversal | `test_payload_path_traversal_refused` (V5-9) |
| Filesystem traversal (capture + execute) | `test_resolve_file_path_rejects_traversal`, `test_execute_restore_content_rejects_traversal` |
| Idempotency replay | env + filesystem `idempotency_guard` probes |
| Cross-tenant authority grants | `test_cross_tenant_isolation_authority_grants` (DENY) |
| Unknown agent history | `agent_history_required=True` → fail-closed DENY |
| Missing evidence in orchestrator | `test_distributed_recovery.py` manual-action paths |
| Concurrent plan execution | lease conflict/takeover tests (`test_orchestrator_reliability.py`) |
| Quota exhaustion | `test_tenant_quota_service.py` (atomic check-and-reserve, concurrent slots) |

## 4. HONEST LIMITATIONS

1. **No live external systems were attacked or tested** — cloud, Vault/KMS,
   SIEM, ticketing, Postgres, Kubernetes paths are implemented where
   feasible but **not validated** in this environment.
2. Evidence-store protection (at rest, in transit, signatures) is
   infrastructure-owned; V5 adds payload-level containment but does not
   implement payload signing (gap G-6).
3. Process-local quotas/leases are single-process guarantees; distributed
   backends are protocol-tested only (gaps G-1, G-2).
4. OTel is opt-in (`INTERLOCK_OTEL_ENABLED=1`); with it enabled, exporter
   configuration security (endpoint TLS, credential handling) is delegated to
   operator configuration.
5. Hosts-file protection is file-level; a compromised process with direct
   write access outside Interlock is outside this control scope.

**Status claim:** controls above are certified for the tested local scope;
external validation required for everything in §4.1/§4.3.
