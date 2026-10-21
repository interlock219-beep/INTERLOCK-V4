# INTERLOCK V6 — PHASE 0: PROTECTED BASELINE RECORD

**Recorded:** 2026-10-15 (session start) · **Nothing modified before this record.**
All git operations in this phase were read-only.

---

## 1. Git state (as found, read-only)

| Item | Value |
|---|---|
| Branch | `master` |
| HEAD | `145a3d9da178fea4be1b5459ecb47e1a555a42c5` (`145a3d9`) |
| Staged | **0 files** |
| Unstaged | **83 files**: 60 × `web/` deletions (user-owned, preserved), 15 × `app/`, 8 × `tests/` |
| Untracked | **33 paths**: 15 V5 reports, 1 alembic merge revision, 7 production files, 8 test files, 2 `interlock_projects/test-tenant/prj-*` dirs (user state) |
| Ignored | 107 entries (`.env` :41, `requirements.txt` :70, `requirements-dev.txt` :71, `.venv/` :10, caches) |
| Stash | `stash@{0}` present, **not touched** |
| CRLF notes | git warns LF→CRLF on `surgical_recovery_types.py`, `test_git_repository_adapter.py` (informational only) |

**Exclusion list (maintained for the whole mission):** 60 `web/` deletions ·
`interlock_projects/` (incl. 2 untracked test-tenant dirs) · `.env` and all
secrets/ignored files · `stash@{0}` contents · `requirements*.txt` (never
force-added) · anything not in an approved commit manifest.

## 2. Documents read

- `INTERLOCK_V5_RELEASE_DECISION.md` — status **IMPLEMENTED WITH EXTERNAL
  VALIDATION REQUIRED**; API-only staging conditional on 6 conditions;
  production blocked by G-3→G-7→G-18→G-16→G-14 chain.
- `INTERLOCK_V5_CONFIRMED_DEFECT_REGISTER.md` — V5-14..V5-21 fixed;
  **V5-D1..V5-D6 documented-not-fixed** (D1 stale-worker mid-step window,
  D2 resume stop-conditions default, D3 evidence hash never recomputed,
  D4 order-0 sort, D5 500-step truncation, D6 transaction_safe breadth).
- `INTERLOCK_V5_PROPOSED_COMMIT_MANIFEST.md` — 4 review units; **Commit 3
  void** (requirements gitignored); exclusions table.
- `INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md` — G-1..G-18 (P0: G-3/G-9/G-13).
- `INTERLOCK_V5_RECOVERY_CORRECTNESS_REPORT.md`, security/containment,
  test-evidence, independent-verification reports (prior session).

## 3. Test suite verification status

| Run | Command | Status |
|---|---|---|
| **V6 Phase 0 baseline (this session, independent)** | `& .\.venv\Scripts\python.exe -m pytest tests -q --no-header --no-cov > $env:TEMP\v6_phase0_baseline_suite.txt 2>&1` | **COMPLETE — exit code 0: 2738 passed, 7 skipped, 0 failed, 24 warnings, 1204.44s (20m04s).** Log: `$TEMP\v6_phase0_baseline_suite.txt` |
| V5 historical claim (prior session) | prior session log `v5_gate_final_suite.txt` | 2738 passed / 7 skipped / 0 failed, exit 0, 16m47s |

**Baseline gate: PASS.** The V5 claim was independently re-verified in this
session: identical counts (2738/7/0), exit 0. Environment: repo `.venv`,
Python 3.11.9, Windows, `--no-cov`. Skips observed in log include
performance thresholds (`test_policy_evaluation.py` — platform-specific),
key manager (`test_regression_critical_fixes.py`), and the remaining
quota-contract/platform skips (7 total, all with reasons in log).

Starting Git state re-confirmed at gate time: `master` @ `145a3d9`,
staged = 0, unstaged = 83, untracked = 34 (33 prior + this Phase 0 record),
`stash@{0}` intact. No drift from Phase 0 record.

## 4. Tooling (verified this session)

| Tool | Version | Note |
|---|---|---|
| Python | 3.11.9 (repo `.venv`) | 8 CPUs |
| pytest / ruff / mypy / bandit / alembic | 9.1.1 / 0.16.3 / 1.20.2 / 1.9.4 / 1.19.1 | all runnable |
| semgrep | 1.173.0 (`semgrep.exe`, not `python -m`) | `python -m` deprecated |
| pip-audit | console script `.venv\Scripts\pip-audit.exe` | **reproduced: 3 advisories / 2 packages** (ecdsa ×2 same ID, python-jose ×1); exit 1 |
| Installed clients | `psycopg2-binary 2.9.12`, `redis 4.6.0`, `SQLAlchemy 2.0.52`, sqlite 3.45.1 | **no local service on :5432/:6379** |
| Migration graph | `alembic heads` = `67080f3cfec6` (single head) | V5-21 fix intact |

**Environment implication:** real multi-instance proofs must use either
(SQLite file + independent OS processes = genuinely independent clients) or
await authorized external infra. No local Postgres/Redis server exists;
creating one locally would require downloads — treat as blocked unless approved.

