# Interlock V5 — Confirmed Defect Register (Release-Gate Audit)

Scope: defects **confirmed in this release-gate run** by reproducible test evidence or
direct code demonstration. Preceding defects V5-1..V5-13 are listed in
`INTERLOCK_V5_RECOVERY_CORRECTNESS_REPORT.md` §4; this register extends the sequence.
Severity: P0 = data loss/security bypass/core guarantee broken; P1 = serious
correctness/security with reachable trigger; P2 = correctness/robustness defect with
constrained trigger or fail-safe direction; P3 = honesty/quality debt.

**Method for every entry:** regression test written first → confirmed failing on
pre-fix code (RED, 12/12 new tests failed — see `$TEMP\v5_gate_red.txt`) → minimal fix
→ same tests green (43/43 with existing tests — `$TEMP\v5_gate_green.txt`) → neighboring
suites green (181 passed) → full suite re-run.

---

## Confirmed and fixed in this run

### V5-14 — Plan lease was per-instance; single-executor semantics vacuous in production (P1)

- **Component:** `distributed_recovery_orchestrator.py` / API routes.
- **File & function:** `DistributedRecoveryOrchestrator.__init__`
  (`lease_store or InMemoryPlanLeaseStore()`); construction sites
  `surgical_recovery.py:457/555`, `control.py:314/547`,
  `session_rollback_service.py:521`.
- **Reproducible evidence:** every route builds a fresh orchestrator per HTTP request
  while durable steps are shared (DB-backed) — each request therefore owned an
  independent lease space. Regression:
  `test_default_lease_store_shared_across_instances` (RED: second instance executed
  concurrently; GREEN: `already_running`).
- **Impact:** two concurrent execute/resume requests for the same plan could run the
  same compensations twice — the V5 single-executor guarantee did not hold where it is
  actually used.
- **Fix:** process-wide default store `_default_lease_store()` (double-checked locking;
  `lease_store` still injectable for tests/isolation). Still process-local by design
  (G-1 unchanged, Redis backend specified in the runbook §6).
- **Regression tests:** `test_default_lease_store_shared_across_instances`.

### V5-15 — `resume_plan` bypassed the plan lease entirely (P1)

- **Component:** orchestrator resume path.
- **File & function:** `DistributedRecoveryOrchestrator.resume_plan`.
- **Reproducible evidence:** code inspection + RED tests: resume never called
  `try_acquire`, so a resume could run **concurrently with an in-flight execute** of
  the same plan (double compensation), and never renewed (no stale-worker detection).
- **Impact:** interrupted-plan recovery — the exact flow leases exist for — was
  unprotected; concurrent execute+resume double-applied compensations.
- **Fix:** `resume_plan` now acquires/renews/releases the lease exactly like
  `execute_durable_plan` (wrapper + `_do_resume_plan`, per-step renewal →
  `lease_lost`, release in `finally` even on cancellation).
- **Regression tests:** `test_resume_plan_enforces_plan_lease`,
  `test_resume_renewal_loss_aborts_resume`.

### V5-16 — Git adapter allowed path escape on tampered payloads (P1, security)

- **Component:** `git_repository_adapter.py`.
- **File & function:** `_execute_restore_content`, `_execute_delete_file`,
  `_execute_restore_deleted_file`, `_execute_rename_back`, `verify`, `detect_drift`,
  `check_conflicts` — all joined `repo_path / payload["file_path"]` (or
  `action.resource`) with **no containment check**; `_extract_file_path` passed
  absolute paths through, and on Windows `Path("repo") / "C:\..."` *replaces* the base.
- **Reproducible evidence:** RED tests deleting/reading a file **outside** the repo via
  a tampered `file_path` (`../victim.txt` and absolute path); GREEN after fix with the
  victim untouched.
- **Impact:** evidence-store tampering (the V5-9 threat class) turned into arbitrary
  file write/delete outside the repository — inconsistent with the hardened
  config/filesystem adapters.
- **Fix:** `_resolve_payload_path()` — refuses absolute/drive/root paths, NUL bytes,
  `..` segments, and any path failing `_assert_contained` (symlink-following resolve);
  used by all execute/verify paths; drift/conflict use the capture-time
  `_resolve_resource_path` (raises on escape → step fails closed).
- **Regression tests:** 4 tests in `TestGitRepositoryAdapterPayloadContainment`.

### V5-17 — Execute-phase exceptions fell through to the next adapter (P1)

- **Component:** orchestrator step execution.
- **File & function:** `DistributedRecoveryOrchestrator._execute_single_step`
  (outer `except (AttributeError, TypeError): continue` wrapped the whole claim).
- **Reproducible evidence:** RED:
  `test_execute_phase_error_does_not_fall_through_to_next_adapter` — first adapter
  executed successfully, its `verify` raised `TypeError`, second adapter re-executed
  the same compensation (execute_calls == 2).
- **Impact:** double compensation of one step by two adapters whenever an adapter
  fails *after* performing its side effect (protocol mismatch on `verify`, shape
  errors on results).
- **Fix:** execution phase (`execute_compensation` → `verify` → result handling) now
  catches **all** exceptions and records the step `FAILED`; only pre-execution
  protocol probing (detect drift / conflicts / generate) may skip to the next adapter.
  Adapters without `verify` report executed-not-verified instead of falling through.
- **Regression test:** same as RED above.

### V5-18 — Resume verification trusted only the first adapter's verdict (P2)

- **File & function:** `_verify_external_outcome` — returned the first registered
  adapter's `verify()` result unconditionally.
- **Evidence:** RED `test_external_outcome_verification_consults_all_adapters`
  (first adapter says no → step marked `requires_manual_verification` although the
  capable adapter says yes).
