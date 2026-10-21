"""Real-engine integration driver for the VS Code extension's Python bridge.

Exercises ``extensions/vscode/python/interlock_bridge.py`` against the REAL
Interlock engine (no mocks, no stubs): probe/status/analyze, confinement
refusals, baseline capture, preview -> approval-gated execute, independent
byte-exact verification, human-edit conflict refusal, and tampered-evidence
rejection.

Run with the engine's interpreter:

    .venv\\Scripts\\python.exe extensions\\vscode\\test\\integration\\bridge_integration.py

Exit code 0 means every check passed; 1 means at least one check failed.
Paths are derived from this file's location (no hardcoded machine paths).
"""

# ruff: noqa: T201 - this is a CLI test driver: progress is reported on stdout.

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# .../extensions/vscode/test/integration/bridge_integration.py -> repo root
REPO = Path(__file__).resolve().parents[4]
PYTHON = Path(os.environ.get("INTERLOCK_PYTHON", str(REPO / ".venv" / "Scripts" / "python.exe")))
BRIDGE = Path(__file__).resolve().parents[2] / "python" / "interlock_bridge.py"


def _load_bridge_module() -> Any:
    """Import the bridge module itself (it is the engine's sealing authority)."""
    spec = importlib.util.spec_from_file_location("interlock_bridge_for_test", BRIDGE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seal_baseline_document = _load_bridge_module().seal_baseline_document

FAILURES: list[str] = []
PASSES = 0


def run(args: list[str]) -> tuple[int, dict, str]:
    cmd = [str(PYTHON), str(BRIDGE), *args]
    # noqa: S603 is on the call below: fixed interpreter + fixed script path.
    proc = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    env: dict = {}
    if proc.stdout.strip():
        try:
            env = json.loads(proc.stdout)
        except ValueError:
            env = {"_parse_error": True, "_raw": proc.stdout[:400]}
    return proc.returncode, env, proc.stderr


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSES
    if cond:
        PASSES += 1
        print(f"  PASS  {label}")
    else:
        FAILURES.append(f"{label} :: {detail}")
        print(f"  FAIL  {label} :: {detail}")


def main() -> int:
    if not PYTHON.is_file():
        print(f"engine interpreter not found: {PYTHON}", file=sys.stderr)
        return 1
    if not BRIDGE.is_file():
        print(f"bridge script not found: {BRIDGE}", file=sys.stderr)
        return 1

    ws = Path(tempfile.mkdtemp(prefix="il_bridge_ws_"))
    outside = ws.parent / "il_bridge_outside.txt"
    outside.write_bytes(b"OUTSIDE-MUST-NOT-CHANGE")
    target = ws / "config.yaml"
    original = b"server:\n  host: localhost\n  port: 8080\n"
    target.write_bytes(original)
    base_hash = hashlib.sha256(original).hexdigest()
    engine_root = ["--engine-root", str(REPO)]

    print("== probe / status / analyze ==")
    code, env, err = run(["probe", *engine_root])
    check("probe exit 0", code == 0, f"code={code} err={err[:200]}")
    check("probe envelope", env.get("ok") is True and env.get("command") == "probe", str(env)[:300])
    check(
        "probe engine available",
        env.get("result", {}).get("engine", {}).get("available") is True,
        str(env)[:300],
    )
    check(
        "probe python range",
        env.get("result", {}).get("python", {}).get("in_supported_range") is True,
        str(env),
    )

    code, env, err = run(["probe", "--engine-root", str(ws / "nope")])
    check("bad engine root exit 3", code == 3, f"code={code}")
    check(
        "bad engine root kind",
        env.get("error", {}).get("kind") == "engine_unavailable",
        str(env)[:200],
    )

    code, env, err = run(["status", "--workspace", str(ws), *engine_root])
    check("status exit 0", code == 0, f"code={code} err={err[:300]}")
    res = env.get("result") or {}
    check(
        "status incident history honest",
        res.get("incident_history", {}).get("available") is False,
        str(res)[:300],
    )
    check(
        "status workspace authorized",
        res.get("workspace", {}).get("authorized") is True,
        str(res)[:300],
    )

    code, env, err = run(["analyze", "--workspace", str(ws), *engine_root])
    check("analyze exit 0", code == 0, f"code={code} err={err[:400]}")
    res = env.get("result") or {}
    check(
        "confinement probes pass",
        res.get("confinement_pass") is True,
        json.dumps(res.get("confinement_probes"))[:400],
    )
    probes = {p["probe"]: p for p in res.get("confinement_probes", [])}
    check(
        "traversal refused",
        probes.get("engine adapter traversal refusal", {}).get("actual") == "refused",
        json.dumps(probes.get("engine adapter traversal refusal")),
    )
    check(
        "scan lists target",
        any(f["path"] == "config.yaml" for f in res.get("scan", {}).get("files", [])),
        json.dumps(res.get("scan", {}).get("files", []))[:300],
    )

    code, env, err = run(["analyze", "--workspace", str(ws / "ghost"), *engine_root])
    check("ghost workspace exit 4", code == 4, f"code={code}")

    print("== confinement refusals ==")
    code, env, err = run(
        ["capture-baseline", "--workspace", str(ws), "--resource", "../outside.txt", *engine_root]
    )
    check("traversal resource exit 4", code == 4, f"code={code} env={str(env)[:300]}")
    code, env, err = run(
        ["capture-baseline", "--workspace", str(ws), "--resource", str(outside), *engine_root]
    )
    check("absolute resource refused", code == 4, f"code={code} env={str(env)[:300]}")
    code, env, err = run(
        ["capture-baseline", "--workspace", str(ws), "--resource", "ghost.txt", *engine_root]
    )
    check("missing file exit 7", code == 7, f"code={code} env={str(env)[:300]}")

    print("== baseline ==")
    code, env, err = run(
        ["capture-baseline", "--workspace", str(ws), "--resource", "config.yaml", *engine_root]
    )
    check("baseline exit 0", code == 0, f"code={code} err={err[:300]}")
    snap = env.get("result") or {}
    check("baseline hash matches", snap.get("hash") == base_hash, str(snap.get("hash")))
    baseline_file = ws / "baseline.json"
    # The engine seals the baseline document; the test stores exactly what the
    # engine produced (that is what the extension does too).
    baseline_file.write_text(
        json.dumps(snap.get("baseline_document"), ensure_ascii=False),
        encoding="utf-8",
    )

    print("== plan: unchanged ==")
    code, env, err = run(
        [
            "plan",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            *engine_root,
        ]
    )
    check("plan exit 0", code == 0, f"code={code} err={err[:300]}")
    plan = env.get("result") or {}
    check("plan matches baseline", plan.get("matches_baseline") is True, str(plan)[:300])
    check(
        "plan wrote evidence sidecar",
        Path(plan.get("evidence_file") or "").is_file(),
        str(plan.get("evidence_file")),
    )

    # The native side-by-side diff takes its right-hand side from the STORED
    # baseline bytes, so that source must stay content-complete - while the
    # plan report (what the UI, the log and the plan document see) must never
    # carry file contents at all.
    stored = json.loads(baseline_file.read_text(encoding="utf-8")).get("snapshot") or {}
    encoded = stored.get("content_b64")
    check("stored baseline keeps the exact bytes", isinstance(encoded, str) and bool(encoded), str(type(encoded).__name__))
    if isinstance(encoded, str):
        decoded = base64.b64decode(encoded)
        check("stored bytes are the real file bytes", decoded == original, str(decoded[:60]))
        check(
            "stored bytes hash to the recorded baseline hash",
            hashlib.sha256(decoded).hexdigest() == stored.get("hash"),
            str(stored.get("hash")),
        )
    check(
        "plan baseline hash equals the stored baseline hash",
        (plan.get("baseline") or {}).get("hash") == stored.get("hash"),
        str((plan.get("baseline") or {}).get("hash")),
    )
    plan_text = json.dumps(plan)
    check(
        "plan report carries no file contents",
        '"content_b64": "[omitted]"' in plan_text and "host: localhost" not in plan_text,
        plan_text[:200],
    )

    code, env, err = run(
        [
            "plan",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(ws / "none.json"),
            *engine_root,
        ]
    )
    check("no baseline exit 7", code == 7, f"code={code} env={str(env)[:200]}")

    print("== plan-many: bulk planning for the Recovery Inbox ==")
    notes = ws / "notes.txt"
    notes.write_bytes(b"notes before the agent\n")
    code, env, err = run(
        ["capture-baseline", "--workspace", str(ws), "--resource", "notes.txt", *engine_root]
    )
    check("notes baseline exit 0", code == 0, f"code={code} err={err[:300]}")
    notes_snap = env.get("result") or {}
    notes_baseline = ws / "notes_baseline.json"
    notes_baseline.write_text(
        json.dumps(notes_snap.get("baseline_document"), ensure_ascii=False),
        encoding="utf-8",
    )
    # The agent changes both files.
    notes.write_bytes(b"notes AFTER the agent\n")
    target.write_bytes(b"config AFTER the agent\n")

    manifest = ws / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "workspace": str(ws),
                "entries": [
                    {"resource": "config.yaml", "baseline_file": str(baseline_file)},
                    {"resource": "notes.txt", "baseline_file": str(notes_baseline)},
                ],
            }
        ),
        encoding="utf-8",
    )
    code, env, err = run(
        [
            "plan-many",
            "--workspace",
            str(ws),
            "--resources-file",
            str(manifest),
            *engine_root,
        ]
    )
    check("plan-many exit 0", code == 0, f"code={code} err={err[:400]}")
    res = env.get("result") or {}
    check("plan-many total", res.get("total") == 2, str(res)[:300])
    check("plan-many count", res.get("count") == 2, str(res)[:300])
    entries = res.get("entries") or []
    check("plan-many planned both files", len(entries) == 2, str(entries)[:300])
    check(
        "plan-many entries are ok",
        all(entry.get("ok") is True for entry in entries),
        str(entries)[:400],
    )
    check(
        "plan-many reports the engine verdict",
        all((entry.get("summary") or {}).get("would_succeed") is True for entry in entries),
        str(entries)[:400],
    )
    check(
        "plan-many without --save-evidence writes no evidence sidecar",
        not Path(str(notes_baseline) + ".evidence.json").exists(),
        str(notes_baseline) + ".evidence.json",
    )

    code, env, err = run(
        [
            "plan-many",
            "--workspace",
            str(ws),
            "--resources-file",
            str(manifest),
            "--save-evidence",
            *engine_root,
        ]
    )
    check("plan-many with evidence exit 0", code == 0, f"code={code} err={err[:300]}")
    saved = [
        entry for entry in (env.get("result") or {}).get("entries", []) if entry.get("ok")
    ]
    check(
        "plan-many saved preview evidence",
        all(
            Path(str((entry.get("summary") or {}).get("evidence_file"))).is_file()
            for entry in saved
        ),
        str(saved)[:300],
    )

    print("== plan-many: one bad entry never kills the batch ==")
    bad_manifest = ws / "manifest_bad.json"
    bad_manifest.write_text(
        json.dumps(
            {
                "workspace": str(ws),
                "entries": [
                    {"resource": "../outside.txt", "baseline_file": str(baseline_file)},
                    {"resource": "notes.txt", "baseline_file": str(notes_baseline)},
                ],
            }
        ),
        encoding="utf-8",
    )
    code, env, err = run(
        [
            "plan-many",
            "--workspace",
            str(ws),
            "--resources-file",
            str(bad_manifest),
            *engine_root,
        ]
    )
    check("plan-many partial exit 0", code == 0, f"code={code} err={err[:300]}")
    entries = (env.get("result") or {}).get("entries") or []
    check("plan-many partial keeps both entries", len(entries) == 2, str(entries)[:300])
    check(
        "plan-many partial marks the bad entry",
        entries[0].get("ok") is False,
        str(entries[0])[:300],
    )
    check(
        "plan-many partial keeps the good entry",
        entries[1].get("ok") is True,
        str(entries[1])[:300],
    )
    check(
        "plan-many partial explains the failure",
        bool((entries[0].get("error") or {}).get("message")),
        str(entries[0])[:300],
    )

    print("== plan-many: manifest and slice safety ==")
    foreign = ws / "manifest_foreign.json"
    foreign.write_text(
        json.dumps(
            {
                "workspace": "C:\\elsewhere",
                "entries": [{"resource": "notes.txt", "baseline_file": str(notes_baseline)}],
            }
        ),
        encoding="utf-8",
    )
    code, env, err = run(
        [
            "plan-many",
            "--workspace",
            str(ws),
            "--resources-file",
            str(foreign),
            *engine_root,
        ]
    )
    check("foreign manifest exit 4", code == 4, f"code={code} env={str(env)[:300]}")

    code, env, err = run(
        [
            "plan-many",
            "--workspace",
            str(ws),
            "--resources-file",
            str(ws / "does-not-exist.json"),
            *engine_root,
        ]
    )
    check("missing manifest exit 2", code == 2, f"code={code} env={str(env)[:200]}")

    code, env, err = run(
        [
            "plan-many",
            "--workspace",
            str(ws),
            "--resources-file",
            str(manifest),
            "--offset",
            "1",
            "--limit",
            "1",
            *engine_root,
        ]
    )
    check("plan-many slice exit 0", code == 0, f"code={code} err={err[:300]}")
    res = env.get("result") or {}
    check("plan-many slice processes one entry", res.get("count") == 1, str(res)[:300])
    check(
        "plan-many slice returns the requested entry",
        (res.get("entries") or [{}])[0].get("resource") == "notes.txt",
        str(res)[:300],
    )

    print("== execute without preview evidence ==")
    code, env, err = run(
        [
            "execute",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            "--approved-by",
            "t",
            *engine_root,
        ]
    )
    check("missing preview exit 7", code == 7, f"code={code} env={str(env)[:300]}")

    print("== fault + preview ==")
    target.write_bytes(b"AGENT OVERWROTE \x00\xff BYTES")
    code, env, err = run(
        [
            "plan",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            *engine_root,
        ]
    )
    check("fault plan exit 0", code == 0, f"code={code} err={err[:300]}")
    plan = env.get("result") or {}
    evidence_file = plan.get("evidence_file")
    check(
        "preview detects difference",
        plan.get("matches_baseline") is False,
        str(plan.get("matches_baseline")),
    )
    check("preview would_succeed", plan.get("would_succeed") is True, str(plan.get("warnings")))
    check(
        "preview no conflict",
        plan.get("conflict_status") == "no_conflict",
        str(plan.get("conflict_status")),
    )
    check(
        "preview has diff",
        (plan.get("diff") or {}).get("changed") is True,
        json.dumps(plan.get("diff"))[:300],
    )
    check(
        "preview requires approval",
        plan.get("requires_approval") is True,
        str(plan.get("requires_approval")),
    )
    check(
        "preview evidence path present",
        bool(evidence_file) and Path(evidence_file).is_file(),
        str(evidence_file),
    )

    print("== execute without approval ==")
    code, env, err = run(
        [
            "execute",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            "--evidence-file",
            str(evidence_file),
            *engine_root,
        ]
    )
    check("no approver exit 5", code == 5, f"code={code} env={str(env)[:300]}")

    print("== execute with approval ==")
    code, env, err = run(
        [
            "execute",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            "--evidence-file",
            str(evidence_file),
            "--approved-by",
            "integration-test",
            *engine_root,
        ]
    )
    check("execute exit 0", code == 0, f"code={code} err={err[:400]} env={str(env)[:600]}")
    res = env.get("result") or {}
    check("execute success", res.get("success") is True, str(res)[:500])
    check("execute verified by engine", res.get("verified") is True, str(res)[:500])
    check(
        "execute independent byte-exact",
        res.get("independent_check", {}).get("byte_exact") is True,
        str(res)[:500],
    )
    check("file restored", target.read_bytes() == original, str(target.read_bytes()[:80]))
    # The native diff shows the stored baseline bytes on its right-hand side,
    # so after recovery the file on disk must equal exactly what that diff
    # displayed - the preview is content-complete, not a summarised diff.
    check(
        "restored file equals the bytes the diff would have shown",
        target.read_bytes() == base64.b64decode(stored.get("content_b64") or ""),
        str(target.read_bytes()[:80]),
    )

    print("== verify after recovery ==")
    code, env, err = run(
        [
            "verify",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            *engine_root,
        ]
    )
    check("verify exit 0", code == 0, f"code={code} env={str(env)[:400]}")
    check("verify success", (env.get("result") or {}).get("success") is True, str(env)[:400])

    print("== verify when state diverges ==")
    target.write_bytes(b"changed again")
    code, env, err = run(
        [
            "verify",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            *engine_root,
        ]
    )
    check("divergent verify exit 6", code == 6, f"code={code} env={str(env)[:400]}")

    print("== HUMAN EDIT between preview and execute must be refused ==")
    target.write_bytes(b"AGENT FAULT AGAIN")
    code, env, err = run(
        [
            "plan",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            *engine_root,
        ]
    )
    check("re-fault preview exit 0", code == 0, f"code={code} err={err[:300]}")
    evidence_file = (env.get("result") or {}).get("evidence_file")
    human = b"human edited AFTER the preview\n"
    target.write_bytes(human)
    code, env, err = run(
        [
            "execute",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            "--evidence-file",
            str(evidence_file),
            "--approved-by",
            "integration-test",
            *engine_root,
        ]
    )
    check("conflict execute exit 5", code == 5, f"code={code} env={str(env)[:600]}")
    check(
        "conflict kind",
        env.get("error", {}).get("kind") in ("engine_refusal", "verification_failed"),
        str(env.get("error"))[:300],
    )
    check("human edit preserved", target.read_bytes() == human, str(target.read_bytes()[:80]))

    print("== tampered evidence is rejected ==")
    target.write_bytes(b"AGENT FAULT 3")
    code, env, err = run(
        [
            "plan",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            *engine_root,
        ]
    )
    check("third preview exit 0", code == 0, f"code={code} err={err[:300]}")
    evidence_file = (env.get("result") or {}).get("evidence_file")
    tampered = Path(str(evidence_file))
    doc = json.loads(tampered.read_text(encoding="utf-8"))
    doc["evidence"]["action_id"] = "attacker-controlled"
    tampered.write_text(json.dumps(doc), encoding="utf-8")
    code, env, err = run(
        [
            "execute",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(baseline_file),
            "--evidence-file",
            str(tampered),
            "--approved-by",
            "integration-test",
            *engine_root,
        ]
    )
    check("tampered evidence exit 7", code == 7, f"code={code} env={str(env)[:300]}")
    check(
        "tampered kind",
        env.get("error", {}).get("kind") == "corrupt_evidence",
        str(env.get("error"))[:300],
    )
    check(
        "file untouched after tamper refusal",
        target.read_bytes() == b"AGENT FAULT 3",
        str(target.read_bytes()[:80]),
    )

    print("== malformed / foreign baselines ==")
    # A legacy (unsealed) baseline is refused as unsealed - it is never
    # silently blessed, whatever it claims to be.
    wrong = ws / "baseline_wrong.json"
    wrong.write_text(
        json.dumps(
            {
                "format": "interlock-baseline-v1",
                "workspace": "C:\\elsewhere",
                "resource": "config.yaml",
                "snapshot": {"hash": "abc"},
            }
        ),
        encoding="utf-8",
    )
    code, env, err = run(
        [
            "plan",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(wrong),
            *engine_root,
        ]
    )
    check("unsealed legacy baseline exit 7", code == 7, f"code={code} env={str(env)[:300]}")

    # A properly sealed baseline for ANOTHER workspace is refused as
    # unauthorized - the seal does not grant access to another workspace.
    foreign = ws / "baseline_foreign.json"
    foreign.write_text(
        json.dumps(
            seal_baseline_document(
                {
                    "format": "interlock-baseline-v2",
                    "workspace": "C:\\elsewhere",
                    "resource": "config.yaml",
                    "captured_at": "2026-10-20T10:00:00+00:00",
                    "snapshot": {"hash": "abc"},
                }
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    code, env, err = run(
        [
            "plan",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(foreign),
            *engine_root,
        ]
    )
    check("foreign baseline exit 4", code == 4, f"code={code} env={str(env)[:300]}")

    bad = ws / "baseline_bad.json"
    bad.write_text("not json", encoding="utf-8")
    code, env, err = run(
        [
            "plan",
            "--workspace",
            str(ws),
            "--resource",
            "config.yaml",
            "--baseline-file",
            str(bad),
            *engine_root,
        ]
    )
    check("malformed baseline exit 7", code == 7, f"code={code} env={str(env)[:300]}")

    code, env, err = run(["definitely-not-a-command"])
    check("bad command exit != 0", code != 0, f"code={code}")

    check(
        "outside sentinel intact",
        outside.read_bytes() == b"OUTSIDE-MUST-NOT-CHANGE",
        str(outside.read_bytes()[:80]),
    )

    shutil.rmtree(ws, ignore_errors=True)
    outside.unlink(missing_ok=True)

    print()
    print(f"passed={PASSES} failed={len(FAILURES)}")
    for failure in FAILURES:
        print("  FAILED:", failure)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