## 5. Architecture map (read from source, not reports)

- **Adapter contract:** `app/domain/services/recovery_adapter.py` —
  `CompensatingActionAdapter` runtime-checkable Protocol: `supports`,
  `capture_recovery_evidence` (+`before_snapshot`), `classify_reversibility`,
  `simulate`, `check_preconditions`, `detect_drift`, `check_conflicts`,
  `generate_compensation`, `execute_compensation`, `verify`,
  `declare_capabilities`; `RecoveryAdapter` ABC = legacy trio + fail-closed
  defaults (base `verify` always False; base execute → `REQUIRES_MANUAL_ACTION`).
- **Registry/certification:** `recovery_adapter_registry.py` (contract
  battery + strict/lenient registration), `recovery_certification_lab.py`
  (behavioral probes vs contract-only), `certification_probes.py`.
- **Orchestration:** `distributed_recovery_orchestrator.py` — `PlanLeaseStore`
  Protocol + `InMemoryPlanLeaseStore` (TTL, fencing, release tombstones),
  process-wide default store (V5-14), lease-guarded `execute_durable_plan`/
  `_do_resume_plan` (V5-15), step-level execute→verify isolation (V5-17),
  multi-adapter verification (V5-18).
- **Durable state ports:** `durable_recovery_repository.py`
  (`RecoveryLeaseRepository` with `expected_fencing_token`, worker registry,
  reconciliation/orphans/coordination) + `causal_state_repositories.py`
  (`DurableExecutionRepository.save(step)` — **no fencing parameter = V5-D1**).
  Implementations: `SQLAlchemyDurableExecutionRepository` (SQL),
  `InMemoryDurableRecoveryRepository` only — **no SQL lease/worker repo yet**.
- **Evidence:** per-adapter ad-hoc `evidence_hash` formulas (sha256 over
  action_id:payload / payload identity — **no canonical spec = V5-D3**);
  `EvidenceVerificationService.verify_evidence_integrity` = field-presence
  only; `verify_evidence_chain` = time-gap order only.
- **Quota:** `QuotaCounterStore` Protocol + `InProcessQuotaCounterStore`
  (V5 contract, cross-instance wiring tested in-process).
- **Identity/authN:** JWT token service, Ed25519 execution tokens, API keys,
  MFA, SSO (OIDC/SAML), sessions; `dependencies/auth.py` + `security.py`.
- **AuthZ/policy:** `authorization_service`, `central_policy_engine`,
  `advanced_authorization_service`, `authority_lineage_service`, approval
  routes (`/pending`, `/approve`, `/reject`, `/revoke`), `emergency_control_service`,
  `action_control_service`, `risk_engine`, `token_scope_enforcement_service`.
- **Execution boundary:** routes import `require_recovery_executor`;
  adapters enforce tenant/authorization/idempotency inside
  `execute_compensation` (base-class helpers).
- **Tests:** 142 unit / 36 integration / 5 stress / 5 performance files,
  incl. `recovery_lab` (crash/concurrency/verification phases) and
  `recovery_gauntlet` harness.

## 6. Known-defect inventory (confirmed inputs for planning)

V5-D1..D6 (above) + gaps G-1 (process-local leases), G-2 (no distributed
quota backend), G-3/G-9 (no live integrations), G-4/G-6 (evidence trust,
config_dir provenance), G-7 (no web frontend — separate decision, never
recreate), G-13 (uncommitted work), G-14 (unfixable deps), G-16 (no
backup/restore), G-17 (no shutdown teardown), G-18 (CI never runs + red
lint/type baselines).

---

## 7. Prioritized engineering plan (V6)

Ordering = mission phase order (correctness → coordination → evidence →
boundary security → adapters/faults → ops). Small reviewable units; each:
regression-first → minimal fix → targeted → neighbors → diff review.

