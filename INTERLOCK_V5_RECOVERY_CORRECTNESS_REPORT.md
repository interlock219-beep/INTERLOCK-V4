# INTERLOCK V5 — RECOVERY CORRECTNESS REPORT

**Date:** 2026-10-14
**Repository:** F:\Desktop_Data_2026\Desktop\INTERLOCK V4
**Baseline log:** `$env:TEMP\baseline_tests.txt` (unit + integration, 2572 tests)
**Method:** reproduce with a failing test → root cause → fix → regression test →
focused + related suites re-run.

---

## 1. BASELINE CAMPAIGN — 33 PRE-EXISTING FAILURES (ALL FIXED)

The baseline run (`tests/unit` + `tests/integration`) failed **33 tests**,
pre-existing against commit `c738c44` before any V5 work. Every failure was
reproduced, root-caused, fixed, and re-verified. Exact baseline list:

| Test file | Count | Root cause | Fix (production unless noted) | Verification |
|---|---|---|---|---|
| `test_advanced_authorization.py` | 12 | Resource allow-list matched patterns as literals; previous-behavior matching too strict on empty resources; cross-tenant grants not denied; missing `retry_after_failure` risk signal; one-shot consumption contract absent in test double; empty-history fail-closed policy conflict | Allow-list: exact match first, pattern entries resolved via `_check_resource_hierarchy`; previous-behavior match loosened when either resource is empty; cross-tenant grants → DENY; `retry_after_failure` risk signal (0.3) added to risk engine; empty-history deny gated on new `agent_history_required` flag; test `MockGrantRepo` gained `consume_one_shot` mirroring the production repository contract (test catch-up) | advanced-auth cluster 139/139 |
| `test_domain_a_advanced_authorization.py` | 1 | Test double lacked production `consume_one_shot` contract | `MockGrantRepo.consume_one_shot` added to test (contract catch-up, assertions unchanged) | cluster above |
| `test_enterprise_recovery_platform.py` | 1 | Enterprise platform with zero components returned recommendations instead of failing | Zero configured components → **FAILURE** | enterprise/identity cluster green |
| `test_filesystem_recovery_adapter.py` | 1 | Windows ACLs rendered as objects instead of SID strings; symlink checks used `stat` instead of `lstat`/`lexists` | ACL rendering fixed to SID strings; symlink handling uses `lstat`/`lexists` | filesystem suite 20/20 |
| `test_identity_compromise.py` | 4 | Test helper used deprecated `asyncio.get_event_loop().run_until_complete` (raises on Python 3.11+) | Test helper `_run` → `asyncio.run` (assertions unchanged) | cluster green |
| `test_independent_verification_service.py` | 5 | `verify_evidence`/`independent_verify` sync/async unification mismatch | Service methods made `async` consistently | verification cluster green |
| `test_opentelemetry_integration.py` | 5 | OTel integration enabled by default without packages present | OTel **opt-in** via `INTERLOCK_OTEL_ENABLED=1`; default = no-op paths | 5/5 without modification |
| `test_self_healing_service.py` | 1 | `HealingEvent.resolved` never set from `healed` | `resolved = healed` | cluster green |
| `test_surgical_recovery_pipeline.py` | 1 | Live filesystem action through the production adapter hit the ACL/symlink defects above | Same filesystem fixes (SID/`lstat`) | surgical suite 41/41 |
| `test_authority_routes.py` | 1 | Grant-lineage route built a result but never returned it | `return result` added to lineage route | 18/18 |
| `test_billing_extra_routes.py` | 1 | Production-mode `Settings` validation requires explicit secrets the test omitted | Test fixture supplies required prod-validation fields (exercises the same credential path; assertion unchanged) | 10/10 |

**Result: 33/33 baseline failures fixed; zero unexplained failures remain
in the baseline scope.**

## 2. SPEC RECONCILIATIONS (HONEST RECORD)

Four fixes changed a test rather than production behavior. Each is a
reconciliation of contradictory specifications, not a weakened assertion:

