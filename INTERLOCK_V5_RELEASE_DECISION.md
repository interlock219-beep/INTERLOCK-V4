# INTERLOCK V5 — RELEASE DECISION

**Date:** 2026-10-15 · branch `master` @ `145a3d9` · all work **uncommitted**
**Basis:** the eight release-gate reports of this campaign (correctness,
test evidence, security review, failure injection, benchmark, gap matrix,
independent verification, this decision), each claim classified in
`INTERLOCK_V5_INDEPENDENT_VERIFICATION_REPORT.md`.

---

## 1. Decision

> **IMPLEMENTED WITH EXTERNAL VALIDATION REQUIRED**
> — **not** production-ready; **conditionally ready for an API-only staging
> trial** (conditions in §4). No commit/push until explicit user approval (G-13).

This confirms (does not upgrade) the status carried from the implementation
campaign: every implementation-side gate that *can* be executed in this
environment was executed and passed; the gates that cannot be executed here
remain open with committed procedures.

## 2. Gate results

| # | Gate | Result |
|---|---|---|
| 1 | Full test suite green, claims reproduced | **PASS** — pre-fix claim reproduced exactly (2719/7/0), post-fix 2731/7/0, **final gate suite 2738/7/0 (exit 0, 16m47s)** = 2731 + 7 quota-contract tests, arithmetic exact; 7 skips documented and stable |
| 2 | Regression-first defect handling | **PASS** — 8 confirmed defects (V5-14..V5-21): RED 12/12 → GREEN 43/43 → neighbors 181/181; 6 further findings documented-not-fixed (V5-D1..V5-D6) with impact bounds |
| 3 | Security scans (CI-parity commands) | **PASS with documented residuals** — pip-audit 20 → 3 advisories in 2 packages (no-fix upstream, G-14; pyjwt/urllib3 cleared); bandit final scan 0 findings; semgrep V5 finding eliminated with justified suppression (42 pre-existing baseline documented); secret scan 0 hits; DAST/secret-scanner tooling not run (documented) |
| 4 | Lint & types on V5 files | **PASS** — ruff 0 across all V5-touched files; mypy 42 → 5, all pre-existing in files untouched at HEAD; repo-wide baseline debt documented (G-18), not bulk-fixed |
| 5 | External integrations (cloud/Vault/SIEM/Postgres/K8s/multi-instance) | **OPEN — requires external validation** — executable runbook committed (`INTERLOCK_V5_EXTERNAL_VALIDATION_RUNBOOK.md`, G-1/G-2/G-3/G-9) |
| 6 | Web independence of the backend | **PASS** (backend has zero `web/` dependency; verified in CI config + import graph) — but frontend checks impossible (`web/` deleted by user, G-7); product ≠ release-ready on backend green alone |
| 7 | Packaging / deploy | **PASS with exception** — alembic single head (`67080f3cfec6`); health/ready endpoints exist; **CI has never run** for this repo (branch mismatch, G-18); no shutdown teardown (G-17); lockfile unpinned hashes (G-15) |
| 8 | Evidence & process | **STOPPED AT APPROVAL** — 8 reports written; commit manifest proposed; **nothing staged or committed**, `stash@{0}` untouched, `web/` deletions + `interlock_projects/` excluded |

## 3. Remaining risks by severity

### P0 — blocks production release
- **G-3** live external integrations never executed (no cloud/Vault/SIEM/Postgres/K8s evidence).
- **G-9** database/cloud/k8s adapters are contract-tested only (honestly labeled `external_validation_required`).
- **G-13** entire V5 campaign exists only in the working tree until committed.

### P1 — blocks production, not a staging trial (with conditions)
- **G-1** leases are process-local (cross-instance double execution possible in multi-replica).
- **G-2** quota counters: contract ready, distributed backend missing.
- **G-4/G-6** evidence integrity is trusted-by-design (no signatures; config `config_dir` provenance from payload).
- **G-7** frontend unverified (`web/` user deletions preserved, never restored).
- **G-14** two dependency advisories with no published fix (not imported by app code).
- **G-16** no backup/restore of evidence/plan history.
- **G-18** CI never triggers on `master` + red repo-wide lint/type baselines.
- **V5-D1/D2/D3** (P2 individually): stale-worker mid-step fencing window; resume stop-condition default divergence; evidence-hash never recomputed.

### P2 — tracked debt
- G-5 (legacy planning drift-gate divergence), G-8 (benchmark scope), G-10 (OTel off by default), G-11 (test/prod config parity), G-12 (hosts manual-action runbook), G-15 (lockfile hashes), G-17 (shutdown teardown), V5-D4/D5/D6 (P3: order-0 sort default, 500-step list truncation, `transaction_safe` breadth).

## 4. Staging-trial readiness (conditions)

A **single-instance, API-only** staging trial is supported by this evidence,
provided the operator accepts:
1. No frontend (G-7) — trial via API routes only.
2. Lease/quota operate in-process — exactly one replica until G-1/G-2 backends land.
3. No cloud/Vault/SIEM/k8s claims — those adapters stay
   `external_validation_required` until the runbook runs (G-3).
4. Evidence store treated as trusted infrastructure (G-4/G-6) with access
   controls compensating for absent payload signing.
5. CI not treated as a gate (G-18) — local ruff/mypy/pytest are the gate.
6. The unfixable-dependency exposure (G-14) accepted in writing.

## 5. Production blocking status

**BLOCKED** pending, in order: user approval + selective commit (G-13) →
external validation runbook execution (G-3 with G-1/G-2/G-9) → frontend
restoration decision (G-7) → CI retargeting + baseline cleanup (G-18) →
backup/restore procedure (G-16) → remediation or acceptance of G-14.

## 6. What changed this run (audit trail)

- 8 defects found and fixed regression-first (V5-14..V5-21); 6 documented.
- `QuotaCounterStore` backend contract extracted (+7 contract tests).
- Dependencies remediated (pyjwt 2.15.0, urllib3 2.8.0) and re-verified.
- Lint/type/security baselines measured at CI parity and reduced to
  pre-existing-only residuals on V5 files.
- 4 new reports + 4 updated reports; full claim classification published.

## 7. Approval checkpoint

**STOPPED HERE.** The proposed file lists, commit split, exclusions, and
pre-commit verification commands are in
`INTERLOCK_V5_PROPOSED_COMMIT_MANIFEST.md`. No Git action will be taken
without the user's explicit approval.