| # | Work package | Pillar | Depends on | Risk | Test criteria | Rollback |
|---|---|---|---|---|---|---|
| **WP-1** | **Evidence canonicalization (V5-D3):** versioned canonical evidence serialization (`evidence_hash_spec: v1\|v2`), `compute_evidence_hash()` shared by adapters, `verify_evidence_integrity` **recomputes** for v2 evidence + tamper detection; v1 evidence keeps field-presence path (backward compatible) | 5 | none | Medium (schema contract) | RED: tampered field must fail verify; GREEN: round-trip + cross-adapter consistency; neighbors: evidence/surgical suites | version gate: v1 path unchanged, flag to revert |
| **WP-2** | **Fencing at the write boundary (V5-D1):** `DurableExecutionRepository.save(step, expected_fencing_token=None)` → SQLAlchemy impl rejects saves from stale tokens; orchestrator passes its lease token per step; stale-worker save = rejected + `lease_lost` (no mid-step silent write) | 3 | none | Medium (port change; default None = backward compatible) | RED: stale-token save rejected; GREEN: normal flow unaffected; **multi-process test (SQLite file, 2 OS processes)**: loser cannot commit | optional param → old callers unaffected; revert impl |
| **WP-3** | **Shared lease + quota backends (G-1/G-2):** `SQLPlanLeaseStore` / `SQLQuotaCounterStore` (SQLAlchemy, atomic conditional UPDATE/INSERT-ON-CONFLICT) implementing existing Protocols; wire as opt-in via settings; runbook §6/§7 evidence produced locally via **multi-process SQLite** tests | 3 | WP-2 (token semantics) | Medium | multi-process acquire/renew/expiry-takeover/quota atomicity under contention; contract tests must pass unchanged against SQL stores | opt-in constructor arg; default stays in-process |
| **WP-4** | **Independent verification hardening (Pillar 4):** adversarial verifier suite — adapter lies / stale data / omits resource / partial success / verify-crash; verifier consults *observed state* not adapter claims; result vocabulary enforced (`INSUFFICIENT_EVIDENCE` never → success) | 4 | WP-1 (evidence recompute gives teeth) | Low | new adversarial tests fail on current gaps, then fix minimal | tests-only + small service changes |
| **WP-5** | **Backup/restore of plans + evidence (G-16):** export/import utility (SQLite snapshot + evidence dump with hash manifest), disposable-env drill: create plan+evidence → backup → destroy → restore → evidence chain verifies | 10 | WP-1 (integrity check on restore) | Low-Med | drill script green in temp dirs; restore evidence chain validates | new additive files only |
| **WP-6** | **Scenario proofs A–J (mission Phase 5):** end-to-end integration tests in disposable sandboxes covering agent-edit restore, partial failure honesty, user-conflict detection, crash-resume, stale-worker fencing, tenant denial, lying adapter, refusal-of-irreversible, corrupted evidence, backup drill | 1,4,7 | WP-1..WP-5 as applicable | Low (tests) | each scenario asserts all 6 required properties or is marked BLOCKED | tests only |
| **WP-7** | **Deterministic fault injection (Pillar 7):** orchestration-transition crash matrix (inject exception/kill at each state transition), duplicate/delayed requests, verifier failures — deterministic, no sleep-based flakiness | 7 | WP-2 | Low | matrix tests deterministic across 3 runs | tests only |
| **WP-8** | **Execution-boundary bypass tests (Pillar 6):** alternate-path policy bypass probes (direct adapter call, malformed args, race, alternate API), prove enforcement at execution time; fix any reachable bypass | 6 | none | Med (may expose real bypass) | adversarial tests; any fix regression-first | per-fix |
| **WP-9** | **CI repair (G-18, safe subset):** retarget workflow triggers to `master` (+PR), align lint step with achievable-clean scope if measurable green (`app`+`sdk`), keep full baseline documented; **no external settings changed, no push** | 10 | none | Low (file edit only) | `ruff check app sdk` measured; workflow YAML validated locally | revert file |
| **WP-10** | **Shutdown teardown (G-17):** lifespan shutdown hook (dispose engine, flush) + graceful-stop test | 10 | none | Low | startup/shutdown test green | revert |
| **WP-11** | **Benchmarks v2 (Pillar 8):** lease contention + concurrent-tenant throughput percentiles vs V5 baseline, documented hardware | 8 | WP-3 | Low | reproducible numbers, budgets unchanged unless justified | tests only |

**Explicitly blocked / not attempted without authorization:** live
cloud/Vault/SIEM/Postgres/Kubernetes validation (G-3), installing new
services (Postgres/Redis downloads), any commit/push/tag/deploy,
`web/` restoration, stash operations, paid resources.

**Stop conditions:** any package requiring unavailable infra/credentials or
ambiguous user-data decisions → stop and report at that boundary.

---

## 8. V6 run log (evidence, in order)

Every claim = recorded command, exit code, counts, log path. Shells use
PowerShell (`;`, not `&&`).

### Doc-WP-1 — Evidence integrity v2 (done)
- RED (two-stage: collection + behavioral, as recorded earlier) → GREEN:
  `pytest tests/unit/test_evidence_integrity_v2.py` → **39 passed, exit 0**.
- Neighbors: unit run **2305 passed / 1 failed** (MagicMock stub, root-caused,
  fixed) → 3-file re-run **110 passed, exit 0**; WP-1 diff reviewed.
- Deliverables: `app/domain/services/evidence_hash.py` (v2 canonical hash +
  `seal_evidence`), all 11 adapters + base sealed, `INTERLOCK_V6_EVIDENCE_V2_SPEC.md`.

### Doc-WP-2 — Durable write fencing (done)
- RED: `tests/unit/test_durable_execution_fencing.py` → `ModuleNotFoundError:
  StaleFencingTokenError` (**exit 2**, feature absent) → GREEN: **11 passed,
  exit 0** (4.02s) incl. deterministic multi-process subprocess proof
  (exit codes 0/42/1, no sleeps).
- Neighbors: **328 passed, 5 skipped, 0 failed, exit 0** (754.72s,
  `$env:TEMP\v6_wp2_neighbors.txt`).
