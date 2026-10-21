# INTERLOCK V6 — PHASE 1 BASELINE (READ-ONLY) & RANKED REMEDIATION PLAN

**Mission:** World-Class Recovery Engine Mission (Phases 1–8, evidence-driven)
**Date:** 2026-10-17
**Repository:** `F:\Desktop_Data_2026\Desktop\INTERLOCK V4` · branch `master`
**Nature:** Read-only baseline inspection. No code changes, no staging/commits/pushes, no
threshold/marker/config changes, no deletions. This document is new and untracked
(the only git-state delta from this phase).

---

## A. Baseline and repository preservation verification (re-inspected this phase)

| Check | Value | Status |
|---|---|---|
| `git rev-parse --short HEAD` | `145a3d9` (matches previously reported) | ✓ |
| Staged changes | 0 | ✓ |
| Porcelain entries | 188 (pre-existing modified/untracked) | ✓ preserved |
| `web/` deletions | 60 (never restored/recreated) | ✓ |
| Stash | 1 (`stash@{0}` intact) | ✓ |
| Campaign files tracked by git | 0 (`logs/v6_recovery_campaign_100k/` git-ignored) | ✓ |
| Destructive commands used | none (no reset/clean/restore/checkout) | ✓ |
| Prior evidence (selftest runs, aborted manifests, failed-run logs) | intact, none overwritten | ✓ |

## B. Reconciled previous campaign results — INDEPENDENT VERIFICATION (this phase)

Method: read-only script (`%TEMP%\opencode\v6_m8_lab\reconcile_100k.py`) parsed **all raw
JSONL records** under `runs/full_20261017_072128/batches/` (200 files) directly — not the
manifest, not any prior report.

| Outcome | Reported | **Derived from raw records** | Match |
|---|---|---|---|
| recovered | 59,958 | **59,958** | ✓ |
| expected_refusal | 29,577 | **29,577** | ✓ |
| expected_failure_detected | 10,222 | **10,222** | ✓ |
| unexpected_failure | 243 | **243** | ✓ |
| invariant_violation | 0 | **0** | ✓ |
| unsupported | 0 | **0** | ✓ |
| **Sum** | **100,000** | **100,000** | ✓ |

Structural integrity verified from raw records:
- 200 batch files × exactly 500 records = 100,000; **100,000 unique attempt IDs, 0 duplicates,
  0 malformed JSON lines**; all 12 family totals == allocation exactly
  (filesystem 20,000 · config 15,000 · database 12,000 · environment 10,000 · archive 10,000 ·
  hosts 8,000 · git 8,000 · orchestrator 7,000 · fault_matrix 5,000 · containment 3,000 ·
  backup_restore 1,500 · certification 500).
- **All 243 unexpected records provenance-checked individually:** every one has
  `variant=ws_inside_ok`, `expected=recovered`, identical detail
  (`PathSecurityError: Path is outside workspace: nested/ok.txt (resolved: …\INTERLOCK V4\nested\ok.txt)`),
  in batches 190–193 (global_index 95021–96994). This is the documented relative-path
  harness-calibration defect, **not** a product recovery failure.
- Family×outcome cross-tab matches the manifest counts exactly; no outcome was reclassified.
- Final manifest: `planned=100000, completed=100000, exit_code=2,
  exit_reason=completed_with_failures, expectation_mismatches=243` — exit 2 is fully
  accounted for by the 243 preserved records.

**Conclusion: prior campaign report is CONFIRMED correct against raw evidence.**

## C. Test baseline (existing tests and current failures)

- **Collection: 2,867 tests** (188 `test_*.py` files; unit 119 · integration 33+4 ·
  performance 5 · stress 2 · support/misc remainder).
- **Controlled rerun #3** (fresh `--basetemp` outside repo, single run, no repeat-until-green):
  **3 failed / 2,857 passed / 7 skipped, 0 errors**, exit 1, 2,486.7 s,
  coverage **83.57% ≥ 80% floor** (branch coverage on), basetemp alive at end.
  Evidence: `%TEMP%\opencode\v6_s4_lab\v6_s4_pytest_run3.log` + `_meta.txt`.
- **Failures are latency-budget only** (`tests/performance/test_recovery_adapter_benchmark.py`):
  env p95 **1.872 ms / 1.0** · hosts **9.233 / 4.0** · fs-compensate **34.024 / 25.0**.
  Uniform 7–15× inflation vs 10/14 historical baselines with functionals never failing;
  confound recorded (light file edits overlapped the window).
- **Isolated benchmark (run once): 8/8 latency tests PASS** in 15.40 s —
  FAIL-in-suite / PASS-isolated; thresholds unchanged; no idle-window rerun performed
  (scheduling approval required).
