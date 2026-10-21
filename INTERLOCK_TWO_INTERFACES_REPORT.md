# Interlock — Two-Interface Product Scope Report

Date: 2026-10-20 · HEAD `624171e` · Not committed (no authorization).

This report covers the scope clarification: Interlock ships **exactly two**
product interfaces over **one** shared recovery engine, each packaged, tested,
and documented independently.

---

## 1. Scope summary

| | Interface 1 — VS Code extension | Interface 2 — Terminal Runner (CLI) |
|---|---|---|
| Role | primary visual interface | first-class terminal/agent interface |
| Deliverable | `interlock-vscode-0.1.0.vsix` | `intentlock-4.0.0-py3-none-any.whl` |
| Recovery logic | shared engine + shared `interlock_bridge.py` | **same** engine + **same** `interlock_bridge.py` (imported, never copied) |

**Shared architecture — no fork.** The CLI adds only argument parsing and
terminal rendering. Every operation (`protect`/`analyze`/`preview`/`recover`/
`verify`/`status`/`doctor`) calls the bridge's own `cmd_*` handlers and returns
the bridge's own exit codes; recovery decisions, conflict/drift checks, approval
gating, and byte-exact verification all remain in `app/`/`sdk/` + the bridge.
(Design note: `interlock_bridge.py` still physically lives under the extension
directory; relocating it beside the engine is a recommended future refactor,
deferred to avoid clobbering parallel work.)

**Explicitly out of scope (not built):** standalone desktop app, separate web
recovery app, browser recovery dashboard, any second GUI outside VS Code. The
`site/` marketing/docs pages are permitted and are **not** a third interface.

---

## 2. Exact deliverables

### 2.1 VS Code extension
- **File:** `extensions/vscode/interlock-vscode-0.1.0.vsix`
- **Size:** 32.24 MB · **SHA-256:** `3a05b4a03eeb402f5fa842acef53813ed137e85b5e4b248e8fc9d4dbe0bdcb7b`
- **Built:** 2026-10-20 12:28 (prior zero-config mission) · **Installed:** local + isolated test dirs
- **Install prerequisite:** none on **Windows x64** (bundles a pinned, SHA-256-verified CPython 3.11.17). On macOS/Linux/ARM it falls back to a **system Python 3.11–3.14** (no runtime is bundled there → zero-config is **not** advertised there).
- **First run:** install the VSIX → the Activity Bar shield → **Protect Workspace** (or `interlock.installEngine`). Requires no manual Python/engine path on Windows x64.
- **Platforms exercised:** Windows x64 / NTFS.

