# INTERLOCK V6 — Supported platforms matrix

Last verified: 2026-10-18 (session: final release readiness). This matrix
records what has been **demonstrated**, what is **declared pending CI**, and
what is **unverified**. Nothing here claims support that has not been
evidenced. A "supported" row means: the declared controlled-beta scope
(filesystem-family recovery on **disposable projects**) has been exercised
end-to-end (install → recovery → independent byte-exact verification) in
that environment.

## Status legend

- **TESTED — PRIMARY**: exercised repeatedly with recorded evidence.
- **DECLARED — CI PENDING**: declared by `requires-python`/deps, encoded in
  the CI matrix (`.github/workflows/ci.yml` → `recovery-cross-platform`),
  but not yet executed (the repository has had no push since 2026-09-27, so
  CI has never run).
- **UNTESTED**: no evidence in any form.
- **UNSUPPORTED**: outside the safety contract (no atomicity guarantee).

## Matrix

| OS / version | Arch | Python | Filesystem | Environment kind | Install | Recovery + integrity | Failure coverage | Status |
|---|---|---|---|---|---|---|---|---|
| Windows 10.0.26300 | x64 | 3.11.9 | NTFS | native, non-elevated | clean venv (157 pkgs, `pip check` clean); **wheel install verified from site-packages** with functional restore smoke | full suite 2922 passed/9 skipped/4 xfailed, exit 0, cov 83.81% (run #3, 3719.82s); recovery subset reproduced across 6 sessions (46 passed/6 skipped latest); demo+recipe SHA-256 reproducible 3×; self-test 4/4 byte-exact | **M1 real process-kill 20/20** (0 torn, 0 invariant violations); **M3 real permission-denial PASS** (original + post-R17 re-run); mocked ENOSPC (not real); 2 symlink drills SKIP (admin); R17 POSIX tests SKIP | **TESTED — PRIMARY** |
| Windows 10/11 | ARM64 | 3.11+ | NTFS | none | — | — | — | UNTESTED (no hardware) |
| Windows (any) | x64 | 3.11.9 | long paths >260 chars | none | — | staging suffix adds 16 chars to target paths; requires `LongPathsEnabled` | — | UNTESTED — limitation |
| Windows | x64 | 3.11.9 | FAT32 / exFAT | none | — | — | — | **UNSUPPORTED** — rename durability/atomicity not guaranteed |
| Windows | x64 | 3.11.9 | network / OneDrive-synced dirs | none | — | — | — | **UNSUPPORTED** — no local atomic-replace guarantees |
| Linux (Ubuntu runner) | x64 | 3.11–3.14 | ext4 | CI runner (planned) | encoded in CI job | encoded (recovery subset) | symlink drills + R17 POSIX tests **will execute** there (unprivileged symlink/chmod semantics) | DECLARED — CI PENDING |
| macOS (runner) | arm64 | 3.11–3.14 | APFS | CI runner (planned) | encoded; **risk cell**: `xmlsec` (via `python3-saml`) wheel availability on arm64 will be proven by the first run | encoded | same as Linux | DECLARED — CI PENDING |
| macOS | x64 | 3.11–3.14 | APFS | none | — | — | — | UNTESTED |

## Declared Python range

`requires-python = ">=3.11,<3.15"` (3.11–3.14). **Locally verified: 3.11.9
only.** 3.12/3.13/3.14 are declared pending the CI matrix; they must not be
marketed as tested until the matrix cells are green with recorded runs.

## Platform-dependent behavior (inspected in code)

- Atomicity: staging files are created **in the target directory**
  (`*.recovery_tmp`) and swapped with `os.replace` — same-volume atomic on
  NTFS/APFS/ext4. Cross-device swaps cannot occur by construction.
- Conflict detection: content-hash compare + `exists()`/`is_symlink()`
  guards; a **micro-second TOCTOU window** between the exists-check and
  `os.replace` remains (a file appearing in that window would be replaced) —
  documented limitation, single-writer assumption.
- Permissions (R17, implemented): staging `os.open(..., 0o600)`, recorded-
  mode-only restore, backup `0o700`/`0o600` POSIX-guarded — enforced and
  **asserted on POSIX only** (4 tests skip on Windows by design).
- Symlinks: staging refuses to follow planted links (`O_EXCL` + pre-unlink);
  the 2 escaping drills execute only where symlink creation is permitted
  (POSIX runners; Windows needs elevation).
- Timestamps: capture stores both float and ns keys; both restore paths have
  live code (verified this session — a suspected dead-branch defect was
  **retracted after inspection**).
- Case sensitivity: engine compares bytes/hashes, not names; case-insensitive
  filesystems behave as the OS does.
- Unicode/long paths: `pathlib` throughout; byte-exact content travels as
  base64 (encoding-independent); >260-char paths on Windows untested.
- Disk-full: typed fail-closed verified only via mocks; the **real ENOSPC
  drill (M2) is prepared and authorization-gated** (never executed).

## What "supported" excludes everywhere

Production databases, migrations, in-use files, live-user data, cross-device
moves, network shares, and any promise of zero data loss. See
`docs/operations/SAFETY_AND_LIMITATIONS.md`.