- 7 skips: Windows-symlink privilege (1), platform-specific perf thresholds (5),
  key-manager absence (1) — all legitimate environmental skips.
- Coverage methodology: `pytest-cov` branch coverage, `fail_under=80`, `term-missing` + XML,
  measured in the controlled run (not inferred).

## D. Recovery capability inventory

`logs/v6_recovery_campaign_100k/CAPABILITY_MATRIX.md` (SUPPORTED/PARTIAL/UNSUPPORTED/
BLOCKED/NOT TESTED with file:line evidence, mapped to campaign families). Highlights:
- **SUPPORTED:** file/config/archive/hosts/git-content/env/db-row compensation, durable
  checkpoint resume, idempotent replay, leases/fencing (in-process), quotas, retry bounds,
  backup→destroy→restore→verify with 4-layer tamper detection, path-traversal/symlink/
  archive containment, secret redaction, unsafe-recovery refusal, honest audit statuses.
- **PARTIAL:** multi-file compensation (no unified patch engine), rename recovery (canned
  manual action, honesty-gated), cancellation (in-process simulated), alembic (no in-suite
  tests), leases (unit-level; no multi-process campaign), deterministic gauntlet (single-seed).
- **UNSUPPORTED (explicit non-claims):** syntax/import/type/test/dependency repair,
  patch (unified-diff) application, merge/rebase conflict resolution, lock-file restoration.
- **NOT TESTED:** real process-kill, real network partition, real disk-full/torn-write,
  clock-skew, live PostgreSQL. **BLOCKED:** live PG/Redis/Docker (no local infra), CI (never run).

## E. Known security and dependency findings (dated evidence, re-verified this phase)

