# Interlock V6 — macOS Installation (Apple Silicon)

Status: **prepared, NOT yet natively validated.** This document is the
authorized macOS install procedure. No macOS download button is enabled
anywhere until the release gate below is fully satisfied (native macOS
build → clean install → native recovery tests → published artifact).
Last verified: 2026-10-19 on a Windows host by static audit, dependency
wheel-resolution against PyPI, and wheel-level functional testing; native
macOS execution is pending the `recovery-cross-platform` and
`macos-release-artifact` CI jobs (`.github/workflows/ci.yml`) or a real
Mac run of this document.

## What "installing Interlock" means on macOS

Interlock is a **Python library/service** (FastAPI + SDK + recovery
engine), not a graphical `.app`. There is nothing to drag into
`/Applications` and no installer package. Installation means: create a
Python virtual environment and install the `intentlock` wheel into it.
Because it is imported by your own Python interpreter, **Gatekeeper does
not show a "downloaded from the internet" dialog** for it; there is no
macOS code-signing or notarization step for a pip-installed pure-Python
wheel. Interlock is **not signed or notarized** — we do not claim
otherwise.

## Supported macOS scope (honest status)

| Item | Status |
|---|---|
| Architecture | **Apple Silicon (arm64)** — all 58 locked dependencies verified to publish `macosx_11_0_arm64` wheels (incl. the risky binaries: `xmlsec`, `cryptography` (abi3), `psycopg2-binary`, `lxml`, `pydantic-core`, `bcrypt`, `greenlet`, `uvloop`); cp311 **and** cp314 wheels confirmed |
| macOS version | **11.0 or newer** is the dependency floor (arm64 wheels target `macosx_11_0`); the *tested* minimum is **not yet established** — no native run has happened. CI targets `macos-latest` |
| Python | 3.11–3.14 declared (`requires-python >=3.11,<3.15`); locally verified on 3.11.9 and 3.14.7 (Windows); macOS CI matrix covers 3.11–3.14 |
| Intel (x86_64) | **UNSUPPORTED for now** — upstream `cryptography` ≥46 publishes **no macOS x86_64 wheel**, so the pinned lock cannot install on Intel without a source toolchain (Rust/OpenSSL). Enabling Intel later requires an owner-approved dependency change (e.g. `cryptography` ≤45) plus native validation |
| Filesystems | APFS recommended. FAT32/exFAT/network-synced folders are **unsupported** (no atomic-replace guarantees), same as on Windows |

## Install from the release wheel (recommended)

```bash
# 1. Prerequisites: Xcode Command Line Tools (xcode-select --install),
#    Python 3.11+ (python.org or Homebrew), ~300 MB disk.

# 2. Verify the artifact checksum you were given (SHA-256):
shasum -a 256 intentlock-4.0.0-py3-none-any.whl
#    Must match the SHA-256 published on the download page / release notes.

# 3. Create and enter a clean environment.
python3 -m venv .intentlock-venv
source .intentlock-venv/bin/activate
python -m pip install --upgrade pip

# 4. Install the wheel (no network access is needed afterwards).
pip install intentlock-4.0.0-py3-none-any.whl

# 5. Verify the installation imports from site-packages.
python - <<'PY'
import app.infrastructure.recovery.filesystem_recovery_adapter as m
assert "site-packages" in m.__file__, m.__file__
from app.domain.services.tool_security import ToolArgumentValidator
print("Interlock installed OK:", m.__file__)
PY
```

## Full-parity install (includes optional SAML support)

The wheel reflects `pyproject.toml` and does **not** include the optional
SAML stack (`python3-saml`, `xmlsec`, `authlib`, `typer`) — a known
packaging inconsistency (the compiled `requirements.txt` lock does). If you
need `ProductionSAMLAdapter`, install the lock instead:

```bash
python3 -m venv .intentlock-venv
source .intentlock-venv/bin/activate
pip install -r requirements.txt
```

## First recovery run

Follow `docs/operations/BETA_FIRST_RUN.md` verbatim: use a **disposable
project directory**, run the engine self-test, perform a modify → recover
cycle, and independently compare restored bytes (SHA-256) with your
baseline. On macOS the symlink-confinement drills and the POSIX permission
(R17) tests run natively (no elevation needed).

## Uninstall / upgrade

```bash
pip uninstall intentlock          # remove the package
rm -rf .intentlock-venv           # remove the environment entirely
# Upgrade: pip install the newer wheel over the old one, or recreate the venv.
```

## Known limitations (macOS)

- Native macOS recovery/kill/permission evidence is **pending** — do not
  treat this document as validation. CI (macos-latest) runs the recovery
  subset, symlink drills, and R17 permission tests on every authorized push.
- The real disk-full drill (M2) has been executed on **no** operating
  system; ENOSPC behavior is verified only via mocks.
- APFS is case-insensitive by default; the engine compares content hashes,
  not names, but a case-only rename may behave as a same-file update.
- No code signing / notarization exists for the wheel.