### 2.2 Terminal Runner (CLI)
- **File:** `dist/intentlock-4.0.0-py3-none-any.whl`
- **Size:** 614,573 bytes (~600 KB) · **SHA-256:** `d67fa147226c34cbf3e60781cb8034953c4a3be8fbe16e4a866affac07f0848d`
- **Install prerequisite:** **Python 3.11–3.14** (the only external requirement — the engine's import closure is standard-library-only). Installed offline with `pip install --no-deps <wheel>`; a plain `pip install` additionally pulls the gateway's server deps (fastapi/redis/…) because both live in one distribution.
- **Console script:** `interlock` (after install), or run directly with `python interlock_cli.py`.
- **First run:** `interlock doctor` → engine available → `interlock protect --workspace … --resource …`.
- **Platforms exercised:** Windows x64 / NTFS / Python 3.11.9. The CLI itself is OS-portable (stdlib + pathlib) but **macOS/Linux are declared pending CI**, not executed here.

**Distribution decision (evaluated):** package-based chosen over a standalone
PyInstaller binary and over a bundled CPython runtime — see
`docs/operations/TERMINAL_RUNNER.md` §1 for the comparison table. The
standalone/bundled options would remove the Python prerequisite but require a
new build dependency (approval-gated) and one build per OS/arch; neither was
built. The remaining prerequisite (Python 3.11–3.14) is stated, not hidden.

---

## 3. Real test results (independently run, 2026-10-20)

### Terminal Runner — green
| Check | Result |
|---|---|
| Source lifecycle (`tests/integration/cli_lifecycle_check.py`) — help/doctor/protect/analyze/preview/recover(no-approval→5)/recover(approved→0)/verify/`--json`/confinement/exit-codes | **38 passed / 0 failed** |
| Packaged wheel in a **fresh venv** (`--no-deps`, no repo on path, no `--engine-root`, no `INTERLOCK_BRIDGE`) — `tests/integration/cli_clean_install_check.py` | **27 passed / 0 failed** |
| `ruff check` / `ruff format --check` / `mypy` (strict) on the CLI | **all pass** |

These prove the installed CLI is self-contained outside the interpreter and
needs neither the checkout nor the extension.

### VS Code extension — deliverable exists; current source **compile-blocked**
- The packaged `.vsix` (built 12:28) **exists and is valid** (hash above). Its
  prior-mission results are recorded in
  `extensions/vscode/INTERLOCK_ZERO_CONFIG_REPORT.md`: unit **239 passing**,
  integration (bundled runtime) **58/0**, extension-host configured **35/0**,
  zero-config host **PASS**, clean-environment install **42/0**.
- **Current working tree does NOT compile/lint right now** (verified this
  session): `npm run typecheck`/`lint`/`compile` fail on three in-flight files
  owned by the **parallel worker** — `src/recoveryReportHtml.ts`
  (`string | null` → `string` × ~15), `src/recoveryReport.ts` (unused
  `worstOf`), `test/unit/recoveryPlan.test.ts` (missing `code` on
  `ProposedContent`). Because `compile` fails, the unit suite cannot run now.
- **I did not touch `extensions/` this session** (my edits: `interlock_cli.py`,
  two `tests/integration/cli_*` drivers, `pyproject.toml`, and docs). These are
  the parallel worker's pre-existing/in-flight failures, **not** my regressions,
  and I am **not** claiming a current passing extension test. The VSIX reflects
  the last good build (12:28); a fresh package should be re-run once the worker
  finishes those fixes.

---

## 4. Supported platforms (per interface)

Detail: `docs/operations/SUPPORTED_PLATFORMS.md` (two-interface section added
2026-10-20).

- **Engine:** Windows x64 / NTFS **TESTED — PRIMARY**; Linux/macOS **DECLARED — CI
  PENDING**; FAT32/exFAT and network/OneDrive dirs **UNSUPPORTED**.
- **Extension zero-config runtime:** **Windows x64 only** (bundled). Elsewhere →
  system Python required.
- **CLI:** any OS with Python 3.11–3.14 in principle; **tested on Windows only**.
- Neither interface advertises a platform it has not exercised; no download
  links exist for unbundled platforms.

---

## 5. Remaining blockers

1. **Parallel-worker compile failures** in the extension tree (above) — must be
   fixed before the extension suite (or a re-package) can run/pass.
2. **No commit/push authorization** — nothing staged/committed; HEAD `624171e`
   is 1 ahead of origin and its `ci.yml` lacks a `master` trigger, so a push
   alone runs no CI.
3. **`ci.yml` is a mixed file** — needs an owner-approved hunk-level
   `git apply --cached` to stage only the intended parts.
4. **Pre-existing dependency change in the working tree (not made by me):**
   `pyproject.toml` vs HEAD shows `cyclonedx-bom` bumped `>=3.2,<4.0` → `>=7.0,<8.0`
   and `semgrep>=1.100,<2.0` **removed** from `[optional-dependencies].security`,
   plus an alembic `data-files` block — all already uncommitted before this
   session. Dependency changes need explicit approval; I neither added nor
   reverted them. My own pyproject edits are only the `[project.scripts]`
   console script, `py-modules = ["interlock_cli"]`, the bridge `data-files`
   line, and per-file-ignores for my files.
5. **`runtime/` gitignored** (owner decision pending: keep vs commit) ·
   **marketplace/PyPI publication not attempted** (no account/authorization) ·
   **M2 real disk-full (Gate C) authorization** never granted · **mcp
   CVE-2026-59951** upstream-blocked · **typer** unused-dep removal awaiting approval.
6. **Bundled runtime exists for Windows x64 only** — macOS/Linux/ARM runtimes
   and per-platform VSIX/CLI builds are not provisioned/tested.

---

## 6. Publication status — neither deliverable is published

| Deliverable | Published? |
|---|---|
| `interlock-vscode-0.1.0.vsix` | **No** — local file only; no VS Code Marketplace account/authorization. |
| `intentlock-4.0.0-py3-none-any.whl` | **No** — local file only; no PyPI upload, no release artifact. |

Both exist and were verified **locally**; nothing was pushed to any registry,
store, or remote.

## 7. Repository safety

Preserved throughout: HEAD `624171e` unchanged, **staged = 0**, stash intact,
all pre-existing/modified/untracked/ignored files untouched (including the 60
`web/` deletions, `site/`, `downloads/`, and the parallel worker's
`extensions/vscode/src` work). No `git add`/`commit`/`push`/`tag`/`reset
--hard`/`clean`/restore. Only build artifacts I created (`build/`, `dist/`,
`*.egg-info`) — all gitignored — plus my new source/docs files as untracked or
the single pre-dirty `pyproject.toml`.
