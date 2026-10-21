# INTERLOCK V6 — CUSTOMER PILOT PLAN v1

**Date:** 2026-10-17 · **Status:** DEMO EXECUTED SUCCESSFULLY (disposable environment, exit 0)
**Companion:** `scripts/pilot_demo_v1.py` · evidence `logs/v6_pilot_demo_v1/evidence_*.json`
(git-ignored; one versioned file per run — no run can overwrite prior evidence)

## 1. Selected scenario (one genuinely supported benefit)

**Agent file modification in a protected workspace → byte-exact restore with
independent verification, human-change preservation, traversal refusal, and
idempotent replay.**

Selection rationale (evidence-based, not aspirational):
- filesystem family outcomes in the 100,000-attempt campaign: recovered outcomes verified independently (raw-record reconciliation, 2026-10-17);
- unit-tested adapter (`tests/unit/test_filesystem_recovery_adapter.py`, byte-exact incl. CRLF/BOM/unicode cases);
- frozen in benchmark Suite A as `A-001..A-005`;
- no database, cache, network, CI, or production access required.

## 2. What the demonstration does (four legs, all harness-verified)

| Leg | Behavior | Measured result (run 2026-10-17) |
|---|---|---|
| recovery | pre-action capture → agent overwrites 3 files (ASCII, CRLF, UTF-8-BOM) → compensation | **3/3 byte-exact** (sha256 pre-fault == restored, harness-computed; adapter claims recorded but never trusted) |
| safety | resource `file:../outside-sentinel.txt` | **refused** (`ValueError: Path traversal detected`), outside sentinel **unchanged** |
| human_change | human edits the file *after* the agent action, before recovery | **refused** (`blocked_by_conflict`, "File was modified after the agent action"), **human bytes preserved** |
| idempotency | duplicate delivery of the same compensation (same idempotency key) | first `succeeded`; duplicate did **not** double-apply (conflict-shaped refusal — safe direction); bytes **still exact** |

Runner: `.venv/Scripts/python.exe scripts/pilot_demo_v1.py` → exit code 0
only when every independent check passes; evidence JSON always written,
failures never suppressed.

## 3. Prerequisites for the customer evaluation

- Repo checkout with `.venv` (Python 3.11+, pinned requirements installed from the verified wheel/sdist artifacts).
- A writable temp directory (the demo creates and deletes its own workspace).
- **No** database, Redis, Docker, credentials, network egress, production access, or customer data.
- Read the evidence JSON: PASS claims must match the harness hashes, not the adapter's `succeeded` field.

## 4. Limitations (disclosed; do not oversell)

- Scope: **filesystem workspace recovery only** — database/config/hosts/git families are NOT part of this pilot.
- Duplicate-replay after a successful restore reports `blocked_by_conflict` (safe refusal) rather than a cached success — behavior is safe (no double-apply) but the status string is conservative.
- Single-machine, single-process demo; concurrency/lease/fencing behavior is covered by the test suites, not by this pilot.
- Latency/throughput claims are NOT part of this pilot (the 3 latency test failures remain open pending the idle-window rerun).
- No world-leadership claim: comparative baselines have been designed (BENCHMARK_DESIGN.md) but not executed.

## 5. Failure behavior

- Any leg failing its independent check → exit code 1, `overall_pass: false`,
  per-leg detail + traceback preserved in the evidence JSON. The demo never
  converts a failure into a skip, and never trusts the adapter's own success claim.
- Refusals (traversal, conflict) are *expected outputs of safety legs*, not errors.
- If the demo cannot run at all (missing env), it fails loudly; there is no
  degraded "success" mode.

## 6. Rollback

- The pilot touches only a temp directory it creates (`v6_pilot_*`), deleted at
  the end of every run (success or failure); evidence files under
  `logs/v6_pilot_demo_v1/` are git-ignored.
- Nothing stages/commits/pushes, no migrations run, no production or customer
  system is contacted. Removing the pilot = delete `scripts/pilot_demo_v1.py`,
  `INTERLOCK_V6_PILOT_PLAN.md`, and `logs/v6_pilot_demo_v1/`.

## 7. Baseline and success criteria (measurable)

**Baseline (manual status quo, measurable by the customer during onboarding):**
1. Time to restore 3 manually-modified files to known-good content (stopwatch, per file);
2. whether the restore is verified byte-exact afterwards (yes/no);
3. whether a co-worker's later edit is at risk of being overwritten by the restore (yes/no);
4. behavior when restoring a path outside the intended workspace (anything goes vs. refused).

**Success criteria (all must hold in the demo evidence, exit 0):**
1. `recovery.independent_pass == true` with 3/3 matching sha256 pairs (vs. baseline #2);
2. `safety.independent_pass == true` — traversal refused, zero outside side effects;
3. `human_change.independent_pass == true` — later human edit preserved;
4. `idempotency.independent_pass == true` — duplicate delivery never double-applies;
5. every PASS backed by harness-computed hashes in the evidence JSON (adapter claims alone never sufficient).

**Claim discipline:** this proves ONE specific benefit to ONE engineering team.
No broader production-suitability or leadership claim is made; frozen Suite A/B
execution and CI evidence remain pending authorization (see the mission report).
