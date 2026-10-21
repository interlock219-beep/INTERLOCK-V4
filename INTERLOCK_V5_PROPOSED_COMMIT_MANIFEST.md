# Interlock V5 — Proposed Selective Commit Manifest

**No commit has been made.** This manifest is the proposal for the user's review;
execution requires explicit approval. HEAD at time of proposal: `master` @ `145a3d9`.

## How to read this

- **Stage:** files that constitute the V5 implementation + baseline-fix campaign.
- **Never stage:** user-owned state (`web/` deletions, `interlock_projects/`),
  ignored/local files (`.env`, venvs, caches), and `stash@{0}` (leave untouched).
- Suggested commit split keeps review units coherent (three commits); a single
  commit is acceptable if preferred.

---

## A. Staged files (exact list)

### Commit 1 — baseline test fixes + reliability hardening (tracked modifications)

```
app/domain/entities/surgical_recovery_types.py
app/domain/services/authorization_service.py
app/domain/services/distributed_recovery_orchestrator.py
app/domain/services/enterprise_recovery_platform.py
app/domain/services/independent_verification_service.py
app/domain/services/recovery_planning_service.py
app/domain/services/risk_engine.py
app/domain/services/self_healing_service.py
app/domain/value_objects/authorization_context.py
app/infrastructure/observability/opentelemetry_integration.py
app/infrastructure/recovery/config_recovery_adapter.py
app/infrastructure/recovery/filesystem_recovery_adapter.py
app/presentation/api/v1/routes/authority.py
app/presentation/api/v1/routes/surgical_recovery.py
tests/integration/test_billing_extra_routes.py
tests/stress/test_live_agent_recovery.py
tests/unit/test_advanced_authorization.py
tests/unit/test_config_recovery_adapter.py
tests/unit/test_domain_a_advanced_authorization.py
tests/unit/test_domain_i_verification.py
tests/unit/test_identity_compromise.py
```

*Covers:* the 33-baseline-failure fixes (pre-V5 reconciliation), V5-13 CWD-leak
stress fix, config/filesystem hardening (V5-8/V5-9), quota route wiring.

### Commit 2 — V5 recovery framework (tracked modification + new files)

```
app/domain/services/distributed_recovery_orchestrator.py   # if split: V5-14/15/17/18 lease+resume+step fixes live here
app/infrastructure/recovery/git_repository_adapter.py      # V5-16/19/20 containment + honesty
app/domain/services/recovery_adapter_registry.py
app/domain/services/recovery_certification_lab.py
app/domain/services/tenant_quota_service.py             # + QuotaCounterStore protocol & in-process store (G-2 contract)
app/infrastructure/recovery/archive_recovery_adapter.py
app/infrastructure/recovery/certification_probes.py
app/infrastructure/recovery/environment_recovery_adapter.py
app/infrastructure/recovery/hosts_recovery_adapter.py
alembic/versions/67080f3cfec6_merge_emergency_states_and_dropped_.py   # V5-21 single-head repair
tests/unit/test_distributed_recovery.py                    # only if modified by the run
tests/unit/test_git_repository_adapter.py
tests/unit/test_orchestrator_reliability.py
tests/unit/test_v5_adapter_registry.py
tests/unit/test_recovery_certification_lab.py
tests/unit/test_tenant_quota_service.py
tests/unit/test_archive_recovery_adapter.py
tests/unit/test_environment_recovery_adapter.py
tests/unit/test_hosts_recovery_adapter.py
tests/performance/test_recovery_adapter_benchmark.py
```

> Note: `distributed_recovery_orchestrator.py` and `test_git_repository_adapter.py`
> are modified tracked files — include them in whichever commit grouping is chosen
> (they carry both baseline and V5-gate changes; splitting within a file is not
> practical without interactive staging).

### Commit 3 — dependency pins: **NOT POSSIBLE / NOT PART OF THE COMMIT**

