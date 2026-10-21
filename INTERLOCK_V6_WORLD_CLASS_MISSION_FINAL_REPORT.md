# INTERLOCK V6 — WORLD-CLASS RECOVERY ENGINE MISSION: FINAL REPORT

**Date:** 2026-10-17 · **Repo:** `F:\Desktop_Data_2026\Desktop\INTERLOCK V4` · branch `master` · HEAD `145a3d9`
**Nature:** Evidence-driven reliability mission (Phases 1–8). No staging/commit/push/tag/publish/deploy, no remotes, no production, no M-PKG application, no threshold/marker/config changes to manufacture passes, no evidence deletion. New files: 4 untracked (1 report + 3 test files) + 2 modified files (1 product fix + its test) — all disclosed in §A/§D.

---

## A. Baseline and repository preservation verification

| Check | Baseline (mission start) | End of mission | Status |
|---|---|---|---|
| HEAD | `145a3d9` | `145a3d9` | **PASS** |
| Staged | 0 | 0 | **PASS** |
| Porcelain | 188 | 194 (= 188 + 4 new untracked + 2 R1-modified) | **PASS** (deltas are mine, listed in §D) |
| `web/` deletions | 60 | 60 | **PASS** |
| Stash | `stash@{0}` intact | intact | **PASS** |
| Campaign/benchmark artifacts tracked | 0 | 0 (`logs/v6_recovery_campaign_100k/`, `logs/v6_frozen_benchmark_v1/` git-ignored) | **PASS** |
| Destructive commands | none | none (no reset/clean/restore/checkout/stash-drop) | **PASS** |
| Root `.env` | untouched | untouched (alembic tests used env-var override on disposable DBs) | **PASS** |

## B. Reconciled previous campaign results — INDEPENDENT VERIFICATION

Read-only script parsed **all 100,000 raw JSONL records** (200 batch files) directly — not the manifest, not any prior report:

| Outcome | Reported | Derived from raw records | Match |
|---|---|---|---|
| recovered | 59,958 | **59,958** | ✓ |
| expected_refusal | 29,577 | **29,577** | ✓ |
| expected_failure_detected | 10,222 | **10,222** | ✓ |
| unexpected_failure | 243 | **243** | ✓ |
| invariant_violation / unsupported | 0 / 0 | **0 / 0** | ✓ |
| **Sum** | **100,000** | **100,000** | ✓ |

Structure: 200×500, **100,000 unique attempt IDs, 0 duplicates, 0 malformed lines**; all 12 family totals == allocation exactly. **All 243 unexpected records provenance-checked individually**: every one `variant=ws_inside_ok`, identical detail (relative-path `PathSecurityError` resolved against process CWD), batches 190–193 — harness-calibration defect, not a product recovery failure. **Prior report CONFIRMED correct.** Script: `%TEMP%\opencode\v6_m8_lab\reconcile_100k.py`.

## C. Ranked root causes and capability gaps

1. **(P1, FIXED)** `WorkspacePathSecurity.validate` resolved relative inputs against process CWD → false-rejects whenever CWD≠workspace (553 campaign records across both legs). → **R1**.
2. **(C-class, NEW, approval-gated)** **D-MIG-1:** full `downgrade base` impossible on any DB — `3cebbede5768` drops 8 tables, `downgrade()` is `pass`. → **R10 proposal**.
3. **(P1, external)** Latency budgets fail in-suite (7–15× inflation) / pass isolated (8/8) — load signature; idle rerun needs scheduling approval.
4. **(P2, approval-gated)** V5-D2 resume default mismatch (R4); V5-D3 evidence-hash never recomputed (R5).
5. **(Phase 2 NARROW)** No executor-layer deadlines/backoff/cancellation (prop 8); happy-path-only atomicity + non-atomic `restore_backup` copy (prop 6); restore compatibility unenforced (prop 10); quota opt-in + breaker not in recovery path (prop 14); no measured false-alarm budget (prop 1).
6. **(PARTIAL-TESTS)** `SQLAlchemyStateCheckpointRepository` untested (5); worker/orphan repo test-only (9); no general audit redaction pass (11); no end-to-end correlation-chain test (12).
7. **(capability non-claims, unchanged)** No syntax/type/import/test/dependency/merge/patch repair; real process-kill/network/disk-full/clock-skew/live-PG NOT TESTED.