- Gates: `ruff check app sdk` **exit 0**; `mypy app` **0 errors / 307 files**;
  `alembic heads` single `a63190d7e268`; migration matrix all **exit 0**
  (fresh-skip / add / drop / idempotent-skip branches); `git diff --check` exit 0.
- Pre-existing finding (documented, not rewritten): `3cebbede5768.upgrade()`
  drops 8 causal-state tables; fresh DBs are healed by `Base.metadata.
  create_all` at app startup — `a63190d7e268` is inspector-guarded so
  `alembic upgrade head` stays green on every path.

### Security-scan triage (evidence for G-3/G-9; no code changes needed)
- `pip-audit` (CI invocation, bare) → **exit 1; 12 rows / 4 packages**
  (ecdsa 0.19.2 ×2 rows PYSEC-2026-1325, nltk 3.10.3 PYSEC-2026-3740,
  python-jose 3.5.0 CVE-2026-85394 — no fix versions listed; virtualenv
  21.7.4 ×4 advisories with fix 21.7.11–13, dev-only; `intentlock` skipped,
  not on PyPI). Log: `$env:TEMP\v6_pip_audit.txt`. Release blocker stays
  (auth-adjacent deps without upstream fix).
- `bandit -r app -ll` (CI) → **"No issues identified", exit 0**. All-levels
  run: **7 LOW** = 3×B101 type-narrowing asserts (`causal_graph_service`),
  1×B110 documented rot13 fallback, 3×B112 documented `# noqa` resilience
  paths — none security-impacting; accepted with reasons. Log: `v6_bandit.txt`.
- `semgrep --config=p/security-audit --config=p/owasp-top-ten app` →
  **6 WARNING findings, 0 errors, 307 files / 202 rules**, all triaged FP with
  evidence: 3× logger-credential match on `token_revocation_service` log a
  token **ID** and two integer **counts**; 3× SQLi-taint rule treats
  `use_case.execute(request…)` as a DB cursor (FastAPI app layer). Raw-SQL
  audit of `app/`: only `health.py` `text("SELECT 1")` (constant) and
  `database_recovery_adapter.py` f-string SQL whose identifiers are
  whitelist (`_validate_table_name`) + regex (`_validate_column_name`)
  validated with parameterized values. Logs: `v6_semgrep.txt/.json`.

### Doc-WP-4 — Independent verification hardening (done: integrity fail-closed + adversarial suite)
- RED (integrity): `TestIntegrityLayerFailClosed::test_integrity_no_evidence_is_inconclusive_not_verified`
  failed with `status=VERIFIED` recorded (**exit 1**) — reproduced the
  fail-open at `independent_verification_service.py:_check_integrity`
  (evidence absent → hash current state → claimed VERIFIED).
- Fix 1: no-evidence path now returns `(False, INCONCLUSIVE)` with
  `reason="no evidence provided: integrity unverifiable"`, keeps `state_hash`
  for forensics; GREEN: `test_domain_i_verification.py +
  test_independent_verification_service.py + test_evidence_verification.py`
  → **88 passed, exit 0**.
- RED (adversarial): `tests/unit/test_adversarial_verification.py` →
  **7 failed / 2 passed, exit 1**, each for the intended reason:
  fail-open `VERIFIED` (empty report; stale evidence; evidence-lookup
  crash → repo was never consulted), feature-absent `TypeError`
  (`observed_states`, `expected_action_ids`), and `AttributeError:
  'NoneType' object has no attribute 'get'` at the status line (malformed
  entry crashed the whole verification).
- Fix 2 (`independent_verify`, both new params optional — existing callers
  unchanged): empty report → `INCONCLUSIVE` early return; observation
  decides per action with `claim_diverged` recorded (never verified on
  divergence); injected evidence repo consulted per action (evidence from
  another incident → `EVIDENCE_CONFLICTING`, lookup exception →
  `INCONCLUSIVE`, both fail closed); expected-but-absent resources recorded
  as omitted → `INCONCLUSIVE`; malformed entries fail their entry without
  crashing the run.
- GREEN: adversarial + 3 verification files → **97 passed, exit 0** (3.78s).
- Gates: `ruff check app sdk` **exit 0**; `mypy app` **0 errors / 309 files**.
- Vocabulary pin: `VerificationConfidence(can_claim_recovered)` excludes
  `INSUFFICIENT_EVIDENCE` and forces `requires_human_review` — asserted in
  `test_confidence_insufficient_evidence_cannot_claim_recovery` (green pin).

### Doc-WP-3 — Shared lease + quota backends (done)
- RED: `tests/unit/test_sql_lease_quota_stores.py` + quota contract →
  `ModuleNotFoundError: coordination_models` (**exit 2**, feature absent).
