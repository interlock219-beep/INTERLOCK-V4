"""INTERLOCK V6 — Customer Pilot Demonstration v1 (disposable data only).

Chosen scenario (genuinely supported): an AI agent MODIFIES files inside a
protected workspace; Interlock restores them byte-exact, refuses to clobber
later human edits, refuses out-of-workspace requests, and stays idempotent.

Why this scenario: filesystem-family recovery was exercised at scale in the
100,000-attempt campaign (independently verified outcomes), unit tested
(tests/unit/test_filesystem_recovery_adapter.py), and frozen in Suite A
(A-001..A-005) — it needs no database, cache, network, or production access.

Adapter contract honored (filesystem_recovery_adapter.capture_recovery_evidence):
  - a PRE-ACTION capture records the original bytes (before-state);
  - evidence is captured AFTER the action with ``before_snapshot`` supplied,
    so ``after_snapshot`` becomes the conflict guard ("file was modified
    after the agent action" -> BLOCKED_BY_CONFLICT, protecting human edits).

Legs:
  1. recovery             — pre-capture -> agent fault -> compensate -> harness
                            sha256 check (adapter claims NEVER trusted)
  2. safety               — traversal resource refused; outside sentinel intact
                            (zero side effects on refusal)
  3. human_change         — a human edit made AFTER the agent action is
                            PRESERVED: restore refuses with conflict instead of
                            overwriting it
  4. idempotency          — duplicate compensation delivery (same idempotency
                            key) never double-applies; bytes stay exact

All data under a fresh temp directory; no repository file, production system,
or customer data is touched. Exit code 0 only when every independent check
passes; evidence is always written to a VERSIONED file under
logs/v6_pilot_demo_v1/ (evidence_<UTC>.json — later runs never overwrite
earlier evidence).

Run:  .venv/Scripts/python.exe scripts/pilot_demo_v1.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.domain.entities.protected_action import (  # noqa: E402
    ActionStatus,
    ProtectedAction,
    Reversibility,
)
from app.domain.entities.surgical_recovery_types import ExecutionState  # noqa: E402
from app.infrastructure.recovery.filesystem_recovery_adapter import (  # noqa: E402
    FilesystemRecoveryAdapter,
)

EVIDENCE_DIR = REPO_ROOT / "logs" / "v6_pilot_demo_v1"
# Versioned per run so no execution can ever overwrite prior evidence.
EVIDENCE_PATH = EVIDENCE_DIR / (
    "evidence_"
    + datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    + ".json"
)

# Three byte-pattern variants (mirrors Suite A filesystem variants).
FILES: dict[str, bytes] = {
    "config.yaml": b"server:\n  host: localhost\n  port: 8080\n",
    "report.csv": b"id,name,value\r\n1,alpha,10\r\n2,beta,20\r\n",
    "notes-utf8.txt": "héllo wörld — ünïcode ✓\n".encode("utf-8-sig"),
}
ADVERSARIAL = b"AGENT OVERWROTE THIS \x00\xff BYTES DO NOT TRUST"
HUMAN_EDIT = b"human made a later edit -- MUST BE PRESERVED\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_action(action_id: str, resource: str) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id,
        tenant_id="pilot-tenant",
        agent_id="pilot-agent",
        actor_user_id=None,
        authority_grant_id=None,
        tool="filesystem",
        resource=resource,
        action_type="modify",
        risk_score=0.5,
        policy_version="v1",
        correlation_id=f"pilot-{action_id}",
        parent_action_id=None,
        workflow_id=None,
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref=f"state:before:{action_id}",
        after_state_ref=f"state:after:{action_id}",
        tool_arguments={"path": resource},
        status=ActionStatus.EXECUTED,
        decision_reason="pilot demo",
        evaluated_at=None,
        executed_at=None,
        created_at=None,
    )


def state_of(result: Any) -> str:
    return str(getattr(result.execution_state, "value", result.execution_state))


async def pre_action_snapshot(
    adapter: FilesystemRecoveryAdapter, workspace: Path, name: str, action_id: str
) -> tuple[ProtectedAction, dict[str, Any]]:
    """Pre-action capture: returns the action and the original before-snapshot."""
    action = make_action(action_id, f"file:{name}")
    pre_evidence = await adapter.capture_recovery_evidence(action)
    snapshot = dict(pre_evidence.compensation_payload.get("before_snapshot") or {})
    assert snapshot.get("hash") == sha256((workspace / name).read_bytes()), (
        "pre-action capture must record the original bytes"
    )
    return action, snapshot


async def leg_recovery(workspace: Path, results: dict[str, Any]) -> bool:
    """Pre-capture -> agent fault -> post-action evidence -> compensate -> verify."""
    adapter = FilesystemRecoveryAdapter(base_path=workspace)
    pre_fault = {name: sha256(data) for name, data in FILES.items()}

    # 1) Establish originals and capture their pre-action state.
    for name, data in FILES.items():
        (workspace / name).write_bytes(data)
    originals: dict[str, dict[str, Any]] = {}
    actions: dict[str, ProtectedAction] = {}
    for i, name in enumerate(FILES):
        action, snap = await pre_action_snapshot(
            adapter, workspace, name, f"pilot-pre-{i}"
        )
        actions[name] = action
        originals[name] = snap

    # 2) The agent action (fault): every file is overwritten.
    for name in FILES:
        (workspace / name).write_bytes(ADVERSARIAL)

    # 3) Post-action evidence: before-state = original, after-state = current
    #    (becomes the conflict guard).
    evidence_map = {}
    for name in FILES:
        evidence_map[name] = await adapter.capture_recovery_evidence(
            actions[name], before_snapshot=originals[name]
        )

    # 4) Compensate through the real pipeline.
    exec_claims: dict[str, Any] = {}
    for name, evidence in evidence_map.items():
        compensation = await adapter.generate_compensation(actions[name], evidence)
        result = await adapter.execute_compensation(
            compensation, evidence.idempotency_key
        )
        exec_claims[name] = {
            "adapter_success": bool(result.success),
            "adapter_state": state_of(result),
        }

    # 5) Harness-owned verification (claims never trusted).
    per_file = {}
    all_ok = True
    for name in FILES:
        actual = sha256((workspace / name).read_bytes())
        ok = actual == pre_fault[name]
        all_ok = all_ok and ok
        per_file[name] = {
            "pre_fault_sha256": pre_fault[name],
            "restored_sha256": actual,
            "byte_exact": ok,
            "adapter_claim": exec_claims[name],
        }
    results["recovery"] = {"files": per_file, "independent_pass": all_ok}
    return all_ok


async def leg_safety(workspace: Path, results: dict[str, Any]) -> bool:
    """Traversal refusal with ZERO side effects outside the workspace."""
    sentinel = workspace.parent / "outside-sentinel.txt"
    sentinel_bytes = b"OUTSIDE-SENTINEL-MUST-NOT-CHANGE"
    sentinel.write_bytes(sentinel_bytes)
    adapter = FilesystemRecoveryAdapter(base_path=workspace)

    refused = False
    refusal_detail = ""
    try:
        action = make_action("pilot-trav", "file:../outside-sentinel.txt")
        evidence = await adapter.capture_recovery_evidence(action)
        compensation = await adapter.generate_compensation(action, evidence)
        result = await adapter.execute_compensation(
            compensation, evidence.idempotency_key
        )
        refused = not bool(result.success)
        refusal_detail = state_of(result)
    except Exception as exc:  # noqa: BLE001 - refusal may raise; that is the point
        refused = True
        refusal_detail = f"{type(exc).__name__}: {exc}"

    sentinel_unchanged = sentinel.read_bytes() == sentinel_bytes
    ok = refused and sentinel_unchanged
    results["safety"] = {
        "refused": refused,
        "refusal_detail": refusal_detail,
        "outside_sentinel_unchanged": sentinel_unchanged,
        "independent_pass": ok,
    }
    return ok


async def leg_human_change(workspace: Path, results: dict[str, Any]) -> bool:
    """A human edit made AFTER the agent action must be preserved, not undone."""
    name = "human-change.txt"
    original = b"original customer content\n"
    (workspace / name).write_bytes(original)
    adapter = FilesystemRecoveryAdapter(base_path=workspace)
    action, snap = await pre_action_snapshot(adapter, workspace, name, "pilot-human")

    # Agent action happens (state A recorded as after-state)...
    (workspace / name).write_bytes(ADVERSARIAL)
    evidence = await adapter.capture_recovery_evidence(action, before_snapshot=snap)

    # ...then a HUMAN edits the file again before recovery runs.
    (workspace / name).write_bytes(HUMAN_EDIT)
    compensation = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(compensation, evidence.idempotency_key)

    human_bytes_preserved = (workspace / name).read_bytes() == HUMAN_EDIT
    refused_with_conflict = (
        not bool(result.success)
        and state_of(result) == ExecutionState.BLOCKED_BY_CONFLICT.value
    )
    ok = human_bytes_preserved and refused_with_conflict
    results["human_change"] = {
        "recovery_state": state_of(result),
        "recovery_error": str(getattr(result, "error", "") or ""),
        "human_bytes_preserved": human_bytes_preserved,
        "independent_pass": ok,
    }
    return ok


async def leg_idempotency(workspace: Path, results: dict[str, Any]) -> bool:
    """Same compensation + same idempotency key => no double application."""
    name = "config.yaml"
    original = FILES[name]
    (workspace / name).write_bytes(original)
    adapter = FilesystemRecoveryAdapter(base_path=workspace)
    action, snap = await pre_action_snapshot(adapter, workspace, name, "pilot-idem")

    # Agent fault, then post-action evidence and compensation.
    (workspace / name).write_bytes(ADVERSARIAL)
    evidence = await adapter.capture_recovery_evidence(action, before_snapshot=snap)
    compensation = await adapter.generate_compensation(action, evidence)

    first = await adapter.execute_compensation(
        compensation, evidence.idempotency_key
    )
    restored_once = (workspace / name).read_bytes() == original
    # Duplicate delivery of the SAME compensation (resume/replay scenario).
    second = await adapter.execute_compensation(
        compensation, evidence.idempotency_key
    )
    still_exact = (workspace / name).read_bytes() == original
    ok = restored_once and still_exact
    results["idempotency"] = {
        "first_success": bool(first.success),
        "first_state": state_of(first),
        "duplicate_success": bool(second.success),
        "duplicate_state": state_of(second),
        "byte_exact_after_duplicate": still_exact,
        "independent_pass": ok,
    }
    return ok


async def main() -> int:
    results: dict[str, Any] = {
        "pilot": "INTERLOCK V6 customer pilot demo v1",
        "scenario": "agent file modification -> byte-exact restore (disposable workspace)",
        "started_at": datetime.now(tz=UTC).isoformat(),
        "workspace": "<temp>",
        "verdicts": {},
    }
    exit_code = 1
    temp_root = Path(tempfile.mkdtemp(prefix="v6_pilot_"))
    results["workspace"] = str(temp_root)
    workspace = temp_root / "workspace"
    workspace.mkdir()
    try:
        legs = {
            "recovery": leg_recovery,
            "safety": leg_safety,
            "human_change": leg_human_change,
            "idempotency": leg_idempotency,
        }
        for leg_name, leg_fn in legs.items():
            try:
                results["verdicts"][leg_name] = bool(await leg_fn(workspace, results))
            except Exception:  # noqa: BLE001 - evidence first, never hide
                results["verdicts"][leg_name] = False
                results.setdefault("errors", {})[leg_name] = traceback.format_exc()
        all_pass = all(results["verdicts"].values())
        results["overall_pass"] = all_pass
        exit_code = 0 if all_pass else 1
    finally:
        results["finished_at"] = datetime.now(tz=UTC).isoformat()
        results["exit_code"] = exit_code
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(
            json.dumps(results, indent=2, sort_keys=True), encoding="utf-8"
        )
        shutil.rmtree(temp_root, ignore_errors=True)

    print(  # noqa: T201 - CLI demo: stdout summary is the interface
        json.dumps(
            {k: results[k] for k in ("verdicts", "overall_pass", "exit_code")},
            indent=2,
        )
    )
    print(f"evidence: {EVIDENCE_PATH}")  # noqa: T201 - CLI demo output
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
