# Interlock Terminal Runner (CLI)

Last verified: 2026-10-20 (mission: two-interface product scope). This is one
of Interlock's **two product interfaces** — the other is the
[VS Code extension](../../extensions/vscode/readme.md). Both drive the **same
shared Python recovery engine through the same orchestration layer**; neither
contains its own copy of the recovery logic.

- CLI source: `interlock_cli.py` (repository root)
- Shared engine command layer: `extensions/vscode/python/interlock_bridge.py`
- Shared engine: `app/` (domain + infrastructure/recovery) and `sdk/`
  (workspace_protection)

> **A note on where the shared code lives.** Today the orchestration module
> (`interlock_bridge.py`) lives under the extension directory but is the single
> command layer for *both* interfaces. The CLI imports it by path (source
> checkout) or from the installed `share/intentlock/python/` prefix (wheel) —
> it is never duplicated. Relocating that module next to the engine is a
> recommended future refactor; it is deliberately **not** done here to avoid
> colliding with parallel work on the extension.

## 1. Distribution method

The scope explicitly requires evaluating how to ship a terminal interface
without assuming the VS Code extension's bundled Python makes the CLI
self-contained. The three practical options:

| Method | Needs Python? | Size | Platforms | Build/CI cost | Status here |
|---|---|---|---|---|---|
| **Package-based** (`pip install` a wheel / run from source) | **Yes — Python 3.11–3.14** | ~0.6 MB wheel | any OS the engine supports | none (pure-`py3-none-any`) | **CHOSEN — built and tested** |
| Standalone executable (PyInstaller) | No | ~20–40 MB per OS | one build per OS/arch | new build dependency (approval required), per-platform jobs, common AV false-positives | not built |
| Bundled runtime (ship CPython like the extension) | No | ~100 MB+ per OS | one bundle per OS/arch | per-platform provisioning + hashing | not built |

**Decision: package-based.** Rationale:

- The engine's import closure is **standard-library-only**, so the recovery CLI
  genuinely has *zero* third-party runtime dependencies — a wheel is ~0.6 MB and
  installs offline with `--no-deps`.
- It works on **Windows, macOS and Linux immediately** with no per-platform
  build, whereas the frozen/bundled options each need a build per OS and would
  only be testable on the platforms CI actually runs.
- The VS Code extension bundles a pinned CPython runtime because an editor
  extension must not require the user to install Python. A terminal tool's
  users already have (or expect to choose) their own interpreter, so requiring
  one is the conventional, lighter contract — and it is stated plainly below
  rather than hidden.

**Prerequisite that remains:** a Python **3.11–3.14** interpreter
(`requires-python = ">=3.11,<3.15"`). This is the *only* external requirement.
The standalone/bundled alternatives would remove it at the cost of the build
complexity above; they are documented but not built.

## 2. Installation

### a) Run from source (zero install)

A source checkout already contains everything. With any Python 3.11–3.14:

```bash
python interlock_cli.py doctor
```

### b) Install the wheel (provides the `interlock` command)

```bash
python -m build --wheel --no-isolation --outdir dist   # from a checkout
pip install dist/intentlock-4.0.0-py3-none-any.whl
interlock doctor
```

The recovery CLI needs only the standard library, so `--no-deps` also works
and avoids pulling the gateway's server dependencies (fastapi/redis/…):

```bash
pip install --no-deps dist/intentlock-4.0.0-py3-none-any.whl
```

A plain `pip install <wheel>` additionally installs the full `intentlock`
dependency set, because the same distribution also carries the server product.
That is the one bit of weight in this method; a dedicated lean CLI-only
distribution is the natural future refinement (not built here).

After install the `interlock` console script resolves the shared engine from
site-packages and the shared orchestration from `sys.prefix/share/intentlock/python/`
— **no `--engine-root` and no repository checkout required.**

## 3. First run

```text
$ interlock doctor
interlock probe
  Engine:               available
  Engine version:       4.0.0
  Engine root:          ...\venv\Lib\site-packages
  Python:               3.11.9 (...\venv\Scripts\python.exe)
  Support:              tested_primary - Windows x64 + NTFS + Python 3.11.9 ...
```

### Full recovery lifecycle

```bash
# 1. Protect: capture verified recovery evidence (writes a baseline file)
interlock protect --workspace ./proj --resource config.yaml
#    -> Baseline saved: ~/.interlock/baselines/<id>-config.yaml.json
#    -> Use it with: --baseline-file "..."

# 1a. Protect an already-protected file: REFUSED (exit 7), the existing
#     baseline is left byte-for-byte untouched. The last known-good
#     before-state is never replaced by an ordinary capture. To keep a second
#     snapshot, write it to its own file:
interlock protect --workspace ./proj --resource config.yaml \
  --out ~/.interlock/baselines/config.yaml-2026-10-20.json

# 2. Analyze: inspect the workspace + confinement + recovery needs
interlock analyze --workspace ./proj

# 3. Preview: show exactly what recovery would restore (read-only)
interlock preview --workspace ./proj --resource config.yaml \
  --baseline-file <baseline>
#    -> Changed since baseline: yes | Recovery would succeed: yes
#    -> Approval required: yes     | Evidence file: <evidence>

# 4. Recover: apply it — REFUSED (exit 5) without an explicit approver
interlock recover --workspace ./proj --resource config.yaml \
  --baseline-file <baseline> --evidence-file <evidence>
#    -> error: ... (exit 5)

# 5. Recover with explicit approval — restores + independently verifies
interlock recover --workspace ./proj --resource config.yaml \
  --baseline-file <baseline> --evidence-file <evidence> --approved-by you

# 6. Verify: independently confirm the bytes match the baseline
interlock verify --workspace ./proj --resource config.yaml \
  --baseline-file <baseline>
```