- GREEN: **30 passed, exit 0** (15.43s): shared lease contract body run
  against *both* backends, multi-process drills (held-lease refusal,
  takeover token+1, stale-owner renew refusal — child exit codes 0/42),
  4×5 quota attempts across 4 processes admitted **exactly 12** at limit 12,
  service-over-SQL parity, selector tests (`memory` default / `sql` opt-in /
  `redis` → loud `ValueError`, G-3). Quota contract tests parameterized
  over `memory|sql` — **zero assertions changed**.
- Neighbors: **483 passed, 1 skipped (pre-existing Windows symlink), 0
  failed, exit 0** (451.20s, `$env:TEMP\v6_wp3_neighbors.txt`) incl.
  integration execute-route + stress live-agent recovery + rollback service.
- Gates: `ruff check app sdk` **exit 0**; `mypy app` **0 errors / 309 files**;
  `alembic heads` single `b4b471ffc2bd`; migration round-trip on scratch DB
  **exit 0/0/0** — tables present → absent → present, version
  `b4b471ffc2bd` → `a63190d7e268` → `b4b471ffc2bd`.
- Wiring: `INTERLOCK_LEASE_BACKEND` / `INTERLOCK_QUOTA_BACKEND`
  (runbook §6/§7 selectors; default `memory` preserves current behaviour)
  at both `control.py` execute/resume sites, both `surgical_recovery.py`
  sites, and the process-wide `quota_service`. `SessionRollbackService`
  constructs the orchestrator **tests-only** today; any future production
  caller must inject `build_plan_lease_store()` (documented; layering kept:
  domain never imports infrastructure).
- Scope honesty: SQLite multi-process results are process-level evidence
  over a single database file — **not** a distributed-database (Postgres/
  Redis) correctness proof; runbook §6/§7 `redis` drills remain blocked on
  authorized infrastructure (G-3).

### Doc-WP-5 — Backup/restore of plans + evidence (G-16) (done)
- Constraint honored: **new additive files only** —
  `app/infrastructure/backup_restore.py` + `tests/unit/test_backup_restore_drill.py`;
  zero edits to existing app files (verified: only these two files were
  created for this WP).
- RED: `pytest tests/unit/test_backup_restore_drill.py` → collection error
  `ModuleNotFoundError: app.infrastructure.backup_restore` (**exit 2**,
  feature absent). One import defect (`sessionmaker` from `sqlalchemy`
  instead of `sqlalchemy.orm`) surfaced inside the RED window and was fixed
  before the fix run — no assertions were ever weakened.
- GREEN: **5 passed, exit 0** (5.77s). The disposable-env drill runs wholly
  in `tmp_path`: seed 1 plan + 2 sealed evidence rows → export
  (sqlite3 backup-API snapshot + exact v2 canonical-preimage dump + SHA-256
  manifest) → `db.unlink()` destroy → restore → evidence chain re-verified
  through the repository's public `list_by_incident` + plan row survives.
- Tamper drills each fail closed at the layer that owns the integrity
  (`pytest.raises(BackupVerificationError)`):
  edited dump artifact → *manifest mismatch*; edited record with recomputed
  manifest → *per-record v2 hash mismatch*; removed record with recomputed
  manifest → *evidence count mismatch*; edited snapshot row with recomputed
  manifest → *restored evidence chain broken* (WP-1 check over restored rows).
- Neighbors: `test_evidence_integrity_v2.py` + `test_surgical_recovery_pipeline.py`
  + drill → **71 passed, exit 0** (8.74s, `$env:TEMP\v6_wp5_neighbors.txt`).
- Gates: `ruff check app sdk` **exit 0**; `mypy app` **0 errors / 310 files**.

### Doc-WP-6 — Scenario proofs A–J (Phase Five, done)
- Deliverable: `tests/integration/test_scenario_proofs_v6.py` — one test per
  scenario A–J, each asserting all six Phase-Five requirements (resource
  state, honest recovery verdict, unrelated data intact, retry safety,
  evidence fidelity, refusal of unsupported guarantees). The module docstring
  quotes scenarios A–J and PILLAR 7 P1–P6 verbatim (mission text reproduced
  in the appendix below). No scenario is BLOCKED: every environment the
  scenarios need (disposable filesystem, SQLite, in-process orchestrator,
  local HTTP app, local audit sink) exists on this machine.
- **RED (honest first run):** `pytest tests/integration/test_scenario_proofs_v6.py`
  → **3 failed, 7 passed, exit 1** (15.04s, `$env:TEMP\v6_wp6_first_run.txt`).
  Triage:
  - **F (genuine product gap):** cross-tenant evidence denial returned 404 but
    recorded **0 security events** — the mission requires "denied **and
    audited*". Fix applied (scope deviation, product file):
    `app/presentation/api/v1/routes/surgical_recovery.py::get_recovery_evidence`
    now calls `log_security_event("recovery_evidence_access_denied", tenant_id=…, evidence_id=…)`
    before raising 404.
  - **B/C (test-assertion bug, not product):** after a partial/blocked run the
    plan outcome is UNKNOWN, so `retry` raises
    `Cannot execute plan with UNKNOWN reversibility — fail closed`
    (`recovery_planning_service.py:210`, the outcome gate) **before** the
    status gate the tests asserted. Assertions were corrected to
    `match="fail closed"` — retry **is** refused (the fail-closed contract);
    no assertion was weakened and no test removed.
