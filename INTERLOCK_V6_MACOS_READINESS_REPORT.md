# INTERLOCK V6 — macOS Availability Readiness Report

Date: 2026-10-19. Mission: make Interlock genuinely installable by macOS
users. Every claim cites evidence; nothing native-macOS is claimed because
no macOS host has been used. Evidence dir: `logs/v6_macos_20261019T/`.

---

## 1. Files changed and reasons

| Path | State before | Change | Why |
|---|---|---|---|
| `app/domain/services/tool_security.py` | clean at HEAD `624171e` | `validate_path` now rejects absolute paths of **both** path flavours (`ntpath.isabs` OR `posixpath.isabs`) + explanatory comment (diff: 11+/1−) | **macOS-breaking security defect**: platform-dependent verdicts accepted `C:\...` on POSIX and `/...` on Windows/Py3.14 |
| `tests/unit/test_tool_security.py` | clean at HEAD | +2 cross-platform regression tests (23+): both-flavour absolutes rejected everywhere; relative paths still accepted | TDD red-first proof (see §3) |
| `docs/operations/SUPPORTED_PLATFORMS.md` | clean at HEAD (committed 2026-10-18) | macOS arm64 row → dependency-resolved; new **macOS Intel = UNSUPPORTED** row; Python row → 3.11.9 **and** 3.14.7 verified; platform-behavior note for the fix | keep the matrix matching evidence |
| `.github/workflows/ci.yml` | **pre-existing modified** (mixed file, as before) | +separate `macos-release-artifact` job (YAML-validated; 3 jobs total) | real macOS build + hash + artifact upload + native tests on push |
| `docs/operations/MACOS_INSTALL.md` | new | authorized macOS install procedure (arm64, wheel or full-parity lock, uninstall, limitations, honest validation status) | §3 deliverable |
| `downloads/index.html`, `downloads/README.md` | new | standalone platform-download section: honest badges, checksums, no fake URLs, no fake waitlist + integration notes for when `web/` returns | §7 deliverable (see §7 note) |

No commit/stage/push/publish was performed (not authorized this mission).

## 2. macOS compatibility fixes

- **Fixed (real, cross-platform):** `ToolArgumentValidator.validate_path`
  used `os.path.isabs`, whose verdict depends on the host OS (and changed
  again in Python 3.14). Consequence on macOS: the existing absolute-path
  rejection test fails, and the *security* verdict for `C:\...` input was
  "accepted as relative". Now absolute under either flavour is rejected on
  every platform. Verified strictly stronger on every OS (no input that was
  previously rejected is now accepted).
