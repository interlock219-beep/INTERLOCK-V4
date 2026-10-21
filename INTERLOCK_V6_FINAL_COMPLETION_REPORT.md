# INTERLOCK V6 — FINAL COMPLETION REPORT

**Date:** 2026-10-16 · **Repo:** `F:\Desktop_Data_2026\Desktop\INTERLOCK V4` · **Branch:** `master` · **HEAD:** `145a3d9`

> This is the final evidence package for the product-completion mission. It is a **new** document;
> all prior reports (`INTERLOCK_V6_FINAL_REPORT.md`, `INTERLOCK_V6_RELEASE_GATE_R1_R4.md`,
> `INTERLOCK_V6_COMMIT_MANIFEST.md`, the V5 series) are preserved unmodified. Results in this
> report were measured during this mission; historical results are labeled as such.
>
> **No staging, commit, push, tag, publish, or deploy was performed.** The repository working tree
> is a verified candidate that is not yet committed.

---

## 1. Executive summary

Interlock is a **control plane for AI coding-agent actions**: it verifies an intent before a tool
runs, gates high-risk actions behind human approval, records tamper-evident audit evidence, and
drives verified recovery (observe → plan → compensate → verify). The product is functionally
mature and its engineering verification is now green on every check that can be executed on this
host.

**What is genuinely complete and verified**

- A fresh clone installs from tracked files, runs the **full 2860-test suite twice** (working tree
  and a fresh environment), passes lint/type/security gates, generates a validated SBOM, migrates
  a virgin database to a single head, and starts and answers health/readiness correctly.
- The dependency audit of the **documented installation path is clean: 0 known vulnerabilities
  across 110 dependencies** (`pip-audit`, exit 0). This required closing a real upstream blocker
  honestly (see §5).
- Every schema operation in the proposed migration was tested against **populated** disposable
  databases: upgrade preserves all pre-existing data byte-for-byte, and one genuine rollback
  limitation was discovered, proven, and given a verified recovery runbook.

**The single most important finding.** A dependency advisory (`mcp` CVE-2026-59951, pulled in by
Semgrep's exact pin) had made every fresh install audit red. The safe remedy was **not** to waive or
ignore the finding but to change the tool-installation architecture: Semgrep is no longer part of
the project's dependency graph (CI invokes it through `semgrep-action@v1`, which supplies its own
copy), so the audited surface is clean while security coverage is unchanged.

**What still blocks a release.** Three things, all external to the code: (a) the schema-drift
migration (M-PKG) is reviewed and proven but **not authorized to apply**; (b) CI has not run
because staging/commit/push is not authorized; (c) Docker and PostgreSQL could not be exercised on
this host. A fourth item — release artifacts omit the migrations — needs a packaging decision.

**Bottom line.** This is a credible, evidence-backed release *candidate*. It is safe for local
development and for a single-node technical evaluation today. It is **not** yet ready for
production or publication, and this report does not claim otherwise.

## 2. Repository baseline and preservation verification

| Invariant | Baseline (mission start) | End of mission | Status |
|-----------|--------------------------|----------------|--------|
| Staged files | 0 | 0 | preserved |
| `stash@{0}` | 1 stash, intact | 1 stash, intact | preserved |
| `web/` deletions | 60 | 60 | preserved |
| `interlock_projects/` | present | present | preserved |
| HEAD | `145a3d9` | `145a3d9` | unchanged |
| Modified (non-web) | 56 | 63 | +7 = documentation/tooling edited this mission |
| Untracked in scope | 54 | 57 | +3 = new reports created this mission |
| Candidate artifacts in repo | none | none | isolated |

Baseline manifest verification passed **107/107** unique paths (groups A–F, 0 duplicates, 0 missing,
0 ignored-but-included) plus the documented amendments. Evidence: `logs/v6_gate_closure/v6_final_baseline.txt`.
No `git reset --hard`, `git clean`, broad restore/checkout, or stash mutation was ever run.

## 3. Changes made (exact paths and rationale)

**Pre-existing user work (54 modified + 53 untracked + 60 `web/` deletions) was left untouched.**
This mission added/changed only the following.