1. **`test_previous_behavior_unknown_history_fails_closed`** — this test
   demanded DENY on empty agent history, but **8+ passing tests** depend on
   empty history being allowed by default. Resolution: production gained the
   `agent_history_required` flag (default off = previous behavior); the
   fail-closed test now sets `agent_history_required=True` and still asserts
   `DENY`. Both behaviors are exercised; no assertion was removed.
2. **`test_domain_i_verification.py` (5 tests)** — converted to `async def` +
   `await` after `verify_evidence`/`independent_verify` were unified as async.
   Assertions are byte-for-byte unchanged.
3. **Test mock repository contracts** (`MockGrantRepo.consume_one_shot` in two
   files) — test doubles caught up to the existing production repository
   interface; production was not changed for these.
4. **Billing Settings fixture** — added required production-validation fields
   so the test reaches its intended code path; the `pytest.raises(ValueError,
   match="Stripe credentials")` assertion is unchanged.

## 3. V5 DEFECT REGISTER (FOUND AND FIXED DURING V5 IMPLEMENTATION)

Each item was found by writing/running V5 tests or probes first.

| # | Defect | Reproduced by | Root cause | Fix | Regression |
|---|---|---|---|---|---|
| V5-1 | New adapters' `detect_drift` compared only the before-state → every legitimate post-action state read `DRIFT_DETECTED`, blocking orchestrator compensation | Drift-contract tests in env/archive/hosts test files | Wrong drift semantics vs orchestrator gate | Canonical contract: before-match → `NO_DRIFT`; recorded-after match → `NO_DRIFT`; after recorded + third state → `DRIFT_DETECTED`; no after recorded → `INSUFFICIENT_EVIDENCE` (allowed through) | drift tests in all three adapter suites; reliability suite |
| V5-2 | Hosts adapter returned `RESOURCE_MISSING` conflict on a deleted hosts file, blocking the manual-intervention path | `test_deleted_hosts_file_requires_manual_intervention` | Missing-file conflict branch too aggressive without an after-state | No after recorded → `NO_CONFLICT` (execution still fails closed to `REQUIRES_MANUAL_ACTION`) | hosts suite 13/13 |
| V5-3 | Hosts `execute_compensation` returned generic `FAILED` for a deleted file, implying a partial file could be fabricated | same test | Message/state implied wrong recovery model | Explicit `REQUIRES_MANUAL_ACTION`: never fabricate a hosts file missing unrecorded entries | hosts suite |
| V5-4 | Archive compensation trusted payload `target_path`/`archive_path` (redirectable write) | `test_target_path_redirection_refused`, `test_archive_path_redirection_refused` | No execute-time containment re-validation | `_restore_archive` re-validates archive ∈ state-dir and target ∈ allowed-roots before any I/O | archive suite 13/13 |
| V5-5 | Archive root guard never fired: `resolved == resolved.anchor` compared `Path` to `str` (always False) | `test_path_guards_reject_bad_targets` | Type mismatch in guard | `resolved == Path(resolved.anchor)` | archive suite |
| V5-6 | Directory manifest digest included symlink markers but restore skips symlinks → verification could never round-trip on trees with symlinks | archive directory round-trip test | Digest mixed restorable and non-restorable content | Manifest covers restorable content only; symlinks counted in `skipped` | archive suite |
| V5-7 | Environment capture read variables outside `allowed_prefixes` (deny-by-default gap) | `test_allowed_prefixes_deny_by_default` | Capture bypassed `_allowed()` | Capture refuses out-of-prefix vars (`ValueError`); `verify` reads through prefix-guarded `_read_value` | env suite 15/15 |
| V5-8 | Config capture silently discarded the supplied `before_snapshot` parameter, making post-action evidence capture impossible (before==after==live) | config probe (`content_restore_round_trip`) | `before_snapshot = None` reset overwrote the parameter | Honor parameter/`action.before_state_snapshot` (filesystem-adapter semantics); fallback unchanged when not supplied | config suites 41/41 + new traversal test |
| V5-9 | Config execute/verify wrote through payload `config_file` uncontained (`../victim.yaml` escape) | `test_payload_path_traversal_refused` | No payload-path containment at execute | `_safe_config_path`: NUL/absolute/drive/`..` rejection + resolve-time containment inside config dir; execute → `FAILED`, verify → `verified=False` | config suites 50/50 |
| V5-10 | Orchestrator rebuilt a bare `ProtectedAction` from the step (no evidence refs) → adapter capability checks saw `unknown`; naive `supports()` gating then skipped legitimate adapters | 4 `test_distributed_recovery` failures under gating | Lost reversibility context + over-strict gating | Step action enriched with `action_type`/`before_state_ref` from evidence; gating on **explicit refusal** verdicts (`unsupported`/`irreversible`/`requires_approval`) only — `unknown` stays eligible and fails closed inside the adapter | `test_distributed_recovery.py` 14/14 + reliability 12/12 |
| V5-11 | First in-memory lease implementation deleted leases on release → fencing tokens could repeat for a plan | `test_lease_store_acquire_conflict_and_release` | Tombstone needed for monotonic tokens | Release keeps an expired ownerless tombstone; `get()` reports released as None | reliability suite 12/12 |
| V5-12 | Certification lab crashed on a probe infrastructure exception instead of reporting failure | `test_crashing_probe_is_reported_as_failure` | Unhandled `probe_fn` exception in `certify()` | Converted to a failed `probe_infrastructure` probe result — never claimed as pass | lab suite 8/8 |
| V5-13 | Full-suite run failed `test_central_policy_engine::test_from_file_loads_valid_policy` (ALLOW instead of DENY) + `test_coverage_gaps` skipped — **only** when stress and unit suites share one pytest process (pre-existing, first surfaced by the first-ever full-suite run; the unit-only sweep could not see it) | Deterministic 4 s repro: stress `test_phase1_disposable_workspace` + the unit test in one invocation | Stress suite leaked the process CWD (`os.chdir` into the temp workspace in `_create_workspace`/phase1/phase10, never restored) → later relative paths (`config/policies.yaml`) resolved against a dead workspace → `from_file` silently loaded an **empty** engine whose fail-open ALLOW default is pinned by `test_from_file_missing_file_returns_empty_engine` (kept as tested spec — the leak was the defect, not the semantic) | All three `os.chdir` sites wrapped in `try/finally` CWD restore; new regression `test_cwd_restored_after_workspace_creation` | stress suite rerun + authoritative full-suite rerun |

