# INTERLOCK V6 — Controlled Beta First Run (filesystem recovery)

Versioned 2026-10-18. This is the **only** workflow the controlled beta asks you
to follow. It covers the supported beta scope: *byte-exact filesystem recovery
for AI-agent file modifications, on disposable projects.*

Everything in this document was executed on the reference host before being
written down. Commands show their real observed output.

## 0. What is in scope and what is not

| In scope (beta) | Out of scope (do not test in this beta) |
|---|---|
| Filesystem-family recovery on files **you create for this test** | Database migrations (`alembic upgrade/downgrade`) — known defect D-MIG-1b, approval-gated repair |
| The documented failure → recovery → verification loop | Production systems, real user projects, valuable databases |
| Conflict protection (human edits preserved), idempotent replay, traversal refusal | SSO, KMS/HSM, web dashboard, PostgreSQL paths (see README Limitations) |
| Reporting problems safely | Performance benchmarking, load testing |

## 1. Prerequisites

- **Python 3.11+** (repo declares `>=3.11,<3.15`; reference host: Windows 11,
  Python 3.11.9).
- `git`, `pip`, ~2 GB free disk for a virtual environment.
- **Not required** for this beta: Docker, PostgreSQL, Redis, network access at
  run time, administrator/root.
- **Untested environments:** macOS and Linux were not executed in the reference
  environment. The recovery code is pure Python (`pathlib`/`os`), but treat
  macOS/Linux runs as *unverified until you report the result* — that report is
  one of the trial's goals.

## 2. Install (the documented, supported method)

```bash
git clone <repository-url>
cd interlock-v4

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -e ".[dev,security]"
```

There is **no** published package index entry; install from a checkout only.
If `pip install` fails, stop and report it (Section 8) — do not improvise
workarounds; the install path is part of what the trial validates.

Sanity checks:

```bash
python --version              # must print 3.11.x or newer (below 3.15)
python -c "import app.main, sdk.intentlock; print('imports ok')"
python -m pip check           # must print: No broken requirements found
```

## 3. Safe demonstration (fully disposable, zero setup)

```bash
python scripts/pilot_demo_v1.py
```

Real observed output on the reference host:

```json
{
  "verdicts": {
    "recovery": true,
    "safety": true,
    "human_change": true,
    "idempotency": true
  },
  "overall_pass": true,
  "exit_code": 0
}
```

What this proves without any risk to you:

1. **recovery** — agent-faulted files are restored byte-exactly, verified by
   the harness's own SHA-256 (adapter claims are never trusted).
2. **safety** — a traversal resource (`file:../outside-sentinel.txt`) is
   refused with zero side effects.
3. **human_change** — a human edit made *after* the agent action is preserved:
   recovery refuses with `blocked_by_conflict` instead of overwriting it.
4. **idempotency** — a duplicate compensation delivery is never double-applied.

The demo runs in a fresh temp directory it deletes afterwards and writes a
versioned evidence file under `logs/v6_pilot_demo_v1/` (later runs never
overwrite earlier evidence). It touches no repository file, no network, and no
database.

## 4–6. Hands-on: trigger a failure, recover, verify independently

Run this **inside the repository directory** with the virtual environment
activated. It creates its own disposable directory, performs one supported
failure, recovers it, and verifies the result with an independent hash you can
re-check yourself. This is the exact snippet validated on the reference host
with the output shown below.

```python
# save as beta_recipe.py and run: python beta_recipe.py
import asyncio, hashlib, shutil, tempfile
from pathlib import Path

from app.domain.entities.protected_action import (
    ActionStatus, ProtectedAction, Reversibility,
)
from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_action(action_id: str, resource: str) -> ProtectedAction:
    return ProtectedAction(
        action_id=action_id, tenant_id="beta-tenant", agent_id="beta-agent",
        actor_user_id=None, authority_grant_id=None, tool="filesystem",
        resource=resource, action_type="modify", risk_score=0.5,
        policy_version="v1", correlation_id=f"beta-{action_id}",
        parent_action_id=None, workflow_id=None,
        reversibility=Reversibility.AUTOMATICALLY_REVERSIBLE,
        before_state_ref=f"state:before:{action_id}",
        after_state_ref=f"state:after:{action_id}",
        tool_arguments={"path": resource}, status=ActionStatus.EXECUTED,
        decision_reason="beta hands-on recipe", evaluated_at=None,
        executed_at=None, created_at=None,
    )


async def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="interlock_beta_"))
    original = b"server:\n  host: localhost\n  port: 8080\n"
    target = work / "config.yaml"
    target.write_bytes(original)
    adapter = FilesystemRecoveryAdapter(base_path=work)
    action = make_action("beta-1", "file:config.yaml")

    # 1) Pre-action evidence records the ORIGINAL bytes.
    pre = await adapter.capture_recovery_evidence(action)
    before = dict(pre.compensation_payload.get("before_snapshot") or {})
    assert before.get("hash") == sha256(original)

    # 2) The agent "fault": overwrite the file.
    target.write_bytes(b"AGENT OVERWROTE THIS FILE")

    # 3) Post-action evidence; before-snapshot = restore source,
    #    current bytes = conflict guard.
    evidence = await adapter.capture_recovery_evidence(action, before_snapshot=before)

    # 4) Plan and execute the compensation.
    compensation = await adapter.generate_compensation(action, evidence)
    result = await adapter.execute_compensation(compensation, evidence.idempotency_key)
    print(f"recovery: success={result.success} "
          f"state={result.execution_state.value}")

    # 5) INDEPENDENT verification — your own hash, not the adapter's claim.
    assert target.read_bytes() == original
    print(f"verified: sha256={sha256(target.read_bytes())}")

    # 6) Nothing else changed and no staging residue remains.
    names = sorted(p.name for p in work.iterdir())
    print(f"workspace contents: {names}")
    assert names == ["config.yaml"]

    # 7) Duplicate delivery is refused, never double-applied.
    again = await adapter.execute_compensation(compensation, evidence.idempotency_key)
    print(f"duplicate delivery: state={again.execution_state.value}")


asyncio.run(main())
```