| File | Change | Rationale |
|------|--------|-----------|
| `pyproject.toml` | `cyclonedx-bom>=7.0,<8.0` (was `3.2.0`); **removed `semgrep==1.181.0`** from extras | R-PKG v2 — SBOM tool conflict + CVE-2026-59951 architecture remedy (§5) |
| `.env.example` | `CORS_ORIGINS` → JSON array | R-PKG — documented format fix |
| `.github/workflows/ci.yml` | W1 install line; W2 migration step moved **before** tests | Approved W1–W5 |
| `.github/workflows/security.yml` | W3 install line; **W4-fix** SBOM command corrected to `cyclonedx-py environment --output-file … --output-format json` | Approved W3 + defect correction (the approved command was invalid for cyclonedx 7.5.0) |
| `.github/workflows/docker-verify.yml` | W5 `.env` copy step | Approved W5 |
| `scripts/run_benchmarks.py` | Distinct UUID approver in the HITL benchmark | Fixed a crash (self-approval guard + UUID-typed column); no security logic changed |
| `README.md` | Test/quality table rewritten from **measured** runs; "production-validated" softened; Alembic head corrected; web-dashboard removal disclosed; stale commit ref fixed | Documentation accuracy (§8) |
| `docs/developer/QUICKSTART.md`, `sdk/README.md` | Removed nonexistent `pip install interlock` | Package is unpublished; install path is clone-based |
| `docs/architecture/ARCHITECTURE.md` | Corrected "unauthenticated intent endpoints" → bearer-token enforced | Stale claim contradicted by code and adversarial tests |
| `SECURITY.md` | Added dependency-security/auditing disclosure (audited surface, CVE handling, accepted advisories) | Honest security posture (§3.3) |
| `docs/INDEX.md` | Indexed the new documents; disclosed `web/` removal | Doc-map accuracy |
| **New:** `INTERLOCK_V6_MPKG_MIGRATION_REVIEW.md` | §5 migration review | Required deliverable |
| **New:** `INTERLOCK_V6_GAP_REGISTER.md` | 18-item gap register | Required deliverable |
| **New:** `docs/operations/EVALUATOR_GUIDE.md` | Evaluator path + supported-configuration matrix | Customer evaluability (§8) |
| **New:** this report; R1–R4 addendum §9 | Evidence package | Required deliverable |

No security check was disabled, no migration validation weakened, no finding suppressed, and no
unrelated file overwritten.

## 4. Tests and verification (commands, exits, counts, durations)

All measured this mission. Working tree and a **fresh environment built from tracked files** were
both run to completion.

| Check | Command | Exit | Result |
|-------|---------|------|--------|
| Full suite (working tree) | `pytest tests -q --no-header --no-cov` | 0 | **2860 passed / 7 skipped / 0 failed**, 1535.59 s |
| Full suite (fresh install, CI parity, w/ coverage) | `pytest tests -q --no-header` | 0 | **2860 passed / 7 skipped / 0 failed**, 3243.58 s; coverage **83.52%** (≥80% required) |
| Ruff | `ruff check app sdk` | 0 | All checks passed |
| MyPy | `mypy app sdk` | 0 | 0 issues in 318 source files |
| Bandit (CI parity) | `bandit -r app -ll` | 0 | No issues |
| Bandit (full) | `bandit -r app` | 1 (expected) | 7 Low findings (B101×3, B110, B112×3) — documented |
| Semgrep (CI rule packs) | `semgrep scan --config p/security-audit p/owasp-top-ten p/python` | 0 | 6 WARNING findings, 0 errors, 0 in release-touched files |
| `pip check` (fresh) | `python -m pip check` | 0 | No broken requirements |
| **Dependency audit (fresh)** | `python -m pip_audit` | **0** | **0 known vulnerabilities / 110 dependencies** |
| SBOM | `cyclonedx-py environment --output-file … --output-format json` | 0 | Validated CycloneDX 1.6, 110 components |
| `git diff --check` | — | 0 | Clean |
| Alembic upgrade (virgin DB) | `alembic upgrade head` | 0 | Applied to single head `b4b471ffc2bd` |
| Alembic single head | `alembic heads` | 0 | Exactly one head |
| Alembic round-trip | `downgrade -1` → `upgrade head` | 0 / 0 | Clean |
| `alembic check` (no M-PKG) | `alembic check` | 1 (expected) | **FAIL — 33-op drift (defect D3)** |
| Startup smoke | uvicorn + `GET /api/v1/health`, `/api/v1/ready` | 200 / 200 | `{"status":"ok"}`; `{"status":"ready","db":"ok","redis":"disabled"}` |
| Benchmarks | `python scripts/run_benchmarks.py` | 0 | authz 0.0083 ms, policy-eval 1.9453 ms (1000 iters) |
| Docker build/verify | — | — | **BLOCKED EXTERNALLY** (no Docker CLI) |
| PostgreSQL runtime/migrations | — | — | **BLOCKED EXTERNALLY** (no PG service) |

