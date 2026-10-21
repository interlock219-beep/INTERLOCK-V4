# Interlock V5 — Security Review Summary

Release-gate security review of the working tree at `master` HEAD `145a3d9` plus all
uncommitted V5/baseline changes. Reviews the current environment only; every claim is
labeled by how it was established.

## 1. Method and tooling used in this run

| Check | Command / method | Result | Status |
|---|---|---|---|
| Secret scan (changed files) | 5 pattern families (AWS access keys, private-key blocks, GitHub/Slack/OpenAI token shapes) over all 47 modified/untracked non-user files | **0 hits**; file:line-only reporting, no contents printed | Verified in this run (heuristic — see limitations) |
| Dependency audit | `pip-audit -r requirements.txt --no-deps` | **20 known vulnerabilities in 4 packages** (pre-remediation) | Verified in this run |
| Dependency audit (post-remediation) | same command after the pin bump | **3 known vulnerabilities in 2 packages** — `python-jose 3.5.0` (CVE-2026-85394), `ecdsa 0.19.2` (PYSEC-2026-1325 ×2 occurrences); no fix published for either; neither imported by app code (G-14). pyjwt/urllib3 advisories cleared. | Verified in this run |
| Static security (CI parity) | `bandit -r app -ll` (same as CI) | 1 High (V5 archive extractall fallback) → suppressed with justified `# nosec` after re-verifying per-member pre-validation; Medium: 0 | Verified in this run |
| Ruff security rules (S) on V5 files | `ruff check` per file | S112 ×2 (intentional skip loops → `# noqa` + reason), S202 ×1 (above) | Verified in this run |
| Semgrep (CI parity) | `semgrep --config auto app` (semgrep 1.173.0, same ruleset family as `semgrep/semgrep-action@v1`) | **43 findings: 1 V5 (archive extractall) — suppressed with documented manual review; 42 pre-existing baseline** (SQLAlchemy `len(all())` performance rules ×~9 across 7 repository files; logger-credential false-positives ×3 in `token_revocation_service.py`; SQL-injection-family rules in `auth.py`, `billing.py`, `database_recovery_adapter.py`) | Verified in this run |
| Dedicated secret scanners (trufflehog/detect-secrets/pre-commit) | toolchain inspection | **Not present** in requirements/pre-commit config | Not tested (limitation) |
| DAST / web scans | — | impossible: `web/` frontend deleted (user state, preserved); backend-only surface | Not tested (G-7) |
| Full local test suite | `pytest tests -q --no-header --no-cov` | see Test Evidence Report | Verified in this run |

`.env` (ignored, present) was **never opened or printed**; it is excluded from scans by
design and must be reviewed by the operator out-of-band.

## 2. Dependency security (P1 finding)

`pip-audit` against the pinned `requirements.txt` (pip-compile output **without
`--hash` entries** — pinned, not hash-verified):

| Package | Pinned | Advisories | Fix available |
|---|---|---|---|
| pyjwt | 2.13.0 | 15 (PYSEC-2026-4140…4152, 4183) | **2.14.0 / 2.15.0** |
| urllib3 | 2.7.0 | 3 (PYSEC-2026-4175…4177) | **2.8.0** |
| python-jose | 3.5.0 | 1 (CVE-2026-85394) | none published |
| ecdsa | 0.19.2 | 1 (PYSEC-2026-1325) | none published |

- **pyjwt is directly imported by the auth path**
  (`app/infrastructure/security/jwt_token_service.py`,
  `ed25519_execution_token_service.py`) → upgrading it is the priority action.
  *Remediation completed in this run:* pins bumped to `pyjwt==2.15.0` (with the
  `[crypto]` extra in dev) and `urllib3==2.8.0` in both requirements files, the
  venv updated, and the authentication suites re-run green (351-test targeted
  batch including `test_auth_api.py`; final full-suite numbers in the Test
  Evidence Report). Note: `requirements*.txt` are **gitignored local files**
  (`.gitignore:70–71`, never tracked) — the bump lives in the ignored pins +
  the venv, so it is a verified local-environment change, not a commit
  artifact. Verified side effect: semgrep 1.173.0 declares
  `pyjwt[crypto]~=2.13.0`, so pip's resolver warns about that dev-tool pin —
  semgrep was executed *after* the upgrade and works correctly (full scan,
  exit 0). The app-critical auth library wins over the tooling pin; recommend
  a semgrep upgrade when a compatible version publishes.
- **python-jose / ecdsa: no fix exists.** Neither is imported by application code
  (verified by import search); they remain in the dependency graph as transitive/
  legacy pins. Remediation = removal from the pin set or accepting with documentation.
  Tracked in the Production Gap Matrix (G-14).
- No hashes in the lockfile (supply-chain) → G-15.

## 3. Authentication, authorization, tenant isolation

*Verified in this run (test-backed):*

- Recovery execute/resume/verify endpoints require `require_recovery_executor`
  (authority-checked dependency) — `surgical_recovery.py`.
- Cross-tenant access fails closed: cross-tenant plan/action/grant reads return
  DENY/404 semantics (baseline tests `test_domain_a_advanced_authorization`,
  isolation assertions in orchestrator step loading).
