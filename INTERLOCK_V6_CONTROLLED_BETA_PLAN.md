# INTERLOCK V6 — Controlled Beta Plan (3–5 volunteer developers)

Versioned 2026-10-18. Draft only: no one has been contacted, nothing has been
published, no installer has been distributed. This document defines the trial
so it can be executed by the coordinator exactly as written.

## 1. Goal and non-goals

**Goal:** determine whether an independent developer can, from a clean
checkout, install Interlock, understand its permissions, reproduce a supported
failure, recover a disposable project, verify the result, and report a problem
safely.

**Non-goals:** production deployment, migration testing, performance claims,
compliance evidence, onboarding customers, or collecting any project data.

## 2. Tester slots (diversify the environment, not the data)

| Slot | Environment | Why |
|---|---|---|
| T1 | Windows 11/10, Python 3.11 | parity with the reference host |
| T2 | macOS (recent), Python 3.11+ | first POSIX execution of the recovery paths incl. the symlink drills that skip on Windows |
| T3 | Linux (Ubuntu/Debian-class), Python 3.11+ | second POSIX datapoint; CI-parity OS |
| T4 (optional) | Windows, Python 3.13 | forward-version check (declared range allows <3.15) |
| T5 (optional) | Linux, Python 3.12 | version-matrix fill |

Minimum viable trial: T1 + one POSIX slot (T2 or T3). The POSIX slot is what
converts the two symlink-escape drills from "skipped" into executed evidence.

## 3. Consent and data boundaries (read to volunteers verbatim)

- You will work **only** in a fresh clone and a disposable directory you create
  for this test. Never point Interlock at a project you cannot afford to lose;
  you do not need to.
- Interlock makes **no network calls** during the tested workflow. If you ever
  observe one, that is a finding — report it and pause.
- You will not be asked for credentials, source code, database dumps, or full
  logs. The reporting template (Section 7) lists exactly what to send.
- The beta uses your machine's CPU/disk only; no telemetry exists to disable.
- You may stop at any time; partial results are still useful if reported.

## 4. Exact procedure (per tester)

1. Environment intake: OS, `python --version`, `git --version`, disk free.
2. Follow `docs/operations/BETA_FIRST_RUN.md` Sections 2–7 end to end, in
   order. Record wall-clock time for install and for the demo.
3. Run the regression subset from Section 10 of that document; record the
   summary line verbatim (on macOS/Linux also record whether the two symlink
   drills ran or skipped).
4. Opt-in extras (disposable data only, stop on anything unexpected):
   - kill the Python process mid-recipe (`Ctrl+C` / `kill -9`) and re-run the
     recipe once — expected: recovery still succeeds; at most a leftover
     `*.recovery_tmp` staging file in the disposable directory;
   - run the recipe with a read-only target file on POSIX and report the error
     text (expected: typed `BackupVerificationError`-style fail-closed message
     or adapter FAILED result, live data untouched).
5. Attempt one **reasonable variation of your own** on the disposable directory
   (e.g., different filename encodings, CRLF files) and report what happened.
6. Complete the reporting template (Section 7).
7. Delete your clone and disposable directory when finished.

## 5. Expected outcomes (what "pass" looks like)

- Install completes with `pip install -e ".[dev,security]"` and `pip check`
  reports no broken requirements.
- Pilot demo: 4/4 verdicts true, exit code 0.
- Recipe: `state=succeeded`, independent SHA-256 matches the original bytes,
  workspace contains only the single file, duplicate delivery ends in
  `blocked_by_conflict`.
- Regression subset: all tests pass or skip/xfail **for the documented
  reasons** (symlink privilege, the four migration xfails); zero failures.
- No file, process, or network activity observed outside the disposable
  directory.

## 6. Independent verification methods (performed by the tester, not Interlock)

- `sha256sum`/`Get-FileHash`/`certutil -hashfile` on the recovered file compared
  against the pre-failure bytes you saved yourself.
- Directory listing before/after (`dir` / `ls -la`) proving scope of change.
- For POSIX slots: `pytest tests/unit/test_recovery_fault_injection.py -q`
  executed (not skipped) for the symlink drills.

## 7. Failure-reporting template (send exactly this, nothing more)

```
Slot: T_
OS / Python: _
Checkout commit: _
Step that failed: _
Exact command: _
Exact error text: _
Reproducible (yes/no, N attempts): _
Observed side effects outside disposable dir (yes/no): _
Observed network attempts (yes/no): _
Time to install / demo: _
```

## 8. Criteria for pausing the trial (all volunteers, immediately)

- Any write, deletion, or permission change **outside** the disposable
  directory or the clone.
- Any network attempt during the tested workflow.
- Any secret or file content appearing in error output.
- The same crash reproduced by two volunteers.
- Any data loss a tester did not cause deliberately.

Pause = stop assigning new steps; keep artifacts; coordinator triages before
resuming. Findings are filed against the defect register
(`INTERLOCK_V6_RECOVERY_HARDENING_REGISTER.md`) with the same RED discipline:
reproduce first, then fix.

## 9. Coordinator checklist before inviting anyone

- [ ] Fresh-checkout install reproduced on the reference host (evidence:
      `logs/v6_beta_install_check/`).
- [ ] `docs/operations/BETA_FIRST_RUN.md` commands re-verified on the reference
      host (done 2026-10-18; re-verify if the checkout moves).
- [ ] Defect register and beta-readiness audit current.
- [ ] A private intake channel exists for the template above (email/issue
      tracker of the tester's choosing).
- [ ] No production access, secrets, or customer data anywhere in the trial
      path.

## 10. Severity triage for incoming reports (added 2026-10-18)

Assign the highest severity that fits; when in doubt, take the higher one and
say why in the report thread.

| Severity | Definition | Response |
|---|---|---|
| **S1 — data integrity** | Any byte mismatch after recovery; any change outside the disposable directory; data loss a tester did not deliberately sacrifice | Pause the whole trial (Section 8); preserve artifacts; reproduce before fixing |
| **S2 — reliability** | Reproducible crash/error in a documented step; recovery refusal that blocks a documented outcome | Fix-then-retest in the next build; note workaround |
| **S3 — usability/docs** | Confusing output, doc mismatch, unclear error | Batch into documentation fixes; no trial pause |

Data-integrity (S1) reports always outrank feature requests and speed
issues. Fixes follow the register's discipline
(`INTERLOCK_V6_RECOVERY_HARDENING_REGISTER.md`): reproduce first, keep the
failing evidence, then change code.