## D. Proposed and completed fixes, with exact diffs

**R1 (implemented) — `sdk/workspace_protection/path_security.py` (+8 lines),** test `tests/integration/test_workspace_protection/test_path_security.py` (+51):
```diff
         if target_str.startswith("\\\\"):
             raise PathSecurityError(f"UNC paths are not allowed: {target_str}")
+        if not target.is_absolute():
+            # Relative inputs are workspace-relative. Anchoring them at the
+            # workspace root (instead of the process CWD, which is arbitrary
+            # for a library) can only convert false-rejects into correct
+            # accepts: the post-resolve containment check below still enforces
+            # the boundary for every path, relative or absolute.
+            target = self._workspace_path / target
         try:
             resolved = target.resolve()
```
New tests: relative-inside accepted from foreign CWD (RED first — reproduced the exact campaign error), relative `../escape` still refused, absolute-outside still refused.

**Test-only additions (no product code):** `tests/unit/test_reference_adapter_contracts.py` (26 tests), `tests/integration/test_alembic_migration_safety.py` (6 tests, 2 honest xfail), `tests/integration/test_workspace_protection/test_path_security_properties.py` (5 seeded property tests, 500-path adversarial sweep).

**Approval-gated proposals (NOT implemented):** R4 resume default, R5 evidence-hash recompute, R8 legacy canned response, R10 migration downgrade repair, R11–R16 Phase-2 backlog — `%TEMP%\opencode\v6_m8_lab\approval_gated_proposals.md`.

## E. Before-and-after test results

