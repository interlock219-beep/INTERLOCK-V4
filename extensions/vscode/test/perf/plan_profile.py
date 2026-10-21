"""Profile the engine's per-file recovery plan cost (read-only).

Times the phases the bridge's `plan` / `plan-many` command runs for one file:
evidence capture, simulation, conflict check, drift check and the preview.
Used to report honest performance numbers for the Recovery Inbox.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BRIDGE_DIR = Path(__file__).resolve().parents[2] / "python"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(BRIDGE_DIR))

import interlock_bridge as bridge  # noqa: E402


async def main() -> int:
    count = int(os.environ.get("PERF_FILES", "20"))
    size = int(os.environ.get("PERF_BYTES", "2048"))
    workspace = Path(tempfile.mkdtemp(prefix="il_plan_perf_"))
    payload = ("export const value = 1;\n" * 400)[:size]
    resource = "pkg/file.ts"
    target = workspace / "pkg" / "file.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload + "\n// agent edit\n", encoding="utf-8")

    engine = bridge.load_engine()
    adapter = engine.FilesystemRecoveryAdapter(base_path=workspace)
    action = bridge.make_action(engine, bridge.stable_action_id(workspace, resource), resource)
    snapshot = {
        "hash": "0" * 64,
        "size": len(payload),
        "content_b64": __import__("base64").b64encode(payload.encode("utf-8")).decode("ascii"),
    }

    timings = {
        "capture": 0.0,
        "simulate": 0.0,
        "conflicts": 0.0,
        "drift": 0.0,
        "preview": 0.0,
    }
    for _ in range(count):
        started = time.perf_counter()
        evidence = await adapter.capture_recovery_evidence(
            action, execution_context={"base_path": str(workspace)}, before_snapshot=snapshot
        )
        timings["capture"] += time.perf_counter() - started

        started = time.perf_counter()
        await adapter.simulate(action, evidence)
        timings["simulate"] += time.perf_counter() - started

        started = time.perf_counter()
        await adapter.check_conflicts(action, evidence)
        timings["conflicts"] += time.perf_counter() - started

        started = time.perf_counter()
        await adapter.detect_drift(action, evidence)
        timings["drift"] += time.perf_counter() - started

        started = time.perf_counter()
        try:
            await adapter.preview_recovery(action, evidence)
        except Exception:  # noqa: BLE001 - the preview may refuse; the cost still counts
            pass
        timings["preview"] += time.perf_counter() - started

    total = sum(timings.values())
    print(f"files profiled      : {count}")
    print(f"total               : {total * 1000:.0f} ms ({total / count * 1000:.1f} ms/file)")
    for phase, seconds in timings.items():
        print(f"  {phase:<10}: {seconds * 1000:8.0f} ms ({seconds / count * 1000:6.1f} ms/file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
