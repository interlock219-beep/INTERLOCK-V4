# INTERLOCK V5 — IMPLEMENTATION CHANGELOG

**Date:** 2026-10-14 (implementation) · **2026-10-15 (final verification &
release gate run — see §5)**
**Branch:** master · HEAD `145a3d9` · **all changes uncommitted** (pending user
review; `web/` deletions and `interlock_projects/` excluded from V5 scope,
`stash@{0}` untouched).

---

## 1. NEW FILES (V5)

### 1.1 Production code

| File | Summary |
|---|---|
| `app/domain/services/recovery_adapter_registry.py` | V5 adapter contract + capability registry: `validate_contract` battery (identity, async protocol surface, legacy trio, capability value), strict registration with `AdapterContractError`, non-strict lab mode, resource-kind selection. |
| `app/domain/services/tenant_quota_service.py` | `TenantQuotaPolicy`/`QuotaDecision`/`QuotaExceededError(ValueError)`/`TenantQuotaService` — atomic check-and-reserve, daily window, per-plan action count, concurrent-execute slots, threadsafe; opt-in (no policy = unlimited). **2026-10-15 gate:** counters extracted behind the `QuotaCounterStore` protocol (`InProcessQuotaCounterStore` reference impl + shared contract tests; services can be pointed at one store = cross-instance quota domain). |
| `app/domain/services/recovery_certification_lab.py` | Two-tier certification: contract battery + behavioral probes (isolated temp workspace) + honest contract-only mode; `run_probe_check` converts probe exceptions to failed results (V5-12). |
| `app/infrastructure/recovery/environment_recovery_adapter.py` | Process-environment recovery for `env:<VAR>`: allowed-prefix deny-by-default capture (V5-7), var-name injection guard, value redaction (hash-only surfaces), drift contract, tenant/idempotency guards. |
| `app/infrastructure/recovery/archive_recovery_adapter.py` | tar.gz file/dir snapshots in a state dir: sha256 tamper refusal, allowed-roots + root/NUL/absolute guards, execute-time target **and** archive containment re-validation (V5-4), root-guard Path fix (V5-5), symlink-excluded manifest digest (V5-6). |
| `app/infrastructure/recovery/hosts_recovery_adapter.py` | Hosts-file DNS recovery: byte-exact CRLF restore, hostname-scoped drift/conflict, hostname injection guard, payload write-redirection refusal, deleted-file → `REQUIRES_MANUAL_ACTION` (V5-2/V5-3). |
| `app/infrastructure/recovery/certification_probes.py` | Behavioral probes for environment/archive/hosts/config/filesystem (5 probes × 5–8 checks each) + `standard_behavioral_probes()` registry. |

### 1.2 Tests (all new, all green)

| File | Tests |
|---|---|
| `tests/unit/test_v5_adapter_registry.py` | 15 |
| `tests/unit/test_environment_recovery_adapter.py` | 15 |
| `tests/unit/test_archive_recovery_adapter.py` | 13 |
| `tests/unit/test_hosts_recovery_adapter.py` | 13 |
| `tests/unit/test_orchestrator_reliability.py` | 12 |
| `tests/unit/test_tenant_quota_service.py` | 19 (12 original + 7 `QuotaCounterStore` contract tests, gate run 2026-10-15) |
| `tests/unit/test_recovery_certification_lab.py` | 8 |
| `tests/performance/test_recovery_adapter_benchmark.py` | 8 |
| **Total new** | **103** (95 unit + 8 performance) — plus 12 git-adapter regression tests added to the pre-existing `tests/unit/test_git_repository_adapter.py` (§5) |

### 1.3 Documentation (this campaign)

`INTERLOCK_V5_RECOVERY_ENGINE_ROADMAP.md`,
`INTERLOCK_V5_ADAPTER_CAPABILITY_MATRIX.md`,
`INTERLOCK_V5_RECOVERY_CORRECTNESS_REPORT.md`,
`INTERLOCK_V5_SECURITY_AND_CONTAINMENT_REPORT.md`,
`INTERLOCK_V5_FAILURE_INJECTION_REPORT.md`,
`INTERLOCK_V5_BENCHMARK_REPORT.md`,
`INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md`,
`INTERLOCK_V5_IMPLEMENTATION_CHANGELOG.md` (this file).

## 2. MODIFIED PRODUCTION FILES

### 2.1 Baseline fixes (33 pre-existing failures — see correctness report §1)