| Scope | Before | After |
|---|---|---|
| Path-security dir | 30 passed, 1 skipped (relative-inside-from-foreign-CWD **failed**: defect) | **33 passed, 1 skipped** (+3 regression) |
| Property suite (new) | — | **5 passed** (500 adversarial paths; victim-zero-side-effect property) |
| Live-agent stress (consumer) | 23 passed (run #3) | **23 passed** (364.9s) |
| Unit suite (full) | 2390 collected | **2390 passed, 1 skipped, 0 failed** (715.8s) |
| Reference adapter contracts | 0 direct tests | **26 passed** |
| Alembic safety | 0 tests | **4 passed, 2 xfailed** (D3 + D-MIG-1 visible) |
| Ruff/mypy on new/changed | — | **exit 0 / exit 0** |

## F. Recovery and safety metrics with denominators

100,000/100,000 attempts (exact allocation, 200×500, seed `0x1A2B3C4D`): verified-correct outcomes **99,757** (59,958 recovered + 29,577 expected refusals + 10,222 honest fault detections); unexpected **243** (all preserved `ws_inside_ok` calibration, root cause now fixed via R1); **invariant violations 0**; unsupported 0. Wall 10,105.94s, 9.9 att/s, disk 77.0 MB, peak 109.8 MB (bounds 4h/2GB/4GB respected). Stress A–H: 216 tests green, no timeouts. Runner selftest 13/13 (integrity controls: tamper→3, invariant→2 immediate, ×5 consecutive→abort).

## G. Full-suite results, performance evidence, environmental limitations

- Controlled rerun #3 (fresh `--basetemp`, single run): **3 failed / 2,857 passed / 7 skipped**, exit 1, coverage **83.57% ≥ 80%**; failures are the 3 latency budgets only. Isolated benchmark (once): **8/8 PASS**. Thresholds unchanged. Latency verdict: FAIL-in-suite / PASS-isolated under load signature (confound: light edits overlapped window).
- Performance: idle coordination burst p95 0.0045ms / churn 0.0272ms / tenant p95 2.828ms @1606.3 plans/s; under 4-worker load tenant p95 4.188ms @1098.6 plans/s (honest degradation). Single-machine (8 vCPU laptop).
- Limitations: real process-kill/network/disk-full/clock-skew/live-PG **NOT TESTED**; CI never run; Docker/PG/Redis unverified; gauntlet single-seed; alembic not in suite before this mission.

## H. External verification and CI evidence

**BLOCKED EXTERNALLY.** Workflows (`ci.yml`, `docker-verify.yml`, `security.yml`) exist but have **never run** (push needs two separate authorizations; neither granted). A config file is not a run — recorded as such (Phase 6 row 4).

## I. Security and production-readiness checklist

14-row checklist: **8 PASS** (artifacts wheel+sdist install→migrate→boot; fresh installs; dated scans — bandit 0/-ll, semgrep 11W/0E, pip-audit 0/110 SBOM; backup drill w/ independent verification; structural observability/runbooks; measured capacity; documented operator docs; threat model/rollback strategy), **3 PARTIAL/PENDING** (migration rollback — D3 + new D-MIG-1; upgrade/downgrade compat; alerts delivery), **2 BLOCKED EXTERNALLY** (CI; container+DB), **1 NOT TESTED** (real kill/network/disk). Full: `%TEMP%\opencode\v6_m8_lab\phase6_checklist.md`.

## J. Comparative benchmark design and completed results

**Design completed, no results claimed** (`logs/v6_frozen_benchmark_v1/BENCHMARK_DESIGN.md`): identical tasks/faults/limits/criteria/verification for Interlock and baselines (git rollback, snapshot tools, PG PITR, checkpoint frameworks); metrics = verified/unsafe/false-success rates, time-to-recovery, overhead, coverage, reproducibility. Candidate baselines to be selected at execution; unavailability reported as NOT TESTED, never as a loss. **No world-leadership claim without reproducible comparative runs on both frozen suites.**

## K. Remaining blockers, required approvals, and next actions

**Frozen benchmark suites designed — NOT executed (Phase 8 review gate):** Suite A `SUITE_A_MANIFEST_v1.json` (26 scenarios, exactly 100,000 attempts, sha256 `dc74ebd2…c5189b`), Suite B `SUITE_B_MANIFEST_v1.json` (31 scenarios, 31,000 attempts, sha256 `da45c22c…115d4c25`). **Awaiting review of scenario definitions + acceptance criteria before any run.**

**Approvals needed (nothing performed):** 1) M-PKG + guard (G6) → 2) R10 downgrade repair → 3) R5/R4/R8 → 4) commit/push ×2 (G7) → 5) production/infra (G11) → 6) idle-window suite rerun (latency exception) → 7) R11–R16 Phase-2 backlog review → 8) frozen-suite execution authorization.

## L. Evidence-based ratings (three dimensions)

| Dimension | Rating | Basis |
|---|---|---|
| **Validation & test quality** | **8.5/10** | 2,867 tests + coverage floor + 13/13 runner selftest + new property/contract/migration suites + honest xfail discipline; docked: 3 open latency failures, alembic/property/state-machine coverage gaps closed only partially, no CI, hypothesis-style generation absent (dependency policy) |
| **Recovery correctness & reliability** | **9/10** | 100k campaign independently reconciled (0 invariant violations, every family exact), R1 closed the only systemic false-reject, 14-property assessment shows 0 GAP + honesty-first design; docked: D-MIG-1 (downgrade impossible), executor-layer deadline/backoff/cancellation absent, non-atomic `restore_backup` copy |
| **Production evidence & operational readiness** | **6.5/10** | Artifacts verified install→migrate→boot, dated clean scans, backup drills, runbooks; docked: CI never run (external), Docker/PG/Redis unverified, M-PKG/D3/D-MIG-1 open, single-machine perf, latency exception open |

**No rating exceeds the evidence above.** Nothing was staged, committed, pushed, published, deployed, or applied to any non-disposable resource.
