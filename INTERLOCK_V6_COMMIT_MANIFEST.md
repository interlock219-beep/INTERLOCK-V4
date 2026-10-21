# INTERLOCK V6 — Proposed Selective Commit Manifest (A–F)

**Date:** 2026-10-15 · **Branch:** `master` · **HEAD:** `145a3d9`
**State at authoring:** nothing staged (`git diff --cached --stat` = empty,
0 staged paths), nothing committed, nothing pushed, no tags. `stash@{0}`
untouched. The user's 60 `web/` deletions are intact and excluded.

**Authorization status:** this is a *proposal only*. Per instruction, no
`git add`/`commit`/`push`/`tag`/`publish` will occur without separate
explicit approval of this exact manifest.

---

## How to read this

- Groups A–E are the proposed commits (one logical unit each, smallest
  reviewable sequencing order A → E; each commit is independently
  revertible).
- Group F is the explicit exclusion list — files that exist in the working
  tree but must **never** enter a commit from this campaign.
- Every path below was taken from a fresh `git status --porcelain` capture
  (`$env:TEMP\v6_git_state.txt`, `$env:TEMP\v6_modified_files.txt`):
  **54 modified tracked (non-web)**, **53 untracked (non-interlock)**,
  **60 `web/` deletions (excluded, group F)**. (R1 review 2026-10-15:
  corrected from "51" — the final two are `INTERLOCK_V6_FINAL_REPORT.md`
  and this manifest, created after the original capture; scripted
  path-by-path verification against `git status --porcelain` confirms
  groups A–E total 107 paths with zero duplicates, zero missing,
  zero phantom, zero ignored-but-included.)

---

## A. Recovery engine core — domain services, entities, contracts
*16 tracked modifications + 4 new files*

Tracked modifications:
```
app/domain/entities/causal_state_types.py
app/domain/entities/snapshot_types.py
app/domain/entities/surgical_recovery_types.py
app/domain/repositories/causal_state_repositories.py
app/domain/repositories/snapshot_repository.py
app/domain/services/authorization_service.py
app/domain/services/distributed_recovery_orchestrator.py
app/domain/services/emergency_control_service.py
app/domain/services/enterprise_recovery_platform.py
app/domain/services/evidence_verification_service.py
app/domain/services/independent_verification_service.py
app/domain/services/recovery_adapter.py
app/domain/services/recovery_planning_service.py
app/domain/services/risk_engine.py
app/domain/services/self_healing_service.py
app/domain/value_objects/authorization_context.py
```
New files:
```
app/domain/services/evidence_hash.py
app/domain/services/recovery_adapter_registry.py
app/domain/services/recovery_certification_lab.py
app/domain/services/tenant_quota_service.py
```
Rationale: recovery semantics, durable orchestrator (verification-status
correctness fix, lease/fencing integration), emergency-deny service
(process-wide singleton), capability registry, certification lab, evidence
hash recompute, quota policy service.

## B. Infrastructure — persistence, migrations, recovery adapters
*15 tracked modifications + 7 new files + 3 new migrations*

Tracked modifications:
```
app/infrastructure/observability/opentelemetry_integration.py
app/infrastructure/payments/payment_providers.py
app/infrastructure/persistence/database.py
app/infrastructure/persistence/models/__init__.py
app/infrastructure/persistence/models/causal_state_models.py
app/infrastructure/persistence/repositories/sqlalchemy_causal_state_repositories.py
app/infrastructure/persistence/repositories/sqlalchemy_recovery_evidence_repository.py
app/infrastructure/recovery/config_recovery_adapter.py
app/infrastructure/recovery/config_rollback_adapter.py
app/infrastructure/recovery/database_record_adapter.py
app/infrastructure/recovery/database_recovery_adapter.py
app/infrastructure/recovery/file_version_adapter.py
app/infrastructure/recovery/filesystem_recovery_adapter.py
app/infrastructure/recovery/git_repository_adapter.py
app/infrastructure/recovery/mock_adapter.py
```
New files:
```
app/infrastructure/backup_restore.py
app/infrastructure/persistence/models/coordination_models.py
app/infrastructure/persistence/repositories/sqlalchemy_coordination_stores.py
app/infrastructure/recovery/archive_recovery_adapter.py
app/infrastructure/recovery/certification_probes.py
app/infrastructure/recovery/environment_recovery_adapter.py
app/infrastructure/recovery/hosts_recovery_adapter.py
alembic/versions/67080f3cfec6_merge_emergency_states_and_dropped_.py
alembic/versions/a63190d7e268_v6_durable_execution_write_fence.py
alembic/versions/b4b471ffc2bd_v6_shared_lease_and_quota_coordination_.py
```
Rationale: durable-execution write fence, shared SQL lease/quota stores,
evidence repository hardening, adapter containment/verification fixes,
backup/restore utility, environment/hosts/archive adapters + certification
probes, and the three additive V6 migrations (`alembic heads` verified
single-head before inclusion).