The 7 skips are: 5 platform-specific performance thresholds, 1 symlink test needing admin
privileges on Windows, 1 needing an external key manager. None failed.

## 5. Security findings, fixes, and unresolved advisories

**Fixed this mission**

- **`mcp` CVE-2026-59951 (GHSA-84m7-p3x7-pcfv)** — resource exhaustion in the MCP SDK's
  streamable-HTTP server, affecting `mcp` 1.8.0–1.29.x, fixed in 1.30.0/2.2.0. Every Semgrep
  release through the latest (1.181.0, uploaded 2026-10-14) pins `mcp==1.29.0` exactly; an
  override is impossible (`ResolutionImpossible`, verified by dry-run exit 1). **Remedy (mission
  §3.2, order 2):** Semgrep removed from the installable extras. CI coverage is unchanged — both
  workflows run it via `semgrep/semgrep-action@v1`, which installs its own Semgrep. Result: the
  documented install path audits **0/110**.
- **SBOM workflow step was broken** for cyclonedx-bom 7.x (invalid subcommand + invalid option
  names, reproduced exit 2). Corrected and verified (exit 0, 110 components).

**Unresolved / accepted (disclosed, not suppressed)**

- **`ecdsa` PYSEC-2026-1325** and **`python-jose` PYSEC-2026-4298** have **no upstream fix** and
  appear only in the production runtime lock (`requirements.txt`), not in the audited install
  path. Tracked as accepted risk (G-14).
- **`virtualenv` PYSEC-2026-4011/12/13/14** affect only stale local environments; a fresh install
  resolves 21.14.8 (clean).
- **`nltk` PYSEC-2026-3740** comes from the `safety` tool, which is not part of any supported path.
- Upstream Semgrep repin of `mcp` remains open; it no longer affects the audited dependency graph.
- 7 Low bandit findings and 6 advisory-level semgrep findings are pre-existing and documented.

No `--ignore-vuln`, no audit suppression, no weakened gate. A failed audit was allowed to fail
until it was genuinely fixed by architecture.

## 6. Migration and data-safety assessment

Full review: `INTERLOCK_V6_MPKG_MIGRATION_REVIEW.md`. Summary of tested facts (disposable SQLite
DBs only; M-PKG was **never** applied to the repository or any non-disposable database):

- **Operations:** 2 create-table, 11 add-column, 4 fail-closed backfills, 3 batched
  tighten/relax, 15 guarded index creations, 4 stale index drops. Every operation is guarded, so
  re-runs are no-ops (proven: a stamped re-run produced zero schema/data change).
- **Upgrade over populated data:** all pre-existing columns and rows byte-identical; backfills
  correct (`token_id`=row id, `tenant_id`='unknown', `status`='active', `created_at` set);
  `alembic check` = 0 with data present.
- **Single head / no history rewrite:** M-PKG is a new head after `b4b471ffc2bd`; earlier history
  untouched; `alembic heads` returns exactly one.
- **Backup/restore:** verified independently — file-copy backup passes `PRAGMA integrity_check`,
  reports the correct revision, and restores losslessly.
- **Rollback limitation (discovered):** `downgrade` **fails** if any `execution_tokens.expires_at
  IS NULL` row exists (only possible after M-PKG relaxes the constraint). After such a failure the
  version is unchanged and data intact, but some indexes are dropped and an `_alembic_tmp_*` table
  is left behind. A **verified recovery runbook** is provided (drop temp tables → `alembic stamp`
  → `upgrade head` → `check`=0).
- **PostgreSQL behavior is unverified here** (no PG service) — CI's postgres service will be the
  first real check after authorization.

**The migration is necessary** (otherwise the strict drift gate keeps CI red permanently) and is
recommended for approval, with the rollback limitation accepted and the runbook used.

## 7. Installation and fresh-clone evidence

A fresh candidate tree was built from `git archive HEAD` plus the exact approved overlay (731
files; verified byte-identical to the working tree; no `requirements*.txt`, no `.env`, no
`interlock_projects/`, no DBs, no keys). In it: `python -m venv` → `pip install -e
".[dev,security]"` (exit 0) → `pip check` (0) → `pip-audit` (0/110) → SBOM (110 components) →
`alembic upgrade head` (0, single head) → uvicorn smoke (200/200). The full suite then passed
2860/7/0 with 83.52% coverage. This is the documented installation path and it works end to end.

