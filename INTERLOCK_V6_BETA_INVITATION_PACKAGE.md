# INTERLOCK V6 — Beta Invitation Package (DRAFT — nothing sent, no one contacted)

Versioned 2026-10-18. This package is what the coordinator sends to a volunteer
**after** the user decides to start the trial. No invitation has been sent, no
installer distributed, no announcement published. Slot T1 = Windows; slot
T2/T3 = macOS or Linux (the POSIX slot is what converts the two symlink drills
from "skipped" into executed evidence).

---

## A. Invitation letter (send verbatim or adapt)

> **Subject: Interlock recovery beta — disposable-project test, ~1 hour**
>
> Hi — Interlock is a small Python control plane that records what an AI agent
> did to your files and can surgically undo a bad file modification,
> byte-exactly, while refusing to overwrite human edits made afterwards. We are
> running a **controlled beta of its recovery engine** and need one independent
> developer per operating system. You would install it from a checkout, run a
> built-in safe demo, trigger one documented "agent fault" on a disposable
> sample file, recover it, and verify the result **with your own hash tool** —
> then report using a short template. It touches nothing of yours: everything
> runs in a directory you create for the test, Interlock makes no network
> calls, and you will not be asked for credentials, source code, or logs.
> Time: about one hour. You may stop at any time; partial results still help.

## B. Exact supported scope (state this verbatim)

| In scope | Out of scope (do not test) |
|---|---|
| Byte-exact filesystem recovery for agent file modifications, on files **you create for the test** | Database or migration operations (`alembic upgrade/downgrade`) — known defect D-MIG-1b |
| Conflict protection, idempotent replay, traversal refusal | Production systems, real projects, valuable databases |
| Reporting problems safely | Performance benchmarking; SSO/KMS; web dashboard; PostgreSQL paths |

## C. Prerequisites and installation

- Python 3.11–3.14 (`python --version` must print 3.11.x+), `git`, `pip`, ~2 GB disk.
- Not required: Docker, PostgreSQL, Redis, admin/root, network at run time.
- Install exactly as in `docs/operations/BETA_FIRST_RUN.md` §2
  (`pip install -e ".[dev,security]"` from a checkout). If install fails, stop
  and report — do not improvise workarounds.
- macOS/Linux volunteers: your OS is **unverified** by us — that is precisely
  why your slot exists. Report outcomes honestly, including skips.

## D. Test procedure

Follow `docs/operations/BETA_FIRST_RUN.md` §§3–7 end to end (demo →
hands-on recipe → independent verification → change-scope check), then the
regression subset in §10. macOS/Linux slots additionally record whether the
two symlink-escape drills ran or skipped. Optional extras (disposable data
only): the process-kill opt-in from `INTERLOCK_V6_CONTROLLED_BETA_PLAN.md` §4.4
— a reusable real-kill harness now exists
(`logs/v6_final_mission_session4/m1_real_kill_drill.py`, proven on Windows
20/20); run it only if you are comfortable with it.

## E. Files and permissions involved (state this verbatim)

- Interlock reads and writes **only inside the disposable directory you point
  it at**, plus a versioned evidence JSON under `logs/` in the checkout and
  Python bytecode caches. It creates staging files named
  `*.recovery_tmp` next to targets and removes them.
- Permissions used: ordinary user read/write. No admin/root. No registry, no
  services, no cron, no firewall changes. No network sockets during the tested
  workflow (one documented exception exists elsewhere in the product — host
  validation may perform a DNS lookup — but not in this workflow).

## F. Known limitations and unsupported operations

- Migration paths carry known, visible defects (3–4 documented xfails) — out of
  scope; do not run alembic.
- Real disk-full behavior is still mocked-only on our side (procedure prepared,
  not executed); real process-kill is now verified on Windows only.
- POSIX backup file permissions are a known open item (proposal R17).
- macOS/Linux execution of the symlink containment drills is unverified until
  your report.

## G. Consent and privacy boundaries (send verbatim)

- You work only in a fresh clone and a disposable directory you create. Never
  point Interlock at anything you cannot afford to lose — you do not need to.
- Interlock makes **no network calls** in the tested workflow. If you observe
  one, that is a finding: stop and report.
- You will not be asked for credentials, source code, database dumps, or full
  logs. The template below lists exactly what to send.
- No telemetry exists; nothing is collected automatically.
- You may stop at any time; partial results are useful.

## H. Structured bug-report template (send verbatim)

```
Slot: T1/T2/T3
OS / python --version: _
Checkout commit: _
Step that failed: _
Exact command: _
Exact error text: _
Reproducible (yes/no, N attempts): _
Files created outside your disposable dir (yes/no): _
Network attempts observed (yes/no): _
Install / demo duration: _
Clarity notes (what confused you): _
```

## I. Explicit stop conditions (send verbatim)

Stop immediately and notify the coordinator if: any file appears, changes, or
disappears outside your disposable directory or the clone; any network attempt
occurs; any secret or file content appears in error output; the same crash
happens twice; anything damages data you did not deliberately sacrifice. Keep
artifacts; do not delete the clone until the coordinator responds.

---

*Coordinator note: do not collect anything outside template H; do not claim
cross-platform validation from a single slot; a successful technical test is
not customer validation or production readiness.*

## J. POSIX slot execution checklist (added 2026-10-18, reproducible)

For the macOS/Linux volunteer, in order. Record the exact output of each step.

1. `uname -a` and `python3 --version` (need 3.11–3.14).
2. Fresh clone into a directory of your own; then Steps 2–7 of
   `docs/operations/BETA_FIRST_RUN.md` verbatim (venv, `pip install -e
   ".[dev,security]"`, imports check, `pip check`, pilot demo, hands-on
   recipe with your own `sha256sum`).
3. `pytest tests/unit/test_recovery_fault_injection.py -q -o addopts=` —
   report whether the two `test_dangling_symlink_staging_cannot_escape*`
   drills **ran** (expected on POSIX) or skipped, with the summary line.
4. Optional, real-kill evidence on POSIX: run
   `python <checkout>/logs/v6_final_mission_session4/m1_real_kill_drill.py`
   if present in your checkout, or ask the coordinator for the script — it
   self-limits to disposable temp directories. Report the summary JSON
   (`torn_writes`, `invariant_violations`).
5. Record observed file permissions of any backup/staging files you see
   (`ls -la`), for the open R17 item.
6. Stop conditions (Section I) apply unchanged on POSIX.
