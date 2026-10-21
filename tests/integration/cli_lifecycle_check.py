"""Independent lifecycle check for the Interlock Terminal Runner (CLI).

This exercises ``interlock_cli.py`` end to end as a real subprocess, WITHOUT
the VS Code extension, to prove the terminal interface works on its own and
drives the shared engine. It is intentionally separate from the extension's
``bridge_integration.py``/clean-environment checks: a passing extension test
does not prove the CLI works, and vice versa.

Run with any Python 3.11-3.14 (the engine is standard-library-only):

    .venv\\Scripts\\python.exe tests\\integration\\cli_lifecycle_check.py

Exit code 0 = every check passed; 1 = at least one failed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "interlock_cli.py"
PYTHON = sys.executable

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


def run_cli(*args: str, workspace: Path | None = None) -> tuple[int, str, str]:
    env = {**os.environ, "NO_COLOR": "1"}
    env.pop("INTERLOCK_BRIDGE", None)
    proc = subprocess.run(
        [PYTHON, str(CLI), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=180,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    global passed, failed
    tmp = Path(tempfile.mkdtemp(prefix="interlock-cli-"))
    workspace = tmp / "workspace"
    workspace.mkdir()
    target = workspace / "config.yaml"
    original = b"name: interlock\nversion: 1\nprotected: true\n"
    target.write_bytes(original)

    print("== CLI help and version ==")
    code, out, _ = run_cli("--help")
    check("help exits 0", code == 0, f"code={code}")
    check(
        "help lists the product operations",
        all(op in out for op in ("protect", "preview", "recover", "verify")),
    )
    code, out, _ = run_cli("--version")
    check("version exits 0 and prints a version", code == 0 and "4.0.0" in out, out[:80])

    print("== doctor (engine health, no workspace needed) ==")
    code, out, _ = run_cli("doctor")
    check("doctor exit 0", code == 0, f"code={code}")
    check("doctor reports the engine available", "Engine:" in out and "available" in out)

    print("== protect (capture baseline) ==")
    code, out, _ = run_cli("protect", "--workspace", str(workspace), "--resource", "config.yaml")
    check("protect exit 0", code == 0, f"code={code} :: {_stderr(out)}")
    check("protect shows the baseline hash", "Baseline sha256" in out)
    baseline_line = next((ln for ln in out.splitlines() if "Baseline saved:" in ln), "")
    baseline_file = baseline_line.split("Baseline saved:", 1)[1].strip() if baseline_line else ""
    check(
        "protect persisted a baseline file",
        bool(baseline_file) and Path(baseline_file).is_file(),
        baseline_line,
    )
    if baseline_file and Path(baseline_file).is_file():
        doc = json.loads(Path(baseline_file).read_text(encoding="utf-8"))
        check(
            "baseline document format is interlock-baseline-v2",
            doc.get("format") == "interlock-baseline-v2",
        )
        check(
            "baseline document carries an integrity seal",
            bool(doc.get("baseline_hash")) and doc.get("baseline_hash_spec") == "v1",
        )
        snapshot = doc.get("snapshot") or {}
        check(
            "baseline snapshot holds the exact bytes", isinstance(snapshot.get("content_b64"), str)
        )
        if isinstance(snapshot.get("content_b64"), str):
            decoded = __import__("base64").b64decode(snapshot["content_b64"])
            check("baseline bytes are byte-identical", decoded == original)
            check(
                "baseline bytes hash to the recorded hash",
                hashlib.sha256(decoded).hexdigest() == snapshot.get("hash"),
            )
        check(
            "baseline stored outside the project", not str(baseline_file).startswith(str(workspace))
        )
        original_baseline_bytes = Path(baseline_file).read_bytes()

        print("== a second protect must not replace the existing baseline ==")
        code2, out2, _ = run_cli(
            "protect", "--workspace", str(workspace), "--resource", "config.yaml"
        )
        check(
            "second protect is refused (exit 7)",
            code2 == 7,
            f"code={code2} :: {_stderr(out2)}",
        )
        check(
            "the existing baseline is preserved byte-for-byte",
            Path(baseline_file).read_bytes() == original_baseline_bytes,
        )

        print("== a tampered baseline must be refused ==")
        tampered = dict(doc)
        tampered["snapshot"] = dict(snapshot)
        tampered["snapshot"]["content_b64"] = __import__("base64").b64encode(
            b"TAMPERED = 2\n"
        ).decode("ascii")
        tampered_path = Path(baseline_file).with_name("tampered-baseline.json")
        tampered_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
        code3, out3, _ = run_cli(
            "preview",
            "--workspace",
            str(workspace),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(tampered_path),
        )
        check(
            "preview refuses a tampered baseline (exit 5)",
            code3 == 5,
            f"code={code3} :: {_stderr(out3)}",
        )
        tampered_path.unlink(missing_ok=True)

    print("== analyze ==")
    code, out, _ = run_cli("analyze", "--workspace", str(workspace))
    check("analyze exit 0", code == 0, f"code={code}")
    check("analyze reports confinement", "Confinement" in out and "pass" in out)

    print("== preview while unchanged ==")
    code, out, _ = run_cli(
        "preview",
        "--workspace",
        str(workspace),
        "--resource",
        "config.yaml",
        "--baseline-file",
        baseline_file,
    )
    check("preview exit 0", code == 0, f"code={code} :: {_stderr(out)}")
    check("preview reports no change", "Changed since baseline" in out and "no" in out)

    print("== damage the file, preview again ==")
    damaged = b"AGENT OVERWROTE \x00\xff BYTES"
    target.write_bytes(damaged)
    code, out, _ = run_cli(
        "preview",
        "--workspace",
        str(workspace),
        "--resource",
        "config.yaml",
        "--baseline-file",
        baseline_file,
    )
    check("preview exit 0 after damage", code == 0, f"code={code}")
    check("preview detects the change", "Changed since baseline" in out and "yes" in out)
    check("preview says recovery would succeed", "Recovery would succeed" in out and "yes" in out)
    check("preview requires approval", "Approval required" in out and "yes" in out)
    evidence_line = next((ln for ln in out.splitlines() if "Evidence file:" in ln), "")
    evidence_file = evidence_line.split("Evidence file:", 1)[1].strip() if evidence_line else ""
    check(
        "preview wrote an evidence file",
        bool(evidence_file) and Path(evidence_file).is_file(),
        evidence_line,
    )
    check("preview is read-only (damage still present)", target.read_bytes() == damaged)

    print("== recover without approval must be refused ==")
    code, out, err = run_cli(
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
    check(
        "recover without --approved-by is refused (exit 5)",
        code == 5,
        f"code={code} :: {err[:200]}",
    )
    check("file untouched after refusal", target.read_bytes() == damaged)

    print("== recover with explicit approval ==")
    code, out, err = run_cli(
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
        "cli-lifecycle-check",
    )
    check("recover exit 0", code == 0, f"code={code} :: {err[:200]}")
    check("recover reports byte-exact", "Byte-exact" in out and "yes" in out)
    check("recover reports engine-verified", "Engine verified" in out and "yes" in out)
    check("file restored byte-for-byte", target.read_bytes() == original)

    print("== verify ==")
    code, out, _ = run_cli(
        "verify",
        "--workspace",
        str(workspace),
        "--resource",
        "config.yaml",
        "--baseline-file",
        baseline_file,
    )
    check("verify exit 0", code == 0, f"code={code}")
    check("verify reports success", "Verified" in out)

    print("== verify when the file diverges ==")
    target.write_bytes(b"changed again")
    code, out, _ = run_cli(
        "verify",
        "--workspace",
        str(workspace),
        "--resource",
        "config.yaml",
        "--baseline-file",
        baseline_file,
    )
    check("diverged verify exits 6 (verification failed)", code == 6, f"code={code}")

    print("== --json machine output ==")
    code, out, _ = run_cli(
        "verify",
        "--workspace",
        str(workspace),
        "--resource",
        "config.yaml",
        "--baseline-file",
        baseline_file,
        "--json",
    )
    try:
        envelope = json.loads(out)
        check("--json emits a parseable engine envelope", True)
        check("--json envelope marks ok=false on divergence", envelope.get("ok") is False)
        check("--json envelope carries the engine command", envelope.get("command") == "verify")
    except Exception as exc:  # noqa: BLE001
        check("--json emits a parseable engine envelope", False, f"{exc} :: {out[:160]}")

    print("== workspace confinement ==")
    sentinel = tmp / "outside.txt"
    sentinel.write_text("intact", encoding="utf-8")
    code, _, _ = run_cli("protect", "--workspace", str(workspace), "--resource", "../outside.txt")
    check("parent traversal is refused", code != 0, f"code={code}")
    check(
        "sentinel outside the workspace is intact", sentinel.read_text(encoding="utf-8") == "intact"
    )

    print("== unknown command / usage ==")
    code, _, _ = run_cli("frobnicate")
    check("unknown command exits 2 (usage)", code == 2, f"code={code}")

    # Cleanup private storage we created for this run.
    try:
        if baseline_file and Path(baseline_file).is_file():
            Path(baseline_file).unlink()
    except Exception:  # noqa: BLE001, S110 - best-effort private-storage cleanup
        pass

    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def _stderr(text: str) -> str:
    return text.replace("\n", " ")[:160]


if __name__ == "__main__":
    sys.exit(main())
