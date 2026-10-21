# Interlock V6 — Troubleshooting Guide

Common setup failures, how to diagnose them, and safe next steps. Every entry
was checked against the actual installation and test environment
(Windows 10/11, Python 3.11.9, 2026-10-18).

## Install problems

**`pip install -e ".[dev,security]"` fails**
- Check Python first: `python --version` must print 3.11.x–3.14.x (the package
  declares `>=3.11,<3.15`). Python 3.10 or 3.15+ will refuse.
- Ensure you are in a fresh venv and `pip` is current enough for PEP 660
  editable installs (`python -m pip install --upgrade pip`).
- There is **no PyPI package named intentlock** to install — install from a
  checkout only. (`pip audit` skipping "intentlock: not on PyPI" is expected.)

**`python -c "import app.main"` fails with ModuleNotFoundError**
- Run commands from the repository root, inside the activated venv. The
  package installs the `app` and `sdk` packages from the checkout.

**`python -m pip check` reports broken requirements**
- You likely mixed venvs or interrupted an install. Recreate the venv
  (`python -m venv .venv --clear`) and reinstall. Do not hand-edit pinned
  requirements.

## Demo and recipe problems

**`python scripts/pilot_demo_v1.py` exits non-zero**
- Read the printed JSON verdicts: each leg is labeled (recovery, safety,
  human_change, idempotency). A failing leg with a fresh checkout is a
  reportable finding — send the full output (it contains no file contents).

**Recipe prints `blocked_by_conflict` on the duplicate-delivery step**
- That step is *supposed* to refuse (idempotency). Only an unexpected
  `blocked_by_conflict` on the **first** recovery is a problem.

**`FileNotFoundError` running the recipe**
- The recipe must run from the repository directory (it imports `app.` modules
  and creates its own disposable temp directory).

## Test-suite gotchas

**Two symlink tests skip on Windows**
- Expected on an unprivileged shell: `test_dangling_symlink_staging_cannot_escape*`
  require symlink privilege (WinError 1314 class). On macOS/Linux they run.

**Four xfailed migration tests**
- Expected and intentional: the visible D-MIG-1/D-MIG-1b/D3 defect records.
  Never convert them to green locally; migrations are out of beta scope.

**Targeted pytest runs fail on the coverage gate**
- The repo default addopts enforce coverage ≥ 80 %. For a quick targeted run
  use `-o addopts=` (full runs keep the gate).

## Recovery-behavior questions

**"A `*.recovery_tmp` file appeared next to my file"**
- That is the staging file of a recovery attempt. Its presence with the target
  intact is the documented safe state after an interrupted attempt; the next
  retry clears it. The target is never half-written.

**"Recovery refused with a conflict"**
- The engine detected changes it did not make (a human edit, or a previously
  completed recovery). Inspect the conflict details in the result; resolve by
  re-capturing evidence if the current state is intentional.

**Migrations / alembic errors**
- Out of beta scope. Do not run `alembic upgrade/downgrade` on anything you
  value; the documented downgrade defects brick databases (handoff §5).

## Getting help safely

Include: OS + `python --version`, checkout commit, the exact step/command, the
full error text, reproducibility. Exclude: source code, secrets, database
dumps, unreviewed full logs. Template:
`INTERLOCK_V6_BETA_INVITATION_PACKAGE.md` §H.