### Baseline integrity and replacement policy

- **Every baseline is sealed by the engine.** The engine writes an
  `interlock-baseline-v2` document whose `baseline_hash` is a SHA-256 over the
  canonical JSON of the whole document (workspace, resource, capture time and
  the complete snapshot including the file bytes). The engine re-verifies that
  seal **before** a baseline may be used to plan, preview, recover or verify —
  a modified, truncated or malformed baseline is refused (exit 5 / 7) and is
  never restored into the workspace.
- **A baseline is never replaced by an ordinary capture.** `interlock protect`
  refuses (exit 7) when a baseline already exists at the target path; the
  existing file is preserved byte-for-byte. Use `--out <other-path>` to keep a
  second snapshot, or move the existing file yourself.
- **Legacy baselines are refused, not blessed.** A baseline captured before
  sealing existed (`interlock-baseline-v1`, or any document without a valid
  seal) is rejected with an explicit "capture a new baseline" message. The old
  file is never modified.
- **The seal is an integrity check, not a signature.** It detects corruption and
  edits by an actor who cannot recompute the canonical hash; an actor with write
  access to the baseline store can still recompute a matching hash. Signed
  receipts backed by external key management remain an open item.

`--json` on any command emits the **exact structured envelope the VS Code
extension consumes**, for agents and scripts.

## 4. Operations and exit codes

Friendly names map to the canonical engine commands (the same vocabulary the
extension drives), so nothing is forked:

| Product operation | Engine command | Notes |
|---|---|---|
| `protect` | `capture-baseline` | establishes evidence; writes the baseline file |
| `analyze` | `analyze` | confinement + capability + findings |
| `preview` | `plan` | read-only; produces preview evidence |
| `recover` | `execute` | **requires `--approved-by`**; drift/conflict guarded |
| `verify` | `verify` | independent byte-exact check |
| `status` | `status` | workspace + support verdict |
| `doctor` | `probe` | engine/runtime health |

Exit codes are the engine's own codes (identical to the extension):

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | usage error (bad/unknown command) |
| 3 | engine unavailable |
| 4 | not authorized |
| 5 | refused (e.g. `recover` without `--approved-by`, drift) |
| 6 | verification failed (bytes diverged from baseline) |
| 7 | precondition (e.g. baseline/evidence file missing) |
| 8 | internal error |
| 130 | cancelled (Ctrl-C) |

## 5. Supported platforms

- **Engine portability:** standard-library-only and pathlib-based, so the CLI
  runs anywhere Python 3.11–3.14 runs — Windows, macOS, Linux.
- **Actually tested here:** **Windows x64 / NTFS / Python 3.11.9** (both CLI
  suites below). macOS and Linux are **declared pending CI** exactly as in
  `SUPPORTED_PLATFORMS.md`; they have **not** been executed in this session.
- **Filesystem limits are inherited from the engine:** FAT32/exFAT and
  network/OneDrive-synced directories are **unsupported** (no atomic-replace
  guarantee). See `SAFETY_AND_LIMITATIONS.md`.

Unlike the extension, the CLI has **no bundled runtime**, so it has no
per-platform runtime matrix to provision — but that also means it will not run
where Python is absent.

## 6. Alignment with the VS Code extension

Both interfaces are kept aligned by construction:

- **Same engine** (`app/`, `sdk/`) — recovery decisions are never duplicated.
- **Same orchestration** (`interlock_bridge.py`) — identical `cmd_*` handlers,
  identical exit codes.
- **Same safety policy** — workspace confinement, conflict/drift checks,
  approval-gated execution, independent byte-exact verification.
- **Same version** — `4.0.0` (CLI prints it; `doctor` reports the installed
  engine version so mismatches are visible).

## 7. Independent tests

The CLI is tested **independently of the extension** (a passing extension test
does not prove the CLI works):

| Check | Command | Result (2026-10-21) |
|---|---|---|
| Source lifecycle (help/doctor/protect/analyze/preview/recover/verify/json/confinement/exit-codes) | `python tests/integration/cli_lifecycle_check.py` | **42 passed / 0 failed** (38 before the baseline-integrity work; the extra checks cover the sealed baseline, the refusal to replace an existing baseline and the refusal of a tampered one) |
| Packaged wheel in a fresh venv (no repo, no `--engine-root`, `--no-deps`) | `python tests/integration/cli_clean_install_check.py` | **27 passed / 0 failed** |

Both checks now also run automatically in CI (the `cli-checks` job in
`.github/workflows/ci.yml`), together with the packaging-completeness guard
(`tests/unit/test_packaging_manifest.py`) that fails if the distribution would
ship without the console script or the shared engine command layer.

Static checks on the CLI: `ruff check`, `ruff format --check`, and
`mypy` (strict) all pass.

## 8. Publication status

**Not published.** No PyPI upload, no release artifact, no marketplace
publication has occurred — there is no publisher account or authorization. The
deliverables exist **locally only**:

- `dist/intentlock-4.0.0-py3-none-any.whl` (built and installed into a clean
  venv for the test above)
- `interlock_cli.py` in the working tree

See `INTERLOCK_TWO_INTERFACES_REPORT.md` for the full deliverable list,
prerequisites, and open blockers.