- **Impact:** false negatives on multi-adapter sets: verified states reported as
  unverifiable (fail-safe direction, but wrong and noisy; manual-verification load).
- **Fix:** consult every adapter; any positive verdict counts; adapters that raise
  yield no verdict (never trusted).
- **Regression test:** as above.

### V5-19 — Git rename recovery over-claimed (P2, honesty)

- **File & function:** `detect_drift` (rename → always `NO_DRIFT` with "not fully
  implemented" detail), `_execute_rename_back` (no-op existence check reported
  `SUCCEEDED`), `verify` (`rename_back` self-certified `True` if the file existed).
- **Evidence:** no rename tests existed (searched); RED rename-honesty tests → GREEN.
- **Impact:** declared capability `file_rename_recovery` reported success without
  performing or verifying any rename reversal; drift never flagged renames.
- **Fix:** rename drift → `INSUFFICIENT_EVIDENCE` (same orchestrator gating, honest
  status); rename execution → `REQUIRES_MANUAL_ACTION` (destination not recorded in
  evidence); rename verification → never self-certifies (manual verification note).
  Capability matrix updated accordingly.
- **Regression tests:** `TestGitRepositoryAdapterRenameHonesty` (2 tests).

### V5-20 — Git capture ignored `before_snapshot` (P2)

- **File & function:** `capture_recovery_evidence(action, ..., before_snapshot=...)`
  accepted the parameter and never used it; captured before == after == live file.
- **Evidence:** RED `test_capture_honors_before_snapshot` (payload before-content was
  the post-action content) → GREEN.
- **Impact:** pre-action flows produced evidence whose before-state equaled the
  after-state — the same defect class as the config adapter V5-8 fix; conflict/drift
  checks then mis-anchor.
- **Fix:** mirror the config/filesystem contract: `before_snapshot or
  action.before_state_snapshot` supplies before-content; live file is after-content;
  fallback (both live) only when no snapshot exists.
- **Regression test:** `TestGitRepositoryAdapterBeforeSnapshot`.

### V5-21 — Migration graph had two heads (P1, deployment)

- **Component:** `alembic/versions/` — `0b481f00` and `3cebbede5768` both descend
  from `fc5e7844e4dd`.
- **Reproducible evidence:** `alembic heads` listed two heads before (saved in this
  run's log); `alembic upgrade head` on a fresh database fails with *multiple head
  revisions*.
- **Impact:** fresh deployments and disaster-recovery rebuilds could not migrate —
  directly breaks Interlock's own backup/restore story (Phase 7).
- **Fix:** additive no-op merge revision `67080f3cfec6` (`down_revision =
  ('0b481f00','3cebbede5768')`, upgrade/downgrade = `pass`); `alembic heads` now
  returns exactly one head. No existing migration was modified or deleted.
- **Verification:** `alembic heads` → `67080f3cfec6 (head)`.

---

## Confirmed, documented, deliberately not changed in this run

| ID | Defect / risk | Sev | Why not changed now | Safe-state / mitigation |
|---|---|---|---|---|
| V5-D1 | Stale-worker window: fencing is enforced at step boundaries (renew), not per operation; a worker that loses the lease mid-step finishes that step before its next renewal check. | P2 (theoretical) | Requires conditional-update-by-token in the durable repository contract (cross-cutting); documented in the orchestrator docstring. | Bounded by one step; tokens recorded in results for audit; Redis backend runbook §6 covers cross-instance takeover tests. |
| V5-D2 | `resume_plan(stop_conditions=None)` continues past failures while `execute_durable_plan` defaults to stop-on-first-failure; the API route always passes explicit plan conditions. | P2 | Changing the default alters documented behavior beyond the confirmed lease defect; no caller hits `None` in production paths today. | Documented; recommend aligning defaults with a dedicated change + tests. |
| V5-D3 | `verify_evidence_integrity` performs field-presence/format checks only — it never recomputes `evidence_hash` over canonical fields; the keyword classifier in `IndependentVerificationService.verify_evidence` inherits that limit. | P2 | Adding hash recomputation changes the evidence schema contract (what is hashed) — needs a versioned evidence-hash spec. | Evidence store is trusted-by-design (G-4); payload containment (V5-16) bounds blast radius; recommend hash-recompute + signature plan (G-4 remediation). |
| V5-D4 | `create_durable_plan` sorts actions missing from `topological_order` with order `0` (ambiguous placement). | P3 | No failing flow observed; needs a policy decision (append-at-end vs reject). | Documented. |
| V5-D5 | `list_by_plan(limit=500)` truncates plans with >500 steps (`total` reported, only 500 executed per pass). | P3 | No plan near the bound in practice; repeated passes are possible but unproven. | Documented; recommend paging loop. |
| V5-D6 | Database adapter declares `transaction_safe` capability; compensation statements are single-statement (atomic on SQLite/Postgres) but there is no multi-statement transaction or explicit rollback path. | P3 (honesty) | Capability string is load-bearing for registration tests; changing it needs a capability-contract decision. | Documented; per-statement atomicity holds on the supported engines. |

---

## Findings outside the code (see Security Review / Release Decision)

- **Dependencies:** pip-audit — 20 known vulnerabilities in 4 pinned packages
  (pyjwt 2.13.0 ×15 [fixable], urllib3 2.7.0 ×3 [fixable], python-jose 3.5.0,
  ecdsa 0.19.2 [no fix published]) → handled in the Security Review Summary.
- **CI:** workflow triggers on `main`/`develop` only; repository branch is `master`
  (+ local branches) → CI never runs for this repo's pushes; ruff/mypy baselines are
  already red at HEAD (details in Test Evidence Report) → Release Decision risk table.
- **Web frontend:** deleted in user working state (preserved); backend CI steps do not
  reference it → backend unaffected; product decision remains open (G-7).