- **GREEN (second run):** `pytest tests/integration/test_scenario_proofs_v6.py`
  → **10 passed, exit 0** (8.44s, `$env:TEMP\v6_wp6_second_run.txt`).
- Evidence classes per scenario (mocks never counted as live proof):
  A/C/G/H/J run **local production code**; B uses a mock adapter labeled as
  the unavailable external system (partial-recovery reporting is proven, the
  external system itself is not); D/E run the real orchestrator + SQLite +
  lease fencing; F is a real HTTP request through the app with a real audit
  sink; I is the production v2 evidence seal; J is the production backup
  utility.
- Neighbors: `tests/integration` + `tests/unit/test_surgical_recovery_pipeline.py`
  → **448 passed, 1 skipped, 0 failed, exit 0** (368.73s,
  `$env:TEMP\v6_wp6_neighbors.txt`; the skip is the pre-existing
  symlink-requires-admin Windows skip).
- Gates: `ruff check app sdk` **exit 0**; `mypy app` **0 errors / 310 files**.

#### Appendix — mission text quoted by the WP-6 module docstring
> **7. PHASE FIVE — PROVE RECOVERY BEHAVIOR**
> Build end-to-end scenarios in disposable environments.
> At minimum demonstrate:
> A. An AI agent modifies a project file; Interlock captures the baseline, records the change, restores the prior state, and independently verifies it.
> B. An agent modifies multiple files and one recovery step fails; Interlock reports partial recovery accurately and preserves unrelated changes.
> C. A user edits a file after the agent's change; Interlock detects the conflict and does not silently overwrite the user's edit.
> D. A recovery worker crashes and restarts; orchestration resumes safely without duplicate destructive actions.
> E. Two workers compete for the same recovery plan; stale workers cannot commit writes after losing authority.
> F. A tenant attempts to access another tenant's recovery evidence; access is denied and audited.
> G. An adapter returns success while leaving incorrect state; independent verification detects the mismatch.
> H. A recovery operation is unsupported or irreversible; Interlock refuses to promise rollback and reports the safe alternative.
> I. Evidence is corrupted or unavailable; Interlock reports uncertainty rather than inventing success.
> J. Backup and restore recover Interlock's own required metadata and evidence in a disposable environment.
> Record reproducible results for every scenario. If an environment is unavailable, label the scenario blocked instead of simulating a pass.
>
> **PILLAR 7 (P1–P6, asserted by every scenario test):** 1. The resulting
> resource state. 2. Whether recovery is complete, partial, failed, or
> uncertain. 3. Whether unrelated user data remains intact. 4. Whether retry
> is safe. 5. Whether evidence accurately reflects what occurred. 6. Whether
> the system refuses unsupported guarantees.

### Doc-WP-7 — Deterministic fault injection (Pillar 7) (done)
- Deliverable: `tests/unit/test_fault_injection_matrix_v6.py` — **18 tests**:
  8-point crash matrix (list_load, lease_heartbeat_first, evidence_load,
  lease_heartbeat_between_steps, drift_check, execute_phase, verify_phase,
  durable_write), 3× full-matrix determinism (byte-identical JSON snapshots
  excluding ids/timestamps/fencing tokens), 4 duplicate/delayed/reordered
  request tests, 3 verifier-failure tests, 2 route-honesty tests. One-shot
  `InjectedCrash` at exact call counters — **no sleeps/timers**; asyncio.Event
  gates for concurrency; `_RecordingAdapter` counts every
  `execute_compensation` invocation including faulted ones; `_Env` carries the
  target plan plus an untouched bystander plan (PILLAR 7 P3).
- **Genuine defect found by this WP (false-verification-claim):**
  `execute_durable_plan` reported `EXECUTED_AND_VERIFIED` whenever all steps
  succeeded even when every step's `verification_passed` was `False`
  (MockRecoveryAdapter.verify always returns False), and the surgical execute
  route unconditionally mapped `completed → SAFE_AUTOMATIC`. Fixes:
  orchestrator tracks `unverified_count` and requires
  `verified_every_step = all_succeeded and unverified_count == 0`; the route
  now gates `SAFE_AUTOMATIC` on
  `verification_status == EXECUTED_AND_VERIFIED.value`, else `UNKNOWN`.
  Decision: `_do_resume_plan` intentionally carries **no**
  `verification_status` key (resume-verification persistence semantics are
  ambiguous and out of WP-7 scope; an absent key is not a false claim).
- **RED:** 13 passed, **5 failed, exit 1**
  (`$env:TEMP\v6_wp7_first_run.txt`) — all five the same defect above.
- **GREEN:** **18 passed, exit 0** (2.28s, `$env:TEMP\v6_wp7_second_run.txt`).
- Post-GREEN style sweep: `ruff check` on the file reported C408×8/C420×1
  (mechanical dict-literal rewrites, outside the `app sdk` gate) — fixed with
  `ruff --fix --unsafe-fixes` and re-verified: **18 passed, exit 0**
  (`$env:TEMP\v6_wp7_style_rerun.txt`); the final full-suite run below
  covers the final file state.