| File | Change |
|---|---|
| `app/domain/services/authorization_service.py` | Resource allow-list: exact match first + `_check_resource_hierarchy` for patterns; previous-behavior matching loosened on empty resources; cross-tenant grants → DENY; `agent_history_required` fail-closed flag. |
| `app/domain/services/risk_engine.py` | `retry_after_failure` risk signal (+0.3). |
| `app/domain/value_objects/authorization_context.py` | Missing context fields for IP-range/session-age/concurrent-session checks. |
| `app/domain/services/independent_verification_service.py` | `verify_evidence`/`independent_verify` unified as `async`. |
| `app/domain/services/enterprise_recovery_platform.py` | Zero configured components → `FAILURE` (not recommendations). |
| `app/domain/services/self_healing_service.py` | `HealingEvent.resolved = healed`. |
| `app/infrastructure/observability/opentelemetry_integration.py` | OTel opt-in via `INTERLOCK_OTEL_ENABLED=1`; default = no-op. |
| `app/infrastructure/recovery/filesystem_recovery_adapter.py` | ACL rendering to SID strings; symlink checks via `lstat`/`lexists`. |
| `app/presentation/api/v1/routes/authority.py` | Grant-lineage route returns its result. |

### 2.2 V5 feature wiring

| File | Change |
|---|---|
| `app/domain/services/distributed_recovery_orchestrator.py` | **V5 reliability:** module-level `PlanLease`/`PlanLeaseStore`/`InMemoryPlanLeaseStore` (TTL, expiry takeover, monotonic fencing tokens with release tombstones — V5-11); constructor `lease_store`/`lease_ttl_seconds`; lease-based `execute_durable_plan` (replaces per-plan locks; result carries `fencing_token`); per-step lease renewal → `lease_lost` abort; **capability gating** (explicit-refusal verdicts cannot claim a step) with evidence-faithful action reconstruction (V5-10); drift gate admits `NO_DRIFT`/`INSUFFICIENT_EVIDENCE`. |
| `app/domain/services/recovery_planning_service.py` | Optional `quota_service`; `create_plan` daily/size check; `execute_plan` compensation slot (try/finally release). Legacy `_execute_with_protocol_adapters` behavior unchanged (gap G-5). |
| `app/presentation/api/v1/routes/surgical_recovery.py` | Module-level `quota_service = TenantQuotaService()`; `_get_recovery_service` injects it; create route: `QuotaExceededError` → 429; execute route: slot held around `execute_durable_plan` → 429 on exhaustion. |
| `app/domain/entities/surgical_recovery_types.py` | `RecoveryAdapterType` members `ENVIRONMENT`, `ARCHIVE`, `DNS_HOSTS` (+ related enums for new adapters). |
| `app/infrastructure/recovery/config_recovery_adapter.py` | (baseline) pre-existing fixes; **V5-8** capture honors `before_snapshot` param/`action.before_state_snapshot`; **V5-9** `_safe_config_path` execution-time containment in restore/delete/restore-deleted/verify. |

## 3. MODIFIED TEST FILES (reconciliations — assertions preserved)

| File | Change |
|---|---|
| `tests/unit/test_advanced_authorization.py` | `agent_history_required=True` added to the fail-closed test (flag introduction documented in correctness §2.1); test `MockGrantRepo.consume_one_shot` contract catch-up (+48 lines). |
| `tests/unit/test_domain_a_advanced_authorization.py` | Same `consume_one_shot` mock contract catch-up (+47). |
| `tests/unit/test_domain_i_verification.py` | 5 tests converted to `async` after service unification; assertions byte-identical. |
| `tests/unit/test_identity_compromise.py` | `_run` helper → `asyncio.run` (deprecated loop API). |
| `tests/integration/test_billing_extra_routes.py` | Settings fixture supplies required prod-validation fields; `pytest.raises` assertion unchanged. |
| `tests/unit/test_config_recovery_adapter.py` | New regression `test_payload_path_traversal_refused` (+32, additive). |
| `tests/stress/test_live_agent_recovery.py` | **V5-13 CWD-leak fix:** all three `os.chdir` sites wrapped in `try/finally` process-CWD restore (stress suite runs before unit in full-suite order; the leak broke every later relative-path test); new `test_cwd_restored_after_workspace_creation` regression (+11). No scenario logic changed. |

**Not touched:** `web/` deletions (user-owned), `interlock_projects/`,
`stash@{0}`, migrations, config files, any test weakening (no test was
deleted, skipped, xfailed, or had assertions relaxed).

## 4. OPERATIONAL NOTES

