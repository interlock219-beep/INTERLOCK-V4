# INTERLOCK V6 — Release Readiness Report

Date: 2026-10-18. Scope of this report: evidence-backed readiness of
Interlock V6 ("intentlock" 4.0.0) for controlled beta, paid beta, and GA.
Every claim cites evidence; mocked or skipped tests are never counted as
real. This document is a new file created by the final readiness mission.

---

## 1. Executive verdict

| Level | Verdict | Basis |
|---|---|---|
| **Controlled beta** (consenting volunteers, disposable projects, Windows x64, Python 3.11.9, offline) | **READY WITH CONDITIONS** | install/recovery/conflict/retry/kill/permission evidence is real and reproducible; conditions: `BETA_FIRST_RUN.md` verbatim, disposable projects only, no production data, limitations doc signed off, M2 disclosed as unexecuted |
| **Paid beta** | **NOT READY** | zero customer-demand evidence (no interviews, no pilot completed); no terms/privacy/refund/ support policy; no incident-response runbook; no external security review; founder-minor legal/accounting scaffolding absent. Recommended instead: consent-based **free pilot** (§11) |
| **General availability** | **NOT READY** | blocked: real disk-full (M2), native POSIX validation (Linux/macOS), CI never executed, external audit, R10 migration repair, full-suite re-run for the R17 delta, operational runbook |

## 2. Repository state

- Initial (this mission): HEAD `145a3d9` (master, 2026-09-27), staged 0,
  stash 1, porcelain **213 = 69 M + 60 D + 84 ??**, 60 `web/` deletions.
- Final: see §4 — one local commit of the exactly-isolated approved paths;
  everything else preserved byte-for-byte (porcelain recount in the session
  log; stash 1; web deletions 60).
- `logs/` evidence directories are git-ignored by design; their integrity is
  recorded in the engineering log (append-only).

## 3. What was verified this session (not inherited)

- Wheel build (`python -m build`): `intentlock-4.0.0-py3-none-any.whl`
  (579.6 KB) + sdist; **installed into a clean venv and imported from
  site-packages** (not the source tree) with a functional restore smoke:
  byte-exact recovery, zero residue, exit 0.
- Fresh dependency audit: exactly 2 findings (`mcp 1.29.0` — upstream-blocked
  by semgrep's verified exact pin; `nltk 3.10.3` — via undeclared `safety`,
  not shipped). `pip check` clean. `bandit -r app -ll`: 0 issues.
  `ruff check app sdk`: clean.
- M3 evidence integrity: original (09:25:14Z) and post-R17 rerun (13:30:38Z)
  both PASS and distinct — the disclosed overwrite was fully repaired.
- Suspected timestamp-restore defect: **retracted after inspection**
  (capture stores both float and ns keys; both restore paths are live).
- CI workflows exist (`ci.yml`, `security.yml`, `docker-verify.yml`) but have
  **never run** (no push since 2026-09-27) and covered ubuntu/3.11 only.

## 4. Files changed by this mission and the commit

Commit (local only; no push/tag/publish): `COMMIT_HASH_PLACEHOLDER`

| Path | Pre-existing state | This mission's change | Why | Tests/evidence | Committed? |
|---|---|---|---|---|---|
| `requirements-dev.in` | clean at HEAD | +`virtualenv>=21.7.13,<22.0` | owner-approved advisory remediation (4 advisories cleared; lock regenerated in git-ignored `requirements-dev.txt`) | pip-audit before/after JSONs; pre-commit hooks execute under 21.14.11 | **YES** (1-line diff verified) |
| `docs/operations/SUPPORTED_PLATFORMS.md` | new file | new | §3-required bounded support matrix | cites existing evidence dirs | **YES** |
| `INTERLOCK_V6_RELEASE_READINESS_REPORT.md` | new file | this document | §12 final report | — | **YES** |
| `app/infrastructure/recovery/filesystem_recovery_adapter.py` | **modified before this mission** (D-RH campaign: 280+/44− total) | +R17 hunks (staging `0o600` ×2, recorded-mode-only chmod ×2) | inseparable from pre-existing uncommitted work at file level | targeted 29/4; subset 46/6 exit 0 | **NO — withheld** (mixed with pre-existing work) |
| `app/infrastructure/backup_restore.py` | **untracked pre-existing** | +R17 backup perms | same | backup drill incl. new POSIX test | **NO — withheld** |
| `tests/unit/test_filesystem_recovery_adapter.py` | clean at HEAD | +R17 tests (126 lines, pure additions) | kept with their engine for coherence | 4 POSIX skip-on-Windows + 1 executed | **NO — withheld with the engine** |
| `tests/unit/test_backup_restore_drill.py` | **untracked pre-existing** | +R17 POSIX test | same | skips on Windows | **NO — withheld** |
| `.github/workflows/ci.yml` | **modified before this mission** (54+/10− incl. pre-existing) | +`recovery-cross-platform` job (12 cells: 3 OS × 4 Pythons, service-free, symlink+R17 tests will execute on POSIX runners) | mixed file — not stageable as a unit | YAML parsed: both jobs valid | **NO — withheld** (mixed) |

## 5. Test record (this session; earlier runs cited with their evidence)