- **Static audit result:** zero Windows-only API usage in `app/` or `sdk/`
  (no `os.name=="nt"`, `sys.platform` branches, `shell=True`, `.exe`,
  `msvcrt/windll`, `O_BINARY`, hardcoded `C:\`). The engine is platform-
  neutral by construction (`pathlib`, same-directory staging + `os.replace`
  = same-volume atomic on APFS/ext4/NTFS; R17 `0o600`/`0o700` modes are
  POSIX-correct on macOS). `subprocess` appears only in `scripts/generate_sbom.py`.
- **Dependency resolution (real PyPI wheel evidence, no Mac needed):** all 58
  locked pins publish `macosx_11_0_arm64` wheels — including every
  build-time risk (`xmlsec 1.3.17`, `cryptography 50` abi3, `psycopg2-binary`,
  `lxml`, `pydantic-core`, `bcrypt`, `greenlet`, `uvloop`); `pydantic-core`,
  `psycopg2`, `lxml`, `xmlsec`, `greenlet`, `uvloop` also publish **cp314**
  arm64 wheels.
- **Intel macOS found dependency-blocked (honest scope cut):** `cryptography`
  ≥46 ships **no x86_64 macOS wheel** (PyPI file listing verified); ≤45 does.
  macOS target = **Apple Silicon only** until an owner approves a pin change
  plus native validation.

## 3. Test commands, results, exit codes (all on Windows; see §4)

| # | Command | Result | Exit |
|---|---|---|---|
| 1 | `pytest tests/unit/test_tool_security.py` **pre-fix**, py3.14.7 (`.venv314`) | **1 failed, 58 passed** (new test: `/etc/passwd` not rejected — the 3.14 `ntpath.isabs` change) | 1 |
| 2 | same pre-fix, py3.11.9 (`.venv`) | 59 passed (POSIX failure is by-inspection; CI-proven pending push) | 0 |
| 3 | same **post-fix**, py3.11.9 / py3.14.7 | **59 passed / 59 passed** | 0 / 0 |
| 4 | recovery+security subset (adapter, fault-injection, backup drill, tool security), py3.11.9 | **105 passed, 6 skipped**, 62.44 s | 0 |
| 5 | same subset, py3.14.7 | **105 passed, 6 skipped**, 61.16 s | 0 |
| 6 | `ruff check app sdk` · `bandit -r app -ll` · `mypy app` | clean · 0 issues · "no issues in 311 files" | 0 / 0 / 0 |
| 7 | `pip download --only-binary :all: --platform macosx_11_0_arm64` (58 pins, cp311) | **all wheels found** | 0 |
| 8 | same, cp314 arm64, per-ABI pins (6 pkgs) | all wheels found | 0 |
| 9 | `cryptography=={45.0.5,44.0.2,43.0.3}` x86_64 probe | all WHEEL_OK (Intel path exists at ≤45) | 0 |
| 10 | `python -m build` | wheel 579.8 KB + sdist 438.8 KB | 0 |
| 11 | clean-venv wheel install → `pip check` → neutral-cwd site-packages import → security assertions → functional recovery smoke | all PASS (byte-exact restore, zero residue, 3 absolutes rejected) | 0 |
| 12 | `yaml.safe_load(ci.yml)` | YAML_OK, 3 jobs | 0 |

The 6 skips are environment-bound and **never counted as passing**: 4 R17
POSIX permission tests, 2 privileged symlink drills — all of which *execute*
natively on the macOS/Linux CI runners.

## 4. Native CI evidence

**None yet — honestly.** The workflow now contains three jobs
(`lint-and-test`, `recovery-cross-platform` incl. `macos-latest`, and the new
`macos-release-artifact` on `macos-latest`), YAML-validated locally. The
repository has had **no push since 2026-09-27**, so no workflow has ever run
and there is no run URL or run result to report. Native macOS evidence
requires the owner's explicit authorization to push. Until then,
macOS-native test results are **BLOCKED**, not passing.

## 5. Installer location, architecture, SHA-256

- Product architecture: **CLI/API/library** (no GUI) → the installable is the
  pure-Python wheel, not a `.dmg`/`.app`. Location (local, not published):
  `C:\Users\Dell\AppData\Local\Temp\opencode\v6_mac_build\intentlock-4.0.0-py3-none-any.whl`
- Tag `py3-none-any`: installs on macOS 11+ **arm64**, Windows x64, Linux.
- SHA-256: `1e76d1f4acc38a3058f6b4dbb15821c0e809f450b29aa55e1ba5680968ff7f2e`
  (sdist `d1f758abc704f0187519bb02d45f08f9e76af9c9bdb2fb63ce6da56a0ce6d61a`);
  built from working tree at HEAD `624171e` + the uncommitted campaign
  changes listed in `INTERLOCK_V6_RELEASE_READINESS_REPORT.md` §4.
  Reproduce: `python -m build --outdir <dir>` on any clean checkout.
- Proven by test #11 that the installed copy (not the source tree) carries
  the security fix and performs byte-exact recovery. macOS-native
  install/run remains pending §4.

## 6. Signing / notarization status

**Not signed, not notarized — and not claimable.** Interlock ships as a
pip-installed pure-Python wheel: Apple notarization applies to apps/executables
distributed outside the App Store context; a venv-installed Python package
triggers no Gatekeeper dialog. If a future `.app`/CLI-binary packaging is
chosen (PyInstaller etc.), signing + notarization become mandatory and need
owner-provided Apple credentials — never committed to the repo. No
certificates, keys, or tokens were touched this mission.

## 7. Website changes and download URL

- **No verified download URL exists, so none is shown.** Publishing was not
  authorized; there is no artifact hosting destination (PyPI, GitHub
  Release, or web server) — a "download" link would be fake.
- The Next.js site `web/` is **absent from the working tree** (60
  pre-existing deletions preserved, per mission rules — restoring it would
  discard that user work). Therefore the platform-download section was
  created as a standalone page: `downloads/index.html` (Windows x64 =
  "verified, not hosted" + SHA-256; macOS arm64 = **"Validation in
  progress"**, no button, no fake waitlist; macOS Intel = unsupported; Linux
  = declared/not validated), plus `downloads/README.md` with drop-in
  integration notes for when `web/` returns.

## 8. Remaining blockers and exact next steps

Release gate status (all must be green before "macOS available"):

| Criterion | Status |
|---|---|
| Native macOS build succeeds | **BLOCKED** (job prepared; needs push authorization) |
| Clean macOS install + startup | **BLOCKED** (procedure ready: `docs/operations/MACOS_INSTALL.md`) |
| Native macOS recovery + safety tests pass | **BLOCKED** (tests prepared in CI; 6 skips become real runs there) |
| Artifact downloadable from intended destination | **BLOCKED** (no hosting authorized; no destination chosen) |
| Instructions + limitations published | prepared locally (`MACOS_INSTALL.md`, `downloads/`) — publication blocked |
| Signing/notarization accurately disclosed | ✓ disclosed as unsigned/unnotarized |

Exact next steps:
1. **Authorize the push** to the existing `origin` → the three CI jobs run;
   `macos-release-artifact` produces + hashes + uploads a real macOS build,
   and the macOS cells of `recovery-cross-platform` produce native recovery,
   symlink, and R17 evidence. Report the run URL/result verbatim.
2. **Choose and authorize a publication destination** (GitHub Release asset
   and/or PyPI) → enable the download button in `downloads/index.html` with
   the published URL + checksum.
3. **Real-Mac validation**: either the CI evidence above or a volunteer/owner
   Mac executing `docs/operations/MACOS_INSTALL.md` verbatim (disposable
   projects only) — closes the "clean install + startup" criterion with
   first-hand evidence.
4. Optional, separate approval: pin `cryptography` ≤45 to unlock Intel macOS
   (trade-off: older crypto pin) — otherwise keep Intel unsupported.