**Limitation:** the built wheel and sdist do **not** contain `alembic/` migrations or
`.env.example`, so the migration step requires a source checkout (gap #4).

## 8. CI status and external blockers

CI has **not run**: no commit/push is authorized, and HEAD `145a3d9` predates all V6 work. The
workflows are corrected and locally validated (YAML parses; install/migration/SBOM steps verified
against the real toolchain). External blockers: **Docker** (CLI absent on this host) and
**PostgreSQL** (no service). R3 and G7 remain `BLOCKED EXTERNALLY` pending authorization and a
Docker/PG-capable runner.

## 9. Product behavior and supported configuration

See `docs/operations/EVALUATOR_GUIDE.md` for the evaluator path and matrix. Key honesty points:
replay protection without Redis is an **in-process** nonce store (single-process evaluation only);
**production mode refuses to start** without Redis, PostgreSQL, and tenant enforcement (fail-closed
startup validators). SSO (OIDC/SAML), KMS/HSM, Stripe (mock), and SMTP (logging) are placeholders
and are disclosed as such. The `web/` dashboard is removed in the working tree and unbuildable
here. Audit events live in the `audit_events` table (API-queryable) and in a hash-chained JSONL
sink that also mirrors to stdout.

## 10. Performance and reliability evidence

`scripts/run_benchmarks.py` was repaired and rerun on this host (8-vCPU Intel, Python 3.11.9,
Windows 11, 1000 iterations): authorization decision **0.0083 ms** mean (~120k/s), policy
evaluation **1.9453 ms** mean. These are single-machine, small-sample numbers and are **not** a
comparative market claim (gap #15). Reliability behavior (fencing, leases, quotas, idempotency,
shutdown/teardown, fault injection, path traversal, concurrency) is exercised by the 2860-test
suite, including the V6 recovery-gauntlet and certification-lab tests.

## 11. Release-artifact inspection

Built in the isolated candidate: `intentlock-4.0.0-py3-none-any.whl` (323 entries) and
`intentlock-4.0.0.tar.gz` (328 files). **No** `.env`, `*.db`, `keys/`, `logs/`,
`interlock_projects/`, or `web/` content; `LICENSE` and `README.md` present; metadata
`Name=intentlock  Version=4.0.0  License=Proprietary  Requires-Python: >=3.11,<3.15`, 30 runtime
dependencies. **Defect:** neither artifact contains `alembic/` migrations or `.env.example`
(gap #4). Evidence: `logs/v6_gate_closure/v6_final_sdist.tar.gz`.

## 12. Market-readiness gap register

18 items with severity, evidence, state, remediation, and closure criteria:
`INTERLOCK_V6_GAP_REGISTER.md`. Critical/High items: schema drift (M-PKG, pending approval),
artifact packaging (pending approval), CI not run (external), Docker/PG unverified (external),
SSO/KMS placeholders (accepted, disclosed), no independent pentest/compliance (accepted,
explicitly not claimed).

## 13. Gate-by-gate verdict

| Gate | Verdict | Basis |
|------|---------|-------|
| **G1 Preservation** | **PASS — VERIFIED** | stash, 60 `web/` deletions, ignored files, `interlock_projects/` all preserved; staged=0 |
| **G2 Reproducible installation** | **PASS — VERIFIED** | Fresh clone installs, migrates, starts, answers health/ready; full suite green. Limitation: source checkout required (artifact packaging gap) |
| **G3 Functional correctness** | **PASS — VERIFIED** | 2860/7/0 twice (working tree + fresh env), coverage 83.52% |
| **G4 Static/type quality** | **PASS — VERIFIED** | ruff 0, mypy 0 (318 files), bandit `-ll` 0; 7 Low + 6 semgrep findings documented |
| **G5 Security** | **PASS — VERIFIED** | Audit 0/110 on the documented path; no suppression; SBOM validated; upstream advisory resolved by architecture |
| **G6 Database safety** | **PENDING APPROVAL** | Migration reviewed, data-tested on populated DBs, runbook provided — **not applied** |
| **G7 CI** | **BLOCKED EXTERNALLY** | No commit/push authorization; CI has not run |
| **G8 Operational readiness** | **PASS — VERIFIED** | Startup/health/ready/shutdown smoke; fault-injection and fencing tests in suite |
| **G9 Release artifact** | **FAIL** | Wheel/sdist omit `alembic/` and `.env.example`; safety half (no secrets/user data) passes. Remediation needs approval |
| **G10 Customer readiness** | **PASS — VERIFIED (with disclosed limitations)** | Docs corrected against measured behavior; evaluator guide + matrix added; placeholders disclosed |
| **G11 External validation** | **BLOCKED EXTERNALLY** | Docker and PostgreSQL unavailable on this host |

## 14. Residual risks and known limitations

- M-PKG is unapplied; `alembic check` fails by design until it is authorized (D3).
- A failed M-PKG downgrade on SQLite can leave partial index loss + a temp table (recovery runbook
  verified); prefer backup-restore for rollback.
- Two runtime-lock advisories (`ecdsa`, `python-jose`) have no upstream fix (accepted, G-14).
- No Docker/PG runtime verification on this host.
- Performance figures are single-machine and small-sample.
- No independent penetration test or compliance assessment; none is claimed.
- Release artifacts are not self-sufficient for migration (source checkout required).

## 15. Exact next decisions required

1. **Authorize M-PKG** (add `v6driftbf01`) → closes G6 and unblocks the CI migration gate. Review
   in `INTERLOCK_V6_MPKG_MIGRATION_REVIEW.md`.
2. **Authorize the packaging fix** (include `alembic/` + `.env.example` in wheel/sdist) → closes G9.
3. **Authorize staging + commit** of the verified change set (manifest A–F + amendments), then a
   separate authorization to **push** → observe CI → closes R3/G7.
4. **Provide a Docker/PG-capable environment** (or authorize relying on CI) → closes G11.
5. **Decide** whether to pursue the upstream Semgrep/`mcp` repin tracking, an external pentest, and
   real SSO/KMS integrations before any commercial push.

---

# EXECUTIVE REPORT — FINAL DELIVERABLE

**What is genuinely complete?** A verified, evidence-backed release candidate: full 2860-test suite
green in two independent environments (83.52% coverage), lint/type/security gates green, dependency
audit clean (0/110) on the documented install path, validated SBOM, virgin-DB migration to a single
head, and a working startup/health/readiness path. Documentation was corrected against measured
behavior and an evaluator guide + gap register were added.

**What changed, and in which files?** `pyproject.toml` (SBOM tool + Semgrep architecture remedy),
`.env.example` (CORS format), three workflow files (approved CI fixes + a corrected SBOM command),
`scripts/run_benchmarks.py` (crash fix), and five documentation files (accuracy). Two new review
documents and an evaluator guide were created. All pre-existing user work was preserved.

**What passed and failed?** Passed: preservation, install, both full suites, ruff, mypy, bandit
(CI parity), semgrep, `pip check`, dependency audit, SBOM, `git diff --check`, alembic
upgrade/round-trip/single-head, startup smoke, benchmarks. Failed (by design/externally): `alembic
check` (33-op drift, needs the reviewed migration); CI (not authorized to run); Docker and
PostgreSQL (unavailable); release artifact completeness (migrations not packaged).

**What is still blocked?** Upstream: none blocking the audited path (Semgrep repin tracked but
isolated). External: CI execution, Docker, PostgreSQL. Approval: M-PKG application, packaging fix,
staging/commit/push.

**Can a new evaluator install and run it using the documented process?** **Yes** — clone, `pip
install -e ".[dev,security]"`, copy `.env.example`, `alembic upgrade head`, start uvicorn, verify
health/ready. That exact path was executed and verified here.

**Is it safe for a controlled pilot?** **Yes, with conditions:** single node, SQLite or the CI
PostgreSQL service, no production-mode (which requires PG+Redis), and no reliance on SSO/KMS/
dashboard (placeholders). Recovery, evidence, and approval gating are exercised by the suite.

**Is it ready for commercial production?** **No.** It needs the migration applied and CI-verified,
a Docker/PG validation pass, and the artifact-packaging decision. The accepted no-fix advisories
and absent external pentest/compliance are also production-sales considerations.

**Is it ready for publication?** **No.** It is not even committed. Publication requires staging →
commit → push → green CI → artifact fix, each behind separate authorization.

**Shortest remaining path to readiness:** (1) approve M-PKG; (2) approve the packaging fix;
(3) authorize staging+commit then push and observe CI; (4) validate on Docker/PG. Only then revisit
publication.

### Verdicts

| Dimension | Verdict |
|-----------|---------|
| **1. Local development readiness** | **READY — VERIFIED** |
| **2. External evaluation / pilot readiness** | **READY, CONDITIONAL** (single-node, no production-mode, placeholders disclosed) |
| **3. Production readiness** | **NOT READY** (migration + CI + Docker/PG validation pending) |
| **4. Publication readiness** | **NOT READY** (not committed; CI not run; artifact gap) |

*No release-readiness claim exceeds the evidence above. No staging, commit, push, tag, publish, or
deploy was performed. The candidate is verified and stopped for review.*