- Test command: `& ".\.venv\Scripts\python.exe" -m pytest <paths> -q
  --no-header --no-cov` (coverage gate `fail_under=80` skipped in dev runs;
  `--strict-markers` respected — no custom markers registered).
- New env var (behavior change): OTel now **off** unless
  `INTERLOCK_OTEL_ENABLED=1`.
- New HTTP semantics: recovery plan create/execute may return **429** with a
  quota message when a quota policy is registered (no policy → never 429).
- Drift semantics: `INSUFFICIENT_EVIDENCE` is now an *allowed* drift state at
  the orchestrator gate (documented; adapters still fail closed internally).

## 5. RELEASE-GATE RUN (2026-10-15 — final verification, hardening)

Regression-first fixes for 8 confirmed defects (full evidence in
`INTERLOCK_V5_CONFIRMED_DEFECT_REGISTER.md`; RED 12/12 → GREEN 43/43 →
neighbors 181/181 → full suite green):

| ID | Sev | File(s) | Fix |
|---|---|---|---|
| V5-14 | P1 | `distributed_recovery_orchestrator.py` | Per-instance default lease store made single-executor semantics vacuous → process-wide `_default_lease_store()` (double-checked locking, injectable). |
| V5-15 | P1 | `distributed_recovery_orchestrator.py` | `resume_plan` bypassed the lease → wrapper acquires/renews/releases; `_do_resume_plan` body; `lease_lost` at step boundaries; release in `finally`. |
| V5-16 | P1 | `git_repository_adapter.py` | Path escape on tampered payloads → `_resolve_payload_path` (rejects absolute/drive/root/NUL/`..`/symlink escapes) in all 4 `_execute_*` + `verify`; drift/conflict use `_resolve_resource_path`. |
| V5-17 | P1 | `distributed_recovery_orchestrator.py` | Execute-phase exceptions fell through to the next adapter (double compensation) → inner try/except → FAILED step; only pre-execution probing may skip. |
| V5-18 | P2 | `distributed_recovery_orchestrator.py` | `_verify_external_outcome` trusted first adapter → consults all; any-True; exceptions = no verdict. |
| V5-19 | P2 | `git_repository_adapter.py` | Rename over-claims → drift `INSUFFICIENT_EVIDENCE`, execute `REQUIRES_MANUAL_ACTION`, verify never self-certifies. |
| V5-20 | P2 | `git_repository_adapter.py` | Capture ignored `before_snapshot` → mirrors config/filesystem contract. |
| V5-21 | P1 (deploy) | `alembic/versions/67080f3cfec6_merge_*.py` | Dual alembic heads → no-op merge revision; `alembic heads` = one head. |

Additional gate hardening (2026-10-15):

- **`QuotaCounterStore` backend contract** extracted from
  `TenantQuotaService` (protocol + `InProcessQuotaCounterStore` + 7 shared
  contract tests; two services over one store share one quota domain —
  the wiring a future Redis/Postgres backend will use). G-2 row updated.
- **Dependencies:** `pyjwt 2.13.0 → 2.15.0`, `urllib3 2.7.0 → 2.8.0`
  (pip-audit fixable advisories); auth suites re-run green; semgrep's
  `~=2.13.0` dev-tool pin conflict documented (semgrep verified working).
  **Note:** `requirements*.txt` are gitignored local files
  (`.gitignore:70–71`, never tracked) — the bump lives in the local pins +
  venv only and cannot be committed without force-adding against repo policy.
- **Lint/type/security debt on V5 files:** ruff clean (0 findings across
  all V5-touched files); mypy 42 → 5 errors (all pre-existing, in files
  untouched at HEAD); bandit B202 + ruff S202 + semgrep ToB findings on the
  archive legacy branch suppressed with inline manual-review justification
  (re-scan clean); semgrep baseline run: 43 findings → 42 pre-existing
  after the V5 suppression.
- New docs: `INTERLOCK_V5_EXTERNAL_VALIDATION_RUNBOOK.md`,
  `INTERLOCK_V5_CONFIRMED_DEFECT_REGISTER.md`,
  `INTERLOCK_V5_SECURITY_REVIEW_SUMMARY.md`,
  `INTERLOCK_V5_PROPOSED_COMMIT_MANIFEST.md`; gap matrix +G-14..G-18.
- Test-count reconciliation: 2719 pre-gate → +12 git regression → +7 quota
  contract → **final suite verified at 2738 passed / 7 skipped / 0 failed**
  (see `INTERLOCK_V5_TEST_EVIDENCE_REPORT.md` §5).