## C. API surface, startup/shutdown operations, CI workflow files
*6 tracked modifications + 1 new file + 3 workflow modifications*

Tracked modifications:
```
app/main.py
app/presentation/api/v1/routes/authority.py
app/presentation/api/v1/routes/control.py
app/presentation/api/v1/routes/emergency.py
app/presentation/api/v1/routes/intent.py
app/presentation/api/v1/routes/surgical_recovery.py
.github/workflows/ci.yml
.github/workflows/docker-verify.yml
.github/workflows/security.yml
```
New files:
```
app/presentation/api/dependencies/emergency_guard.py
```
Rationale: emergency-deny enforcement wired at all five execution entry
points (surgical execute/resume, control execute/resume, intent execute),
graceful-shutdown `engine.dispose()` teardown, route fixes from WP-6/WP-7
(evidence-access denial audit, honest `SAFE_AUTOMATIC` gating), and the
local workflow-file edits (workflow *files* only — no external repository
settings or branch protections were touched).

## D. Test suite and demo harness — V5 + V6
*14 tracked modifications + 19 new files*

Tracked modifications:
```
demo_e2e_causal_recovery.py
tests/integration/test_billing_extra_routes.py
tests/stress/test_live_agent_recovery.py
tests/unit/recovery_gauntlet/harness.py
tests/unit/recovery_lab/test_phase07_08_09_crash_infra_concurrency.py
tests/unit/recovery_lab/test_phase16_17_orchestrator_verification_confidence.py
tests/unit/test_advanced_authorization.py
tests/unit/test_config_recovery_adapter.py
tests/unit/test_distributed_recovery.py
tests/unit/test_domain_a_advanced_authorization.py
tests/unit/test_domain_i_verification.py
tests/unit/test_git_repository_adapter.py
tests/unit/test_identity_compromise.py
tests/unit/test_recovery_score_service.py
```
New files:
```
tests/integration/test_execution_boundary_bypass_v6.py
tests/integration/test_scenario_proofs_v6.py
tests/performance/test_coordination_benchmark_v6.py
tests/performance/test_recovery_adapter_benchmark.py
tests/unit/coordination_store_factories.py
tests/unit/test_adversarial_verification.py
tests/unit/test_archive_recovery_adapter.py
tests/unit/test_backup_restore_drill.py
tests/unit/test_durable_execution_fencing.py
tests/unit/test_environment_recovery_adapter.py
tests/unit/test_evidence_integrity_v2.py
tests/unit/test_fault_injection_matrix_v6.py
tests/unit/test_hosts_recovery_adapter.py
tests/unit/test_lifespan_shutdown_v6.py
tests/unit/test_orchestrator_reliability.py
tests/unit/test_recovery_certification_lab.py
tests/unit/test_sql_lease_quota_stores.py
tests/unit/test_tenant_quota_service.py
tests/unit/test_v5_adapter_registry.py
```
Rationale: every V5/V6 work-package deliverable, the scenario proofs
(A–J), the deterministic crash matrix, execution-boundary bypass probes,
shutdown-teardown tests, coordination benchmarks, and the pre-existing
baseline/regression test updates.

## E. Documentation and reports — V5 + V6
*19 new files*