- Quota enforcement returns HTTP 429 (`QuotaExceededError` mapping, create+execute).
- Registry registration refuses contract violations (strict raise), adapter
  capability refusals block claiming steps (`unsupported/irreversible/
  requires_approval` → never executes).
- Lease acquisition failure → `already_running` (fail-closed: no execution without a
  lease), resume now included (V5-15).
- Evidence redaction: environment references capture hashes, not raw values
  (certification probe asserts the pre-action secret never appears in
  `before_state_reference`).

*Not tested:* production-grade auth flags against real services (G-11), token
lifetime/rotation behavior across instances, rate limiting beyond quota.

## 4. Recovery-specific hardening (this campaign)

- **Path containment** on every payload-derived filesystem touch:
  config (`_safe_config_path`, V5-9), filesystem (V5-4), archive (state-dir + target
  rules), hosts (byte-level), git (V5-16 — absolute/`..`/NUL/symlink escapes refused
  at execute *and* verify *and* drift/conflict).
- **Archive extraction (TarSlip):** two layers — per-member rejection (links,
  non-regular, escape via `resolve().relative_to`) + `filter="data"` where available;
  bandit B202 on the legacy fallback branch is suppressed *with the pre-validation
  documented on the suppression line* (reviewed manually this run).
- **Evidence payload trust:** payloads are treated as untrusted input at execution
  time (containment re-validation), not just at capture time.
- **Authorization of compensations:** tenant context embedded at generation and
  re-verified at execution (`_verify_compensation_authorization`); idempotency-key
  mismatch blocks execution.
- **Honesty fixes:** rename recovery no longer claims success/verification
  (V5-19); resume verification consults all adapters and trusts only positive
  verdicts from verifiers (V5-18).

## 5. API error behavior, logging, audit evidence

- Typed errors at boundaries: 404 (unknown plan), 400 (wrong state), 429 (quota),
  401/403 (authority dependencies). Recovery executions log
  `log_security_event(...)` with tenant/plan ids (verified in route code this run).
- No secret values printed in review artifacts (this review used file:line reporting
  only; pip-audit output contains package names/versions only).
- *Not exhaustively tested:* error responses for stack-trace leakage under
  production settings (test suite runs with `DEBUG`-style test config; G-11).

## 6. Database migration safety

- Two-head fork repaired additively (V5-21): merge revision `67080f3cfec6` is a no-op;
  `alembic heads` → single head. No migration was modified or deleted.
- Downgrades: existing migrations retain `downgrade()` bodies (standard Alembic);
  the merge revision downgrades trivially (returns to two parallel heads — the only
  honest downgrade for a merge). *Operational note:* destructive drops are not
  auto-reversable in terms of data — restore requires backups (G-16).

## 7. Operations, packaging, health

- Startup: application factory + Uvicorn; health endpoints `/health`, `/ready` exist
  (verified by route search). **No shutdown teardown** in the lifespan (P2: open DB
  connections/stream flushes on SIGTERM unhandled beyond framework defaults).
- Dependencies: pinned via pip-compile (Python 3.11, `requires-python >=3.11,<3.15`),
  no hashes; dev extras include pip-audit/bandit/ruff/mypy (audit tooling present).
- CI: exists but triggers only on `main`/`develop` while the repository is on
  `master` → **CI has never run for this repository's pushes** (P1 process finding);
  additionally ruff (628 pre-existing test-file errors) and mypy (≥5 pre-existing
  errors) are red at baseline. Details: Test Evidence Report.

## 8. Findings summary

| ID | Finding | Sev | State |
|---|---|---|---|
| S-1 | 20 dependency advisories (pyjwt/urllib3 fixable; python-jose/ecdsa not) | P1 | pyjwt/urllib3 pins bumped + suites re-run; unfixable pair documented (G-14) |
| S-2 | Git adapter payload path escape | P1 | **Fixed (V5-16)** + 4 regressions |
| S-3 | Lease/vacuous single-executor + resume bypass | P1 | **Fixed (V5-14/15)** + 4 regressions |
| S-4 | Double-compensation fall-through | P1 | **Fixed (V5-17)** + regression |
| S-5 | CI never triggers (branch mismatch); lint/type baselines red | P1 (process) | Documented → Release Decision |
| S-6 | Evidence integrity = field checks only, no `evidence_hash` recompute | P2 | Documented (V5-D3, G-4 lineage) |
| S-7 | No shutdown teardown | P2 | Documented (G-17) |
| S-8 | Lockfile without hashes | P2 | Documented (G-15) |
| S-9 | Dedicated secret scanners (trufflehog/detect-secrets/pre-commit) and DAST not runnable here | P2 (limitation) | Documented |
| S-10 | Bandit B202 / ruff S202 / semgrep ToB tarfile-extractall suppressions on the legacy fallback branch | P3 | Justified inline (per-member validation reviewed manually) + file re-scans clean |

## 9. Explicit non-claims

- No external system (cloud, KMS/Vault, SIEM, Postgres-live, Kubernetes) was
  contacted; no credential was used or printed.
- No production readiness or certification beyond the tested local scope is implied;
  external certification requires the External Validation Runbook to be executed.
