"""Clean-environment install check for the Interlock Terminal Runner (CLI).

Builds/uses the ``intentlock`` wheel, installs it into a FRESH virtualenv with
``--no-deps`` (the recovery CLI's import closure is standard-library-only, so
the gateway's fastapi/redis/... deps are NOT required), then drives the
installed ``interlock`` console script from a temporary working directory with
NO repository on ``sys.path`` and NO ``INTERLOCK_BRIDGE`` override.

This proves the packaged CLI artifact is self-contained (outside of the Python
interpreter itself) and independent of both the source checkout and the VS Code
extension. It deliberately does NOT reuse any result from the extension's tests.

Run:  .venv\\Scripts\\python.exe tests\\integration\\cli_clean_install_check.py
Exit: 0 = all checks passed; 1 = at least one failed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "dist"

passed = 0
failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f"  :: {detail}" if detail else ""))


def run(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int = 180) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(cwd), env=env, timeout=timeout
    )
    return proc.returncode, proc.stdout, proc.stderr


def find_wheel() -> Path:
    wheels = sorted(DIST.glob("intentlock-*.whl"), key=lambda p: p.stat().st_mtime)
    if wheels:
        return wheels[-1]
    # Build one on demand (offline: --no-isolation uses the current setuptools).
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(DIST)],
        cwd=str(REPO),
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = sorted(DIST.glob("intentlock-*.whl"), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise SystemExit("no wheel produced")
    return wheels[-1]


def main() -> int:
    global passed, failed
    wheel = find_wheel()
    print(f"== wheel under test: {wheel.name} ({wheel.stat().st_size} bytes)")

    tmp = Path(tempfile.mkdtemp(prefix="interlock-cli-clean-"))
    venv = tmp / "venv"
    try:
        # 1. Fresh virtualenv.
        print("== creating a clean virtualenv ==")
        code, _, err = run([sys.executable, "-m", "venv", str(venv)], tmp, os.environ.copy(), 300)
        check("venv created", code == 0, err[-300:])
        if code != 0:
            return 1

        if os.name == "nt":
            vpy = venv / "Scripts" / "python.exe"
            vscript = venv / "Scripts" / "interlock.exe"
        else:
            vpy = venv / "bin" / "python"
            vscript = venv / "bin" / "interlock"

        # 2. Install the wheel with --no-deps (CLI needs only the stdlib).
        print("== installing the wheel (--no-deps, offline) ==")
        code, _, err = run(
            [str(vpy), "-m", "pip", "install", "--no-deps", "--quiet", str(wheel)],
            tmp,
            os.environ.copy(),
            300,
        )
        check("wheel installed into the clean venv", code == 0, err[-400:])
        if code != 0:
            return 1
        check("interlock console script exists", vscript.exists(), str(vscript))

        # 3. The bridge must be resolvable from the venv's own prefix.
        bridge_in_venv = venv / "share" / "intentlock" / "python" / "interlock_bridge.py"
        check(
            "shared bridge bundled inside the venv prefix",
            bridge_in_venv.is_file(),
            str(bridge_in_venv),
        )

        # 4. Environment: NO repo on the path, NO INTERLOCK_BRIDGE, cwd = temp.
        workroot = tmp / "cwd"
        workroot.mkdir(exist_ok=True)
        workspace = tmp / "workspace"
        workspace.mkdir()
        target = workspace / "config.yaml"
        original = b"name: interlock\nversion: 1\nprotected: true\n"
        target.write_bytes(original)

        env = {k: v for k, v in os.environ.items() if k not in ("INTERLOCK_BRIDGE", "PYTHONPATH")}
        env["NO_COLOR"] = "1"

        def cli(*args: str) -> tuple[int, str, str]:
            return run([str(vscript), *args], workroot, env)

        # 5. Drive the installed CLI through a full lifecycle.
        print("== installed CLI: help / version ==")
        code, out, _ = cli("--help")
        check("help exits 0", code == 0, f"code={code}")
        check(
            "help lists protect/preview/recover/verify",
            all(op in out for op in ("protect", "preview", "recover", "verify")),
        )

        print("== installed CLI: doctor (engine from site-packages, no --engine-root) ==")
        code, out, _ = cli("doctor")
        check("doctor exit 0", code == 0, f"code={code}")
        check("engine reported available", "Engine:" in out and "available" in out)
        check("installed engine version 4.0.0", "4.0.0" in out, out[:200])

        print("== installed CLI: protect ==")
        code, out, _ = cli("protect", "--workspace", str(workspace), "--resource", "config.yaml")
        check("protect exit 0", code == 0, f"code={code} :: {out[-200:]}")
        bl = next((ln for ln in out.splitlines() if "Baseline saved:" in ln), "")
        baseline_file = bl.split("Baseline saved:", 1)[1].strip() if bl else ""
        check("baseline persisted", bool(baseline_file) and Path(baseline_file).is_file(), bl)
        if baseline_file and Path(baseline_file).is_file():
            doc = json.loads(Path(baseline_file).read_text(encoding="utf-8"))
            snap = doc.get("snapshot") or {}
            decoded = base64.b64decode(snap.get("content_b64", ""))
            check("baseline bytes byte-identical", decoded == original)
            check(
                "baseline hash matches bytes",
                hashlib.sha256(decoded).hexdigest() == snap.get("hash"),
            )
            check(
                "baseline stored outside the workspace",
                not str(baseline_file).startswith(str(workspace)),
            )

        print("== installed CLI: preview -> recover -> verify ==")
        target.write_bytes(b"damaged by an agent \x00\xff")
        code, out, _ = cli(
            "preview",
            "--workspace",
            str(workspace),
            "--resource",
            "config.yaml",
            "--baseline-file",
            baseline_file,
        )
        check("preview exit 0", code == 0, f"code={code}")
        check(
            "preview detects change + approval required",
            "Changed since baseline" in out and "Approval required" in out,
        )
        ev = next((ln for ln in out.splitlines() if "Evidence file:" in ln), "")
        evidence_file = ev.split("Evidence file:", 1)[1].strip() if ev else ""
        check("evidence file written", bool(evidence_file) and Path(evidence_file).is_file(), ev)

        code, _, err = cli(
            "recover",
            "--workspace",
            str(workspace),
            "--resource",
            "config.yaml",
            "--baseline-file",
            baseline_file,
            "--evidence-file",
            evidence_file,
        )
        check("recover without approval refused (exit 5)", code == 5, f"code={code} :: {err[:200]}")

        code, out, err = cli(
            "recover",
            "--workspace",
            str(workspace),
            "--resource",
            "config.yaml",
            "--baseline-file",
            baseline_file,
            "--evidence-file",
            evidence_file,
            "--approved-by",
            "clean-install-check",
        )
        check("recover with approval exit 0", code == 0, f"code={code} :: {err[:200]}")
        check("recover reports byte-exact", "Byte-exact" in out and "yes" in out)
        check("file restored byte-for-byte", target.read_bytes() == original)

        code, out, _ = cli(
            "verify",
            "--workspace",
            str(workspace),
            "--resource",
            "config.yaml",
            "--baseline-file",
            baseline_file,
        )
        check("verify exit 0 + success", code == 0 and "Verified" in out, f"code={code}")

        target.write_bytes(b"diverged")
        code, out, _ = cli(
            "verify",
            "--workspace",
            str(workspace),
            "--resource",
            "config.yaml",
            "--baseline-file",
            baseline_file,
            "--json",
        )
        check("diverged verify exits 6 with parseable --json", code == 6, f"code={code}")
        try:
            env_json = json.loads(out)
            check("--json envelope ok=false on divergence", env_json.get("ok") is False)
        except Exception as exc:  # noqa: BLE001
            check("--json envelope ok=false on divergence", False, str(exc))

        print("== installed CLI: confinement + usage ==")
        sentinel = tmp / "outside.txt"
        sentinel.write_text("intact", encoding="utf-8")
        code, _, _ = cli("protect", "--workspace", str(workspace), "--resource", "../outside.txt")
        check("parent traversal refused", code != 0, f"code={code}")
        check("outside sentinel intact", sentinel.read_text(encoding="utf-8") == "intact")
        code, _, _ = cli("frobnicate")
        check("unknown command exit 2", code == 2, f"code={code}")

        # Cleanup the private evidence we wrote for this run.
        try:
            if baseline_file and Path(baseline_file).is_file():
                Path(baseline_file).unlink()
        except Exception:  # noqa: BLE001, S110 - best-effort private-storage cleanup
            pass

        print(f"\nRESULT: {passed} passed, {failed} failed")
        return 0 if failed == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
