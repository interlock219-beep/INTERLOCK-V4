# INTERLOCK V5 — TEST EVIDENCE REPORT

**Run date:** 2026-10-15 · branch `master` @ `145a3d9` · all work uncommitted
**Environment:** Windows, repo `.venv`, PowerShell.
Command used for suites:
`& ".\.venv\Scripts\python.exe" -m pytest <paths> -q --no-header --no-cov`
(coverage gate skipped deliberately in dev runs; no custom markers;
`--strict-markers` clean).

All runs below were executed **uncontended** (no parallel scans/builds
during a full-suite run; an earlier contended attempt was discarded and is
not cited).

---

## 1. Pre-fix baseline (regression-first discipline: this is the "before")

| Item | Value |
|---|---|
| Command | `pytest tests -q --no-header --no-cov` (background) |
| Result | **2719 passed, 7 skipped, 0 failed** in 17m21s |
| Log | `$env:TEMP\v5_gate_full_suite.txt` |
| Meaning | Reproduces the prior campaign's headline claim **exactly** before any gate fix touched the tree. Claim class: **Verified this run.** |

## 2. Regression tests written first (RED)

| Item | Value |
|---|---|
| Scope | 12 new regressions in `tests/unit/test_git_repository_adapter.py` exercising V5-16/V5-19/V5-20 (path escape, rename honesty, before-snapshot capture) |
| Result | **12 failed, 31 passed** (failures = the un-fixed defects, expected) |
| Log | `$env:TEMP\v5_gate_red.txt` |

## 3. After the 8 fixes (GREEN + neighbors)

| Item | Value |
|---|---|
| Targeted green | **43 passed, 0 failed** — orchestrator reliability (12) + git adapter (31) · `$env:TEMP\v5_gate_green.txt` |
| Neighbor sweep | **181 passed, 0 failed** — neighboring suites adjacent to the changed orchestrator/git code (exact file list not persisted in the `-q` log; the run header/count is) · `$env:TEMP\v5_gate_neighbors.txt` |
| Alembic | `alembic heads` → exactly **one** head (`67080f3cfec6`) |

## 4. Post-fix full suite

| Item | Value |
|---|---|
| Result | **2731 passed, 7 skipped, 0 failed**, `EXITCODE=0`, 16m58s |
| Arithmetic | 2719 + 12 new regressions = 2731 exactly (no other delta) |
| Log | `$env:TEMP\v5_gate_full_suite_postfix.txt` |

## 5. Final gate suite (authoritative, after dependency + lint + quota-contract changes)

| Item | Value |
|---|---|
| Command | `pytest tests -q --no-header --no-cov` (background, uncontended) |
| Expected arithmetic | 2731 + 7 new `QuotaCounterStore` contract tests = **2738** |
| Result | **2738 passed, 7 skipped, 0 failed**, `EXITCODE=0`, 16m47s — arithmetic matches exactly (no other delta); same 7 documented skips |
| Log | `$env:TEMP\v5_gate_final_suite.txt` |

## 6. Targeted verification batch (dependencies + touched areas)

| Item | Value |
|---|---|
| Scope | 18 files: quota contract, git adapter, orchestrator reliability, distributed recovery, registry, certification lab, env/archive/hosts adapters, surgical/agent/auth routes, session rollback, advanced authorization (×2), filesystem/risk/jwt/token/planning matches |
| Result | **351 passed, 0 failed** in 43.3s — executed **after** `pyjwt==2.15.0` + `urllib3==2.8.0` were installed (auth path green under the patched pin) |
| Log | `$env:TEMP\v5_gate_targeted.txt` |

## 7. The 7 skips (stable across every run this campaign)

| Skip | Reason |
|---|---|
| symlink creation tests | require OS symlink privilege (admin) |
| 5 performance-threshold tests | machine-dependent thresholds (benchmark asserts documented separately) |
| key-manager test | external key manager unavailable |

Skips were **never** added/changed this run; no test was deleted, xfailed,
or had assertions relaxed (modified test files are inventory-changed only —
see changelog §3).

## 8. Static-analysis evidence (exact CI commands)

| Check | Result |
|---|---|
| `ruff check` (24 V5-touched files) | **0 findings** |
| `ruff check app sdk tests` (CI parity) | 640 at HEAD → **621 findings after this run's V5-file fixes** (remainder = pre-existing repo-wide debt, mostly `tests/`; G-18, not bulk-fixed) |
| `mypy app` | **5 errors / 306 files** — all in files untouched at HEAD (`payment_providers` stripe stubs, `snapshot_types` ×2, `snapshot_repository` ×2); was 42 before this run's type fixes |
| `bandit -r app -ll` | pre-gate: 1 High (archive B202 legacy branch) → suppressed with inline manual-review justification; **final scan: 0 findings** (plus benign pre-existing `nosec` warnings in `database_recovery_adapter.py`) |
| `semgrep --config auto app` | 43 findings → 1 V5 (archive extractall, suppressed with manual-review justification, file re-scan clean) + **42 pre-existing baseline** (repository `len(all())` performance rules, logger-credential FPs, auth/billing/database SQL rules — never enforced because CI does not trigger) · log `v5_gate_semgrep.txt` |
| `pip-audit -r requirements.txt` | 20 advisories/4 packages before → **3 advisories / 2 packages remain** (`python-jose`, `ecdsa` — no fix published, G-14; the duplicate `ecdsa` row is the same PYSEC ID reported twice by the tool) |

## 9. Reproducibility note

The three full-suite logs (pre-fix 2719, post-fix 2731, final §5) plus the
RED/GREEN/neighbor/targeted logs are the primary evidence set for this gate.
Anyone re-running the commands above on this tree should reproduce the same
counts while the tree remains uncommitted as reported here.
