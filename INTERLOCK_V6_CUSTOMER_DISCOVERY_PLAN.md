# INTERLOCK V6 — Customer Discovery Plan (PREPARED, NOT EXECUTED)

Draft only: no customer has been contacted, no interview conducted, no price
quoted, no revenue projected. This plan exists so the discovery step can start
immediately when the user authorizes it, and it is explicitly gated on the
release gates in `INTERLOCK_V6_FINAL_HANDOFF.md` §9.

## 1. Problem hypothesis (one sentence)

Developers using AI coding agents repeatedly hit a gap git cannot close: an
agent deletes or overwrites files *since the last commit* (uncommitted work,
generated artifacts, non-versioned directories), and the standard recovery
story is "revert, re-prompt, or redo" — Interlock surgically restores the exact
pre-action bytes while preserving human edits made afterwards.

## 2. Target interviewees (who to look for, not invented customers)

- Developers who run AI coding agents (Copilot Workspace, Cursor, aider,
  Claude Code, Devin-class tools) on real projects several times a week.
- Roles: senior/staff engineers, tech leads, small-team founders who merge
  agent PRs without CI safety nets.
- Where to find them (when authorized): the user's own professional network,
  local meetups, agent-tool communities — never scraped or cold-harvested by
  the assistant.

## 3. Demo (synthetic data only — already built)

- `python scripts/pilot_demo_v1.py` → 4/4 verdicts, ~seconds, zero setup.
- Hands-on self-recovery: `docs/operations/BETA_FIRST_RUN.md` §§4–6 plus the
  real self-test report `logs/v6_selftest_recovery_20261018T085000Z/report.md`.
- Nothing in the demo touches the interviewee's machine beyond a temp folder.

## 4. Five neutral interview questions (no leading, no selling)

1. "Walk me through the last time an AI agent changed a file you didn't want
   it to change. What did you do next?"
2. "What does your current safety net look like between the agent's edit and
   your commit — automatic or manual?"
3. "When a recovery tool refuses to act to avoid clobbering your own edit,
   is that the behavior you'd want, or would you expect it to ask?"
4. "What would you need to see before trusting a tool to restore files
   automatically — tests, hashes, audits, a money-back promise?"
5. "If this existed and worked as described, how would you expect to pay for
   it — seat, usage, one-time, or not at all?"

## 5. Paid-pilot experiment (proposal only; gated)

- Gate: controlled-beta verdict holds (handoff §9 category 8 PASS) AND at
  least two pilot users complete the first-run procedure without data-safety
  incidents AND POSIX validation is no longer BLOCKED.
- Shape: 2–3 teams, 2 weeks, disposable-project use only, weekly 15-minute
  feedback, one page of agreed success metrics (time-to-recovery, false
  refusals, trust rating).
- Price: a hypothesis to be *tested in the interviews* (question 5), not set
  here. No financial projections are made; revenue is not profit.

## 6. Evidence-based decision rules (before spending more effort)

**Start charging** when: ≥2 pilot users independently verify recoveries and
say they would pay; no unresolved data-integrity defects (S1) in their usage;
POSIX validation no longer BLOCKED.

**Change the product** when: ≥3 interviewees describe the same workflow gap
that the current scope does not cover (e.g., directory-level recovery), and a
narrow fix fits the existing architecture.

**Stop or re-scope** when: interviewees consistently say git snapshots /
time-machine backups already solve it, or the trust burden of an
evidence-driven tool exceeds its value for them.

## 7. What will NOT be claimed

No market size, no conversion rates, no revenue, no testimonials, no customer
names — until real interviews and pilots produce them. A successful technical
self-test is not demand evidence.

## 8. Execution checklist (prepared 2026-10-18; nothing executed)

**Slot T1 (Windows developer):** send invitation (package §A) → consent
(package §G) → they run `docs/operations/BETA_FIRST_RUN.md` §§2–7 + §10 →
they return template H → triage by severity (beta plan §10).

**Slot T2 (Linux/macOS developer):** same, plus package §J (POSIX checklist:
symlink drills, optional real-kill harness, permission observations).

**Five interviewees (prospective users of AI coding tools):**
1. Identify candidates through the user's own network (never harvested by the
   assistant); confirm they use AI coding agents weekly.
2. Send this draft message (adapt greeting only):

   > Hi — I'm researching how developers handle mistakes by AI coding agents
   > (files deleted or overwritten since their last commit). Would you do a
   > 20-minute call? No product pitch; I just want to understand your current
   > workflow. Nothing will be installed on your machine.

3. Use the five neutral questions (Section 4) verbatim; record answers with
   consent; store notes without personal data beyond role/context.
4. After each call, log: current recovery practice, failure frequency,
   time/cost estimate, existing alternatives, willingness-to-pay signal — as
   quotes, not conclusions.
5. After five calls: aggregate into the Section 6 decision rules. Report
   counts, not stories, and never invent interest that was not expressed.