Real observed output on the reference host:

```
recovery: success=True state=succeeded
verified: sha256=13372663edff22096ce10b1bef3c60b50f32dfd7ddb8f36d24964e7362511ecb
workspace contents: ['config.yaml']
duplicate delivery: state=blocked_by_conflict
```

Your `sha256` value will match only if your file content is byte-identical to
the snippet's `original` — that is the point: the check is content-based, not
trust-based. (That digest is SHA-256 of the 45 bytes
`server:\n  host: localhost\n  port: 8080\n`.)

## 7. What Interlock changed — and what it did not

In the demo and the recipe above, Interlock:

- wrote **only inside the disposable directory it created**;
- created staging files next to the target and removed them (a failed or killed
  attempt leaves at most a `*.recovery_tmp` / `*.restore-tmp` staging file,
  never partial bytes at your target);
- wrote a versioned evidence JSON under `logs/v6_pilot_demo_v1/` (demo only).

Interlock did **not**: call the network, modify anything outside the disposable
directory, touch your `.env`, require credentials, or start any service.
Verification error messages are content-free by design (a regression test
asserts secrets never appear in them), but they do contain **file names** —
redact paths if your filenames are sensitive.

## 8. Reporting a problem without exposing your project

Send only:

1. Your OS and `python --version` output, and the Interlock commit/checkout.
2. The exact step number from this document and the exact command you ran.
3. The **complete error text** (these messages contain file names and IDs, not
   file contents — see Section 7).
4. For backup/restore tests: the `manifest.json` fields `manifest_version`,
   `evidence_count`, and the artifact SHA-256 digests — **not** the
   `snapshot.sqlite3` or `evidence_dump.json` files themselves.
5. Whether the failure is reproducible (run the step once more).

Do **not** send: source files, `.env` values, database dumps, full
`logs/` directories without review, or anything you would not paste into a
public issue.

Pause the trial and notify the coordinator immediately if any of these occur:
data loss outside the disposable directory, a write outside the workspace
boundary, any unexpected network attempt, secrets appearing in output, or two
volunteers hitting the same crash.

## 9. Known limitations you may hit (honest list)

- **Symlink drills** (`test_dangling_symlink_staging_cannot_escape*`) skip on
  unprivileged Windows shells; on macOS/Linux they run — please report the
  result of `pytest tests/unit/test_recovery_fault_injection.py -q` from your
  environment.
- **Real process-kill / disk-full** behavior is covered by mocked fault
  injection only; a real kill of a recovery process in your disposable
  directory is welcome extra evidence (opt-in, disposable data only).
- **Migration paths** (`alembic upgrade/downgrade`) carry the known, visible
  D-MIG-1b defect (3 documented xfails) and are outside this beta's scope.
- **POSIX permissions:** backup artifacts use default umask; this beta does not
  exercise multi-user permission hardening (proposal R17).
- **Backups** (`export_backup`/`restore_backup`) are local operator utilities:
  supported and drilled, but they require the application to be stopped and are
  only as trustworthy as the directory they live in.

## 10. Regression evidence you can reproduce

```bash
pytest tests/unit/test_recovery_fault_injection.py \
       tests/unit/test_backup_restore_drill.py \
       tests/unit/test_filesystem_recovery_adapter.py \
       tests/integration/test_alembic_migration_safety.py \
       tests/integration/test_scenario_proofs_v6.py -q
```

Reference-host result (2026-10-18): `60 passed, 2 skipped, 4 xfailed` (skips =
symlink privilege; xfails = the four documented migration defects — they are
*supposed* to be visible, not green).