- Neighbors: `pytest tests/unit tests/integration -q` → **2783 passed,
  2 skipped, 0 failed, exit 0** (1031.61s, `$env:TEMP\v6_wp7_neighbors.txt`).
  Both skips pre-existing (key manager unavailable; symlink requires admin).
- Gates: `ruff check app sdk` **exit 0**; `mypy app` **0 errors / 310 files**.

### Doc-WP-8 — Execution-boundary bypass: emergency-deny enforcement (Pillar 6) (done)
- Discovery: `EmergencyControlService.evaluate_authorization` /
  `is_emergency_deny_active` had **zero callers in any execution path** —
  deny was activatable through the emergency routes but never enforced at
  execute/resume time (the "policy decision in the UI is insufficient" bypass
  the mission names explicitly).
- Deliverables:
  - `get_emergency_control_service()` process-wide singleton in
    `emergency_control_service.py`; `routes/emergency.py` now activates
    through it (activation and enforcement share one state object);
  - new guard `app/presentation/api/dependencies/emergency_guard.py`
    (`assert_execution_permitted(tenant_id)` → 403) wired into **all five
    execution entry points**: surgical `/recovery/plan/{id}/execute` +
    `/resume`, control `/recovery/execute` + `/recovery/{id}/resume`,
    intent `/intent/execute`;
  - `tests/integration/test_execution_boundary_bypass_v6.py` — **12 tests**
    (4 emergency-enforcement + 8 fail-closed guard/status checks incl.
    cross-tenant 404, adapter idempotency conflict, filesystem traversal).
- **RED (recorded in two stages):**
  - run 1: collection `ImportError` — `get_emergency_control_service`
    absent, **exit 2** (feature absent, `$env:TEMP\v6_wp8_first_run.txt`);
  - shared singleton added without enforcement → behavioral RED:
    **4 failed / 8 passed, exit 1** (`$env:TEMP\v6_wp8_third_run.txt`) —
    control and intent paths literally logged `recovery_executed` while deny
    was ACTIVE (bypass evidence captured in the log).
- Test-bug fixes inside the RED window (no assertion weakened):
  `status`→`plan_status` NameError; `CompensationAction` missing
  drift/conflict/verification/dependency fields; control-test user needed an
  executor role (register hard-codes `viewer`, so tests mint an admin JWT the
  way `test_replay_and_token_security` does); `_PlanRepo.update_status`
  completed so the pre-fix failure mode reads DID-NOT-RAISE, not AttributeError.
- **GREEN:** **12 passed, exit 0** (3.41s, `$env:TEMP\v6_wp8_green_run.txt`).
- Documented non-changes (checked, not bypasses): control `/recovery/execute`
  accepting SIMULATED plans is by design (planning-service `execute_plan`
  also accepts SIMULATED); control resume lacking an APPROVED check is benign
  (no steps exist pre-execution).
- Scope honesty: enforcement state is process-wide in-memory — multi-instance
  deny propagation requires shared infrastructure (**G-3, category 4**).
  WP-8 network resets / disk exhaustion / permission changes / key-rotation
  faults remain BLOCKED (live infra) and were never simulated.
- Gates: `ruff check app sdk` **exit 0**; `mypy app` **0 errors / 311 files**.

### Doc-WP-10 — Predictable shutdown teardown (G-17) (done)
- Deliverable: `tests/unit/test_lifespan_shutdown_v6.py` (**2 tests**) +
  fix in `app/main.py`: the lifespan post-yield teardown now runs
  `finally: database.engine.dispose()` so a stop/restart deterministically
  releases pooled DB connections (previously nothing ran after `yield`).
- **RED:** **2 failed, exit 1** (`$env:TEMP\v6_wp10_first_run.txt`) —
  teardown disposed nothing (0 calls), confirming G-17.
- Test correction inside the loop (not a weakened product assertion): the
  original `client.is_closed` assertion tested a starlette TestClient
  property — probed behavior showed it stays `False` after context exit and
  the transport still serves, i.e. it was mis-scoped to a third-party client.
  Replaced with the real guarantee: teardown fires **exactly once** at
  context exit, and a restart cycle (second lifespan) serves again and
  disposes once more.
- **GREEN:** **2 passed, exit 0** (`$env:TEMP\v6_wp10_green_run.txt`).
- Honest limits: `SecurityMetrics` are in-memory counters with no exporter —
  there is no flush target to wire; OTel shutdown is not wired either (both
  documented for the gap assessment, never faked). Multi-instance connection
  drain under live Postgres remains BLOCKED on G-3.
- Gates: `ruff check app sdk` **exit 0**; `mypy app` **0 errors / 311 files**.