### 3.1 Release-gate findings (2026-10-15 independent verification)

Found by re-reading V5 code against its own contracts (not by test failure);
each got a regression-first fix (RED 12/12 → GREEN 43/43 → neighbors 181/181).
Full detail: `INTERLOCK_V5_CONFIRMED_DEFECT_REGISTER.md`.

| # | Defect | Root cause | Fix | Regression |
|---|---|---|---|---|
| V5-14 | Default lease store was created **per orchestrator instance** → two "single-executor" instances never contended (fencing/lease semantics vacuous) | Module default rebuilt on each construction | Process-wide `_default_lease_store()` (double-checked locking), constructor-injectable | `test_orchestrator_reliability.py` |
| V5-15 | `resume_plan` executed without acquiring the lease (bypassed every lease guard) | Resume path predates the lease wiring | Wrapper acquires/renews/releases; `_do_resume_plan` body; `lease_lost` at step boundaries; release in `finally` | `test_orchestrator_reliability.py` |
| V5-16 | Git adapter joined payload-relative paths uncontained → absolute/`..`/drive/symlink payloads escaped the workspace during compensation | No payload-path containment at execute/verify | `_resolve_payload_path` (rejects absolute/drive/root/NUL/`..`/symlink escapes) in all 4 `_execute_*` + `verify`; drift/conflict raise via `_resolve_resource_path` | `test_git_repository_adapter.py` |
| V5-17 | Exception **during** an adapter's execute/verify fell through to the next adapter → double compensation possible | Only pre-execution probing was guarded | Inner try/except around execute+verify+result handling → FAILED step; only pre-execution probing may skip | `test_orchestrator_reliability.py` |
| V5-18 | `_verify_external_outcome` trusted the **first** adapter's verdict (others ignored) | Single-adapter loop with early return | Consult all registered verifiers; any-True; exception = no verdict | `test_orchestrator_reliability.py` |
| V5-19 | Git rename over-claimed recovery: drift claimed `NO_DRIFT`, execute claimed success, verify self-certified | Rename detection heuristics treated partial evidence as proof | Drift → `INSUFFICIENT_EVIDENCE`; execute → `REQUIRES_MANUAL_ACTION`; verify never self-certifies | `test_git_repository_adapter.py` |
| V5-20 | Git capture ignored `before_snapshot` → before==after==live (same class as V5-8) | Parameter dropped | Mirrors config/filesystem contract: `before_snapshot or action.before_state_snapshot`; live file = after | `test_git_repository_adapter.py` |
| V5-21 | Alembic had **two heads** (migration deploy would fail) | Two independent revisions without a merge | No-op merge revision `67080f3cfec6` (only new migration file); `alembic heads` = 1 | `alembic heads` verified |