`requirements.txt` and `requirements-dev.txt` are **gitignored**
(`.gitignore:70–71`) and have never been tracked at HEAD — verified this run
via `git ls-files` / `git check-ignore`. The pyjwt 2.15.0 / urllib3 2.8.0
bump therefore lives in the **local environment only** (the ignored pin
files + the updated venv), and is verified by the auth suites, not by a
commit. Force-adding them (`git add -f`) would contradict the repo's ignore
policy — only do this if the user explicitly decides to version pins.
The empty slot is kept for review clarity.

### Commit 4 — documentation (new files)

```
INTERLOCK_V5_RECOVERY_ENGINE_ROADMAP.md
INTERLOCK_V5_ADAPTER_CAPABILITY_MATRIX.md
INTERLOCK_V5_RECOVERY_CORRECTNESS_REPORT.md
INTERLOCK_V5_SECURITY_AND_CONTAINMENT_REPORT.md
INTERLOCK_V5_FAILURE_INJECTION_REPORT.md
INTERLOCK_V5_BENCHMARK_REPORT.md
INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md
INTERLOCK_V5_IMPLEMENTATION_CHANGELOG.md
INTERLOCK_V5_INDEPENDENT_VERIFICATION_REPORT.md
INTERLOCK_V5_CONFIRMED_DEFECT_REGISTER.md
INTERLOCK_V5_TEST_EVIDENCE_REPORT.md
INTERLOCK_V5_EXTERNAL_VALIDATION_RUNBOOK.md
INTERLOCK_V5_SECURITY_REVIEW_SUMMARY.md
INTERLOCK_V5_RELEASE_DECISION.md
INTERLOCK_V5_PROPOSED_COMMIT_MANIFEST.md
```

---

## B. Explicit exclusions and why

| Excluded | Why |
|---|---|
| `web/` (60 deleted paths in working tree) | User's uncommitted deletions — preserved per instructions; must not be restored, recreated, or committed without explicit approval (G-7). |
| `interlock_projects/` (untracked) | User's working directory — never part of V5 commits. |
| `.env`, `.venv/`, `.venv314/`, caches, `.kilo/`, `.pytest_tmp_sso.db`, `__pycache__` (97 ignored entries) | Local/ignored state; secrets must never be committed (`.env` never opened). |
| `stash@{0}` | Pre-existing user stash — left untouched. |
| `requirements.txt`, `requirements-dev.txt` (gitignored, never tracked) | Repo policy excludes them (`.gitignore:70–71`); the pyjwt/urllib3 bump inside them is a verified local-environment change (auth suites green) — versioning pins is a separate user decision. |
| Any file not listed in section A | Unrelated user changes or out-of-scope files. |

---

## C. Pre-commit verification (rerun at approval time)

```powershell
git status --porcelain                      # diff against section A lists
git diff --stat                             # review every hunk
git diff --cached --stat                    # confirm ONLY listed files staged
& ".\.venv\Scripts\python.exe" -m pytest tests -q --no-header --no-cov   # expect: see Test Evidence Report
& ".\.venv\Scripts\python.exe" -m ruff check <listed .py files>          # expect: 0 new errors
& ".\.venv\Scripts\python.exe" -m mypy app                                # expect: only pre-existing untouched-file errors
```

Red flags that must stop the commit: any `web/` path staged, any `interlock_projects/`
path staged, `stash@{0}` referenced by any command, unexpected files in
`git diff --cached`, test count below the reported pass count.

## D. Post-commit actions (separate decisions)

1. Retarget `.github/workflows/ci.yml` triggers to `master` and clear pre-existing
   ruff/mypy debt so CI can become a merge gate (G-18).
2. Execute the External Validation Runbook for cloud/KMS/SIEM/Postgres/Kubernetes
   and the two distributed coordination backends (G-1/G-2/G-3).
3. Decide `web/` frontend restoration separately (G-7).