### Doc-WP-11 — Benchmarks v2 (Pillar 8) (done)
- Deliverable: `tests/performance/test_coordination_benchmark_v6.py` —
  lease-contention burst (100 concurrent `try_acquire` on one plan, exactly
  one winner), lease churn (acquire→renew→release ×200 after warm-up),
  concurrent-tenant throughput (8 tenants × 3-step durable plans executed
  concurrently, per-plan percentiles + aggregate throughput).
- Hardware documented in the module docstring (calibration machine,
  2026-10-15): Intel(R) Core(TM) i5-10310U CPU @ 1.70GHz (8 logical cores),
  15.6 GB RAM, Windows 11 Pro.
- **Calibration run: 3 passed, exit 0** (0.54s,
  `$env:TEMP\v6_wp11_calibration.txt`) with measured values printed:
  - lease burst: p50 **0.0033 ms**, p95 **0.0048 ms** (n=100);
  - lease churn: p50 **0.0246 ms**, p95 **0.0265 ms** (n=200);
  - concurrent-tenant: p50 **2.52 ms**, p95 **2.84 ms** per plan;
    throughput **1601.8 plans/s** (wall 5.0 ms for 8 concurrent plans).
- Budgets (all ~5× measured or wider, so loaded CI machines never flake):
  burst/churn p95 ≤ **5.0 ms** (sub-ms noise floor — 5× measured sits below
  the floor, so the floor governs); concurrent-tenant p95 ≤ **50 ms**
  (~17×); throughput ≥ **10 plans/s** (~160× headroom). V5 baselines are
  unchanged and still enforced by the V5 benchmark file (orchestrator
  10-step p95 1.04 ms / budget 10 ms; env capture p95 0.124 ms …).
- Hygiene: measurement `print`s kept (house style — stress suites print
  measurements); numbers also recorded in each test docstring above.
- Covered by the final full-suite run below.

### Doc-Final — Full validation to completion (2026-10-15)

All gates re-run on the **final** working-tree state, after code freeze:

| Gate | Command | Result | Exit | Log |
|---|---|---|---|---|
| Full suite | `pytest tests -q --no-header --no-cov` | **2860 passed, 7 skipped, 0 failed**, 1254.86s (0:20:54) | **0** | `$env:TEMP\v6_final_validation_suite.txt` |
| Lint | `ruff check app sdk` | All checks passed | 0 | — |
| Types | `mypy app` | Success: no issues in **311** source files | 0 | `$env:TEMP\v6_final_mypy.txt` |
| Security | `bandit -r app` | **0 High / 0 Medium / 7 Low** (49,464 LOC); lows itemized + triaged in final report Part 9; `# nosec` count **0** | 1 (findings-present) | `$env:TEMP\v6_bandit_final.txt` |
| Security | `semgrep --config auto app --json` (CI parity) | **42 findings, 0 errors** — identical to V5's pre-existing baseline (43 − 1 fixed); **0 in campaign-new files**; 19 in `database_recovery_adapter.py` on untouched lines (diff-verified: 0 added/removed `execute`) | 0 | `$env:TEMP\v6_semgrep_auto_final.json` |
| Security | `semgrep --config=p/security-audit app` | 311 files, **0 findings** (remote ruleset changed since earlier campaign run of same config — caveat recorded) | 0 | `$env:TEMP\v6_semgrep_final2.json` |
| Dependencies | `pip-audit` | **12 known vulns in 4 pkgs** — virtualenv ×8 fixable (21.7.11–13); ecdsa ×2, nltk, python-jose: no fix (G-14 accepted) | 1 (findings) | `$env:TEMP\v6_pip_audit_final.txt` |
| Migrations | `alembic heads` | **single head `b4b471ffc2bd`** | 0 | — |
| Whitespace | `git diff --check` | no whitespace errors (LF/CRLF notices only) | 0 | — |
| Staging state | `git diff --cached --name-only` | **0 paths staged**; `web/` deletions **60** preserved; `stash@{0}` untouched | — | `$env:TEMP\v6_git_state.txt` |

- **Suite accounting:** final 2860 = Phase-0 baseline 2738 + **122 net-new
  tests** added by the campaign's work-package files (WP-1..WP-11
  deliverables); same 7 skips as baseline with identical reasons
  (5× platform thresholds, 1× symlink-requires-admin, 1× key manager
  unavailable); **0 failed at every stage since Phase 0**.
- WP-8/WP-10 neighbor coverage: both changes (5 route wirings + `app/main.py`
  lifespan) are covered by this final full-suite run (routes exercised by
  integration suites; lifespan by the `client` fixture on every test) —
  no separate neighbor run was claimed for them.
- Security/diff review: performed over `git diff HEAD` (54 modified, 2030
  insertions across the tracked diff; 0 suspicious/secret/debug added lines,
  0 `.env` references, 0 out-of-scope paths) + the 12 new `app/` files
  (0 secret-pattern hits); full numbers and triage in
  `INTERLOCK_V6_FINAL_REPORT.md` Parts 9–10; commit proposal in
  `INTERLOCK_V6_COMMIT_MANIFEST.md` (A–F, **nothing staged**).