```
INTERLOCK_V5_ADAPTER_CAPABILITY_MATRIX.md
INTERLOCK_V5_BENCHMARK_REPORT.md
INTERLOCK_V5_CONFIRMED_DEFECT_REGISTER.md
INTERLOCK_V5_EXTERNAL_VALIDATION_RUNBOOK.md
INTERLOCK_V5_FAILURE_INJECTION_REPORT.md
INTERLOCK_V5_IMPLEMENTATION_CHANGELOG.md
INTERLOCK_V5_INDEPENDENT_VERIFICATION_REPORT.md
INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md
INTERLOCK_V5_PROPOSED_COMMIT_MANIFEST.md
INTERLOCK_V5_RECOVERY_CORRECTNESS_REPORT.md
INTERLOCK_V5_RECOVERY_ENGINE_ROADMAP.md
INTERLOCK_V5_RELEASE_DECISION.md
INTERLOCK_V5_SECURITY_AND_CONTAINMENT_REPORT.md
INTERLOCK_V5_SECURITY_REVIEW_SUMMARY.md
INTERLOCK_V5_TEST_EVIDENCE_REPORT.md
INTERLOCK_V6_EVIDENCE_V2_SPEC.md
INTERLOCK_V6_PHASE0_BASELINE.md
INTERLOCK_V6_FINAL_REPORT.md            (created with this manifest)
INTERLOCK_V6_COMMIT_MANIFEST.md         (this file)
```
Rationale: all campaign reports; V5 documents are historical evidence,
V6 documents are current-run evidence. Nothing in this group contains
secrets, credentials, `.env` values, or machine-specific runtime config.

## F. Explicit exclusions — never staged, never committed

| Excluded | Why |
|---|---|
| 60 `web/` deletions (` D web/...`) | User-owned uncommitted deletions; restoring/committing `web/` requires explicit approval (ABSOLUTE SAFETY RULES #3). |
| `stash@{0}` (`WIP on master: 145a3d9 ...`) | Must never be modified, popped, or dropped (#4). |
| `interlock_projects/` (untracked) | User workspace content, not part of a release (#4 of master-prompt restrictions). |
| Ignored files: `.env`, `requirements*.txt`, pytest logs (`pytest_*.log/txt`), `.venv/`, caches/`__pycache__`, generated artifacts | Secrets/environment/ignored dependency pins must never be force-added. |
| Credentials, tokens, keys, `.env` values | Never expose or commit (#6/#7 of safety rules). |

---

## Pre-commit verification (rerun at approval time)

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --no-header --no-cov
.\.venv\Scripts\python.exe -m ruff check app sdk
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m bandit -r app                       # project invocation (CI parity: -r app -ll)
.\.venv\Scripts\semgrep.exe --config auto app --quiet             # project semgrep invocation
.\.venv\Scripts\python.exe -m pip_audit                            # known advisory rows: see final report
git diff --check
git diff --cached --stat                                          # must be empty until `git add` is approved
```
Exact recorded results for each command (counts, exit codes, logs) are in
`INTERLOCK_V6_FINAL_REPORT.md` Part 2.

## Post-commit actions (separate decisions, NOT authorized by this manifest)

1. Push to an approved remote/branch (explicit authorization required).
2. Tag + release notes + publication (gated process A–F of the master
   prompt: prepare → verify → propose → **stop for authorization** →
   publish approved artifact → verify published metadata).
3. CI trigger retarget is *file-local only*; changing repository/branch
   settings requires separate approval.
4. `web/` restoration and `requirements*.txt` force-add remain blocked
   pending explicit approval.

**Nothing in groups A–E has been staged. Approval of this manifest is the
prerequisite for the first `git add`.**

---

## Amendment (proposed 2026-10-16, R1–R4 closure run — requires approval with this manifest)

Detailed evidence: `INTERLOCK_V6_RELEASE_GATE_R1_R4.md` §1.3 / §2.3 / §5.

| Change | Files | New group membership | New total |
|--------|-------|----------------------|-----------|
| +2 modified | `pyproject.toml` (R-PKG: `cyclonedx-bom>=7.0,<8.0`, `semgrep==1.181.0`), `.env.example` (R-PKG: JSON-array `CORS_ORIGINS`) | group C | 109 |
| +1 new | `INTERLOCK_V6_RELEASE_GATE_R1_R4.md` (this release's gate report) | group E (docs) | 110 |
| +1 new (conditional) | `alembic/versions/v6driftbf01_v6_v5_model_drift_backfill.py` (M-PKG) — does **not** exist in the repository yet | group B (alembic) | 111 |

If only the manifest base (107) is approved, the amendment rows are not staged.
If M-PKG is not approved, row 3 never applies. Staging still requires its own
explicit authorization after approval — nothing above changes that.