- bandit `-r app -ll` exit 0 (7 Low findings accepted, gap #12); semgrep 3 packs
  **11 WARNING / 0 ERROR** (gap #13, advisory-tier, Django-rule false positives characterized).
- pip-audit **0 vulns / 110 SBOM components** after standard toolchain upgrade
  (bootstrap pip/setuptools CVEs remediated by upgrade, not `--ignore-vuln`).
- Accepted runtime-lock advisories without upstream fix: `ecdsa` PYSEC-2026-1325,
  `python-jose` PYSEC-2026-4298 (absent from supported install path; gap #11).
- `mcp` CVE-2026-59951 removed from install path by R-PKG v2 (gap #2 FIXED).

## F. Missing integration and operational evidence

1. **CI has never run** (no push authorization; workflows target `main`/`develop`, repo is `master`).
2. **Docker / PostgreSQL / Redis unverified** (CLI absent; ports 5432/6379 closed).
3. **`alembic check` fails (D3 drift, 33 ops)** until M-PKG applied (pending approval).
4. Real process-kill / network / disk-full / clock-skew / live-PG fault classes (above).
5. No independent pentest/compliance assessment; performance evidence is single-machine.
6. Wheel/sdist install → migrate → boot **is** verified locally (G9 closed this phase).

## G. Documented limitations and release blockers (unchanged)

- G6 `PENDING APPROVAL` (M-PKG + downgrade guard) · G7/G11 `BLOCKED EXTERNALLY` (CI, infra) ·
  latency exception open · two separate push authorizations ungranted · publication blocked.
- Product findings recorded (not defects to hide): `WorkspacePathSecurity.validate` resolves
  **relative** paths against process CWD (suite exercises absolute paths only);
  `MockRecoveryAdapter.verify` always `verified=False` → orchestrator correctly emits
  `EXECUTED_NOT_VERIFIED` (honesty demonstration).

---

## RANKED REMEDIATION PLAN (Phase 8 gate — review before implementation)

Priority: **P0** = blocks safe recovery of genuinely recoverable states / safety exposure ·
**P1** = blocks a release gate or evaluation · **P2** = correctness/robustness with constrained
trigger · **P3** = honesty/test-quality debt. Each entry: affected files · evidence · risk ·
test plan. Only small, evidence-backed fixes within existing authorization are proposed;
major architectural changes are marked **APPROVAL REQUIRED** and will not be started.

| # | Pri | Defect / gap | Affected files | Evidence | Risk of fix | Test plan |
|---|---|---|---|---|---|---|
| R1 | P1 | `WorkspacePathSecurity.validate` resolves **relative** paths against process CWD → false rejection (fail-safe direction) whenever CWD ≠ workspace root; produced 553 harness-calibration unexpected records across both campaign legs | `sdk/workspace_protection/path_security.py:41-85` | 243 preserved raw records (batches 190–193) + 310 run-1 records, all `ws_inside_ok`; 91% file coverage misses lines 64–65 (the resolve-failure path) | Low: relative input currently *fails* outside-CWD; anchoring to workspace root can only convert false-rejects to correct accepts; containment check (line 70) still enforced after resolve | New unit tests: relative path inside workspace accepted regardless of CWD; `../escape` relative still refused; absolute-path behavior byte-identical; run `tests/integration/test_workspace_protection/` + containment campaign family regression |
| R2 | P1 | Latency budget failures (3) unresolved — suite FAIL / isolated PASS; root cause not isolated (load vs regression) | `tests/performance/test_recovery_adapter_benchmark.py` (measurement only; **thresholds frozen**) | run#3 log (p95 7–15× inflation, functionals never fail) vs isolated 8/8 | N/A — no code change proposed; **idle-window full-suite rerun requires scheduling approval** (not performed) | Approved idle rerun must reproduce 8/8 in-suite; until then exception stays disclosed |
| R3 | P2 | Missing **direct adapter tests** for `FileVersion`, `DatabaseRecord`, `ConfigRollback` capability rows | new `tests/unit/test_<adapter>_capability.py` files (test-only) | capability matrix §G/§A rows cite no direct tests | None (test-only; no product code, no thresholds) | RED-first: each test must fail to find coverage pre-file; run unit suite |
| R4 | P2 | V5-D2: `resume_plan(stop_conditions=None)` continues past failures while execute defaults stop-on-first-failure | `app/…/distributed_recovery_orchestrator.py` (default only) | V5 register documented, no production caller hits `None` | Behavior change of a documented default → **APPROVAL REQUIRED** before changing | RED/GREEN default-alignment tests + API-route condition tests |
| R5 | P2 | V5-D3: `verify_evidence_integrity` does field-presence checks only — never recomputes `evidence_hash` | evidence store + `independent_verification_service` | V5 register (schema-contract dependency) | Evidence-schema contract change → **APPROVAL REQUIRED** (versioned hash spec) | Tamper-one-field → hash mismatch refusal tests |
| R6 | P3 | No in-suite **alembic migration tests** (fresh upgrade / drift / downgrade guard) | new `tests/integration/test_alembic_migration_safety.py` (disposable sqlite DB only) | gap register #1; suite has zero alembic coverage | None if restricted to disposable DBs; must not touch M-PKG or production | Fresh-DB `upgrade head` + `check`-expected-state test; M-PKG-dependent assertion marked `xfail`-style *until approved* (no threshold weakening) |
| R7 | P3 | V5-D4/D5: ambiguous topological placement (order 0); `list_by_plan` truncates >500 steps | durable plan repository | V5 register (no failing flow observed) | Policy decisions → needs product decision (documented) | Property test: plan with 501 steps fully listed; ordering policy test |
| R8 | P3 | Legacy `execute_recovery` returns canned `SUCCEEDED` without effect | git/fs legacy paths | capability matrix §J PARTIAL | Removing/rewiring a public method = **APPROVAL REQUIRED** (larger change) | Honesty tests already assert current contract; new contract tests if approved |
| R9 | — | CI / Docker / PG / Redis / M-PKG / push / production | external | gates G6/G7/G11 | **BLOCKED EXTERNALLY / PENDING APPROVAL** — no action possible here | CI green on authorized push; docker-verify green; PG migration suite |

**Not proposed (explicitly):** no universal-repair capability work (syntax/type/dependency/
patch/merge engines) without separate approval as major new capabilities; no threshold,
marker, or config edits; no re-run of historical campaign attempts; no erasure of any
failed/aborted evidence.

## Priority-ordered execution proposal

1. **R1** (smallest, highest-yield correctness fix + regression tests) → 2. **R3** and
**R6** (test-only additions) → 3. present **R4/R5/R8** as approval-gated change proposals →
4. Phase 2 property-by-property architecture assessment (read-only) → 5. Phase 4 frozen
Suite A/B manifests + acceptance criteria **presented for review before any new campaign**
(per Phase 8: no new 100k campaign prior to review).

---

## EXECUTION STATUS (end of Phase 1–8 execution pass, 2026-10-17)

| Item | Status | Evidence |
|---|---|---|
| R1 path-anchoring fix | **DONE** | RED reproduced exact campaign defect → 8-line fix → 33 passed/1 skipped (dir) · live-agent 23 passed (364.9s) · experiment 5 passed · full unit suite **2390 passed / 1 skipped / 0 failed** · `%TEMP%\opencode\v6_m8_lab\r1_evidence.md` |
| R3 reference adapter tests | **DONE (test-only)** | `tests/unit/test_reference_adapter_contracts.py` 26 passed |
| R6 alembic safety tests | **DONE (test-only)** | `tests/integration/test_alembic_migration_safety.py` 4 passed + 2 xfailed (both defects visible) |
| **D-MIG-1 (new, found by R6)** | **CONFIRMED → R10 proposal** | `downgrade base` impossible even on empty DB; `3cebbede5768.downgrade()==pass` after dropping 8 tables; xfail documents it |
| R4/R5/R8/R10 | **PROPOSED — awaiting approval** | `%TEMP%\opencode\v6_m8_lab\approval_gated_proposals.md` |
| Phase 2 14-property assessment | **DONE** | `%TEMP%\opencode\v6_m8_lab\phase2_property_assessment.md` — 0 GAP, 5 NARROW (props 1/6/8/10/14), 4 PARTIAL-TESTS (5/9/11/12) |
| Phase 4 frozen suites | **DESIGNED, NOT EXECUTED (review gate)** | `logs/v6_frozen_benchmark_v1/` — Suite A 26 scenarios/100,000 attempts sha256 `dc74ebd2…`; Suite B 31 scenarios/31,000 attempts sha256 `da45c22c…`; `BENCHMARK_DESIGN.md` incl. Phase 7 comparative protocol (no competitor results claimed) |
| Phase 5 property tests | **DONE (dependency-free)** | `tests/integration/test_workspace_protection/test_path_security_properties.py` 5 passed (500-path seeded adversarial sweep + refused-op zero-side-effect property); `hypothesis` NOT added (would need approval) |
| Phase 6 checklist | **DONE** | `%TEMP%\opencode\v6_m8_lab\phase6_checklist.md` — 14 rows: 8 PASS, 3 PARTIAL/PENDING, 2 BLOCKED EXTERNALLY, 1 NOT TESTED |
| Static quality | **CLEAN** | ruff exit 0 on all new/changed files (2 inline noqa on trusted subprocess argv, 2 on seeded RNG); mypy exit 0 on path_security.py |

New Phase-2-derived backlog (NOT implemented; needs review/approval as they are
executor-layer behavior changes): R11 `restore_backup` non-atomic `shutil.copyfile` →
temp+rename; R12 general secret-redaction pass over audit details (`audit_logger.py:67`
writes caller details verbatim); R13 plan/step deadlines + backoff + mid-plan
cancellation; R14 restore-time compatibility validation (`manifest_version`/`dump_version`/
`hash_spec` unread); R15 executor-layer bounds (per-adapter concurrency limit; circuit
breaker into recovery path; default-on quota); R16 measured false-alarm budget.

---

## CONTINUOUS ENGINEERING EXCELLENCE MISSION — session 1 (2026-10-17) additions

| Item | Status | Evidence |
|---|---|---|
| Porcelain 194→195 discrepancy | **RESOLVED** | The +1 was `INTERLOCK_V6_WORLD_CLASS_MISSION_FINAL_REPORT.md`, written after the 194 measurement; every entry since accounted (see engineering log) |
| D-MIG-1 investigation | **ESCALATED → D-MIG-1b** | Two disposable repros (`%TEMP%\opencode\v6_m8_lab\d_mig1_repro.py`, `d_mig1_booted_roundtrip.py`): failed downgrade leaves DB bricked BOTH directions (`duplicate column name: after_state_snapshot` on re-upgrade); booted DBs still brick (unique-index name mismatch). Proposal: `r10_d_mig1_repair_proposal.md` |
| R10 | **PROPOSAL WRITTEN — approval-gated** | as above; historical migration untouched |
| R11 restore atomicity | **DONE** | verify-before-swap + `os.replace`; RED (pre-fix body) showed healthy DB overwritten; GREEN byte-identical; drill suite 8 passed |
| R14 restore compatibility gates | **DONE** | manifest/dump/hash-spec fail-closed gates; +2 tests; drill 8 passed exit 0 |
| R12 audit redaction | **DONE** | recursive key+Bearer masking before write/hash; RED via real HEAD module leaked, GREEN masked; 56 passed across 5 audit suites |
| D-MIG-1b regression | **DONE (xfail, visible)** | `test_failed_downgrade_must_not_brick_reupgrade`; alembic suite 4 passed + 3 xfailed exit 0 |
| Suite A/B manifest review | **VERIFIED (design)** | sha256 both match `MANIFESTS.sha256`; sums 100,000/31,000 exact; 0 dup IDs; all required fields incl. independent verification present; refusal-never-recovery rule embedded; still NOT EXECUTED (review gate) |
| Customer pilot | **DEMO EXECUTED, exit 0** | `scripts/pilot_demo_v1.py` 4/4 legs harness-verified (3/3 byte-exact, traversal refused+sentinel intact, human edit preserved via conflict, idempotent replay no double-apply); plan `INTERLOCK_V6_PILOT_PLAN.md` |
| R4/R5/R8/R13/R15/R16 | **approval-gated** (ranked in engineering log) | backlog ranking by safety/correctness/production risk |