| Command | Result | Exit |
|---|---|---|
| `pytest tests\unit\test_filesystem_recovery_adapter.py tests\unit\test_backup_restore_drill.py -o addopts=` | 29 passed, 4 skipped (POSIX-mode reasons recorded), 25.5s | 0 |
| recovery regression subset (fault-injection + backup + adapter) | 46 passed, 6 skipped, 62.0s | 0 |
| `ruff check app sdk` / on changed files | clean | 0 |
| `bandit -r app -ll` | 0 issues | 0 |
| `pip_audit -f json` (working venv) | 2 documented findings | 1 (findings present) |
| `python -m build --outdir <temp>` | wheel + sdist | 0 |
| clean-venv wheel install + `pip check` + functional smoke | site-packages import; byte-exact restore; zero residue | 0 |
| M3 drill rerun (post-R17) | PASS | 0 |
| Full suite (2922 passed/9 skipped/4 xfailed, 3719.82s) | run #3, historical — **not re-run** (no runtime-logic delta justified it; recorded as a GA requirement) | 0 |

## 6. Support matrix

See `docs/operations/SUPPORTED_PLATFORMS.md`. Summary: **Windows x64 /
NTFS / Python 3.11.9 = TESTED PRIMARY**; Linux x64 + macOS (arm64) /
Python 3.11–3.14 = **DECLARED, CI PENDING** (encoded in the new CI job;
executes the symlink drills and R17 POSIX tests on first push); Windows
ARM64, long paths, FAT32/exFAT/network dirs = untested or **UNSUPPORTED**
(no atomic-replace guarantees).

## 7. Gate C and Gate D

- **Gate C — PARTIAL.** C-A1 (M1 real kill 20/20) ✓, C-A2 (M3 real
  permission, original + rerun) ✓, C-A4 independent checks ✓, C-A5
  regressions ✓, C-A6 scoped ✓. **C-A3 (real disk-full M2) BLOCKED** —
  authorization requested twice, never granted; procedure + refusal-guarded
  drill prepared (`logs/v6_gate_cd_20261018T100500Z/m2_procedure.md`,
  `m2_diskfull_drill.py`). Mocked ENOSPC is not a pass.
- **Gate D — PASS (controlled-beta scope) / PARTIAL (GA).** Runtime-lock
  advisories 0; 2 unique non-actionable findings documented with verified
  constraints; privacy docs match behavior (no network/telemetry in
  recovery paths); R17 implemented with POSIX-only tests **skipped, not
  passing**; external audit not claimed (GA-mandatory).

## 8. Real vs mocked vs skipped failure tests

- **Real (Windows, this product's own host):** hard process-kill mid-recovery
  (20/20), permission denial at the atomic swap (original + rerun),
  conflict/refusal paths, wheel-level functional recovery.
- **Mocked only:** disk-full/ENOSPC, quota exhaustion, cross-user access,
  concurrent-writer windows.
- **Skipped (environment):** 2 symlink-escape drills (Windows privilege),
  4 R17 POSIX permission tests (no POSIX host) — CI job will run both sets
  on Linux/macOS at first push.

## 9. Security, privacy, packaging, operations

- Dependencies: runtime lock clean of dev tooling; orphan subtree removed
  (session 7); `mcp` upstream-blocked (semgrep exact pin — DoS-only surface,
  never used); `nltk` not shipped; venv-seeded `setuptools` documented.
- Privacy: engine reads/writes/backs up **only files inside the configured
  disposable project dir**; transmits nothing; needs no network; verification
  failure → typed fail-closed with evidence preserved.
- Packaging: pure-python wheel verified installable offline-capable from a
  local artifact; no console script exists (interfaces: Python API, SDK,
  `scripts/`, uvicorn) — first-run docs reflect this.
- Supply chain: no published artifacts (publishing requires separate
  authorization); release-artifact hashing can be added at publish time.
- Operations: no CI execution yet; no runbook; no incident-response drill.

## 10. Outstanding blockers and risks

Beta-scope: real M2 (one approval away); POSIX execution (one CI push away).
GA-scope: everything in §1's GA row + external audit + R10 + customer
demand + legal/ops scaffolding.

## 11. Is charging customers justified today?

**No.** Nobody has been interviewed; willingness to pay is unknown; the
paid-beta legal/support/incident apparatus does not exist. Recommended path:
a **consent-based free pilot** (3–5 volunteers, disposable projects, the
existing invitation package) with measurable progression criteria:
(a) ≥3 volunteers complete `BETA_FIRST_RUN.md` unassisted, (b) zero
data-integrity incidents across ≥2 weeks, (c) M2 executed and passing,
(d) Linux/macOS CI cells green, (e) ≥2 interviewees express uncoerced
willingness to pay a named price. **Founder note: you are 16 — involve a
trusted adult for payment accounts, contracts, handling any customer data,
refunds, and public commitments, and get appropriate legal/accounting
advice before charging anyone.**

## 12. Next three actions (priority order)

1. Push to the existing `origin` (needs your explicit authorization) → the
   12-cell cross-platform CI job plus the security workflow execute →
   converts Linux/macOS/Python-matrix and symlink/R17-POSIX evidence from
   "declared" to real.
2. Approve the M2 one-time elevation (UAC) → the prepared drill closes
   Gate C's last criterion.
3. Send the invitation package to slot T1 (+POSIX slot T2 now that CI will
   back it) → first independent-installation evidence; start the five
   discovery interviews.

## 13. Operations requiring separate authorization

Pushing (any ref), tagging, publishing packages, deploying, M2 elevation,
WSL/POSIX-host provisioning, external audit engagement, contacting
volunteers/customers, dependency removals beyond the approved remediation,
and running the frozen Suite A/B benchmarks.
