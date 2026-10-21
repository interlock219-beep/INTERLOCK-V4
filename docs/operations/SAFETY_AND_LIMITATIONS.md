# Interlock V6 — Safety and Limitations Guide

One page, for testers and evaluators. Every statement links to its evidence
source; nothing here is aspirational. Last verified 2026-10-18.

## What Interlock can recover (verified)

| Capability | Evidence |
|---|---|
| Restore a file an AI agent **deleted**, byte-exactly | `tests/unit/test_filesystem_recovery_adapter.py::test_execute_restore_deleted_file`; real self-test 2026-10-18 (`logs/v6_selftest_recovery_20261018T085000Z/`, independent SHA-256 verification PASS) |
| Undo an agent's **overwrite** of a file, byte-exactly | pilot demo leg 1 (repeatedly re-run, 4/4 verdicts); Suite A frozen evidence |
| Refuse to overwrite a **human edit** made after the agent's action | pilot demo leg 3 (`blocked_by_conflict`) |
| Never double-apply a **duplicate delivery** | pilot demo leg 4; self-test retry (`blocked_by_conflict`, target unchanged) |
| Refuse **path traversal** (`file:../…`) with zero side effects | pilot demo leg 2; traversal drills |
| Survive a **hard process kill** mid-recovery without torn writes | real-kill drill 2026-10-18: 20/20, 0 torn (`logs/v6_final_mission_session4/m1_kill_evidence.json`) — Windows only |
| Fail closed on **malformed/hostile backups** with typed errors | 19 fault-injection drills (`tests/unit/test_recovery_fault_injection.py`) |

## What Interlock cannot do (do not expect these)

- **Database / migration recovery.** Known defects D-MIG-1b/D3 brick database
  rollback paths (4 visible xfails). Out of beta scope by prohibition.
- **Recover what it never observed.** The engine is evidence-driven, not a
  backup daemon: it can only restore states it captured before the action.
- **Real disk-full behavior.** Covered by mocked `ENOSPC` tests only; the real
  drill needs an isolated volume (procedure prepared, not executed).
- **POSIX guarantees.** No macOS/Linux execution exists yet; symlink-escape
  drills skip on unprivileged Windows. POSIX safety is *unverified*.
- **Guaranteed recovery, zero data loss, universal rollback.** Not claimed.
- Production systems, valuable data, SSO/KMS, web dashboard, PostgreSQL paths.

## What you must do as a user

- **Keep your own backup.** Interlock complements version control; it does not
  replace it. Never point it at data you cannot afford to lose.
- Run it only on **disposable projects** during the beta.
- Verify recoveries **independently** (`Get-FileHash` / `sha256sum`) — the
  first-run guide's recipe shows how.
- Treat any `blocked_by_conflict` result as a **feature**: it means human or
  external changes are being preserved, not that recovery failed.

## When to stop immediately

Stop and report if: anything changes outside your disposable directory; a
network attempt occurs; secrets or file contents appear in error output; the
same crash repeats. See `INTERLOCK_V6_CONTROLLED_BETA_PLAN.md` §8 (pause
criteria) and `INTERLOCK_V6_BETA_INVITATION_PACKAGE.md` §I.

## Known accepted limitations (documented, not bugs)

- Manifest integrity is unkeyed SHA-256 (tamper-evidence only; register U5).
- Host validation may perform a DNS lookup (intended SSRF defense; register U3).
- Backup artifact POSIX permissions are default-umask (proposal R17, open).
- Restore-vs-running-app enforcement is OS-dependent on POSIX (register U1).

Sources: `INTERLOCK_V6_FINAL_HANDOFF.md`,
`INTERLOCK_V6_BETA_READINESS_CHECKLIST.md`,
`INTERLOCK_V6_RECOVERY_HARDENING_REGISTER.md`.