## 4. VERIFICATION MATRIX (V5 FINAL)

| Suite | Result |
|---|---|
| Baseline failures (33) individually re-verified | all pass |
| `tests/unit/test_v5_adapter_registry.py` | 15/15 |
| `tests/unit/test_environment_recovery_adapter.py` | 15/15 |
| `tests/unit/test_archive_recovery_adapter.py` | 13/13 |
| `tests/unit/test_hosts_recovery_adapter.py` | 13/13 |
| `tests/unit/test_orchestrator_reliability.py` | 12/12 |
| `tests/unit/test_tenant_quota_service.py` | 19/19 (12 original + 7 contract tests, gate run) |
| `tests/unit/test_recovery_certification_lab.py` | 8/8 |
| `tests/performance/test_recovery_adapter_benchmark.py` | 8/8 |
| `tests/unit/test_distributed_recovery.py` (existing) | 14/14 |
| `tests/unit/test_surgical_recovery_pipeline.py` + `tests/integration/test_surgical_recovery_routes.py` | 41/41 |
| config suites (existing + new traversal test) | 50/50 |
| `tests/unit tests/integration` (full scope, one process) | **2659 passed, 2 skipped, 0 failed** (15m53s) |
| `tests/stress` (incl. new V5-13 CWD regression) | **45 passed, 0 failed** (22m22s) |
| **Full suite `tests` (all directories, authoritative)** | **2719 passed, 7 skipped, 0 failed** (38m29s) — 7 skips environment-bound: 5 platform-specific performance thresholds, symlink admin privilege, key manager unavailable |

**Release-gate re-verification (2026-10-15):**

| Suite | Result |
|---|---|
| Pre-fix full suite (claim reproduced before any gate fix) | **2719 passed, 7 skipped, 0 failed** (17m21s) |
| New git-adapter regressions (RED, defects un-fixed) | 12 failed / 31 passed as expected |
| After the 8 gate fixes (GREEN) | **43 passed, 0 failed** |
| Neighbor sweep | **181 passed, 0 failed** |
| Post-fix full suite | **2731 passed, 7 skipped, 0 failed**, exit 0 (16m58s) |
| Targeted batch (dependencies + touched areas, incl. auth under pyjwt 2.15.0) | **351 passed, 0 failed** (43s) |
| **Final gate suite (authoritative)** | **2738 passed, 7 skipped, 0 failed**, exit 0 (16m47s) = 2731 + 7 quota-contract tests exactly |

## 5. DRIFT/CONFLICT SEMANTICS — WHY `INSUFFICIENT_EVIDENCE` PASSES

The orchestrator gate admits `NO_DRIFT` and `INSUFFICIENT_EVIDENCE` and blocks
everything else. If no after-state was recorded in evidence, a deviation from
the before-state cannot be distinguished from the protected action's own
effect. Returning `DRIFT_DETECTED` there would block **every** legitimate
post-action compensation; returning `NO_DRIFT` would overstate certainty.
`INSUFFICIENT_EVIDENCE` is the honest classification: the orchestrator
proceeds, and the adapter's authorization, idempotency, and conflict gates
still decide the outcome. When an after-state *is* recorded, deviations are
classified strictly (`DRIFT_DETECTED`).
