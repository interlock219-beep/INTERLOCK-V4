# INTERLOCK V6 — Release Gate Report: R1–R4 Closure

Statuses used (exhaustive): `PASS` · `FAIL` · `PENDING APPROVAL` · `BLOCKED EXTERNALLY`.
Every claim below cites recorded commands and exit codes. No claim exceeds its evidence.

**Authorization boundary observed throughout:** no `git add`, commit, push, tag, publish,
deploy, remote-setting change, force-add of ignored files, stash operation, `web/` change,
or dependency-policy change to the repository. All experimental remedies were applied only
inside a temporary candidate tree (`%TEMP%\opencode\v6_r2_candidate`).

---

## 0. Status summary

| ID | Blocker | Status | One-line reason |
|----|---------|--------|-----------------|
| R1 | Approve manifest A–F + create commits | `PENDING APPROVAL` | Path-by-path verification passed (107/107, zero anomalies); staging is explicitly not yet authorized |
| R2 | Reproducible install from fresh clone | `PENDING APPROVAL` | Documented procedure is **broken under current tracked files** (empirically proven); a 3-line remedy is **empirically proven end-to-end on a candidate tree**; closure requires applying the approved remedy and re-verifying |
| R3 | First CI run on `master` green | `BLOCKED EXTERNALLY` | Requires (a) approved commit, (b) separate push authorization, (c) approved workflow fixes; a real CI run cannot occur locally |
| R4 | Remediate fixable advisories | `PENDING APPROVAL` | All fixable advisories identified with exact remediations; smallest compliant remedy validated on candidate only; applying it changes dependency policy (approval required) |

Release recommendation (unchanged): **do not publish**. Publication remains gated on R1–R4
closure plus the push-authorized first CI run.

---

## 1. R1 — Manifest approval and commit plan

**Definition (verbatim from `INTERLOCK_V6_FINAL_REPORT.md` Part 12):** approve the commit
manifest groups A–F and create the commits.
**Acceptance:** manifest approved verbatim → A–E committed, F intact, `git status` clean
except F, gates re-run green on the committed tree.

### 1.1 Verification performed (this run)

Scripted path-by-path reconciliation of `INTERLOCK_V6_COMMIT_MANIFEST.md` against
`git status --porcelain`:

- Group A = 20 (16 modified + 4 new) · B = 25 (15 modified + 7 app-new + 3 alembic-new) ·
  C = 10 (6 modified + 3 workflows-new + 1) · D = 33 (14 modified + 19 new) · E = 19 (docs).
- Total **107 = 54 modified (non-`web/`) + 53 untracked (non-`interlock_projects`)** — exact.
- Zero duplicate paths, zero manifest paths missing from disk, zero on-disk candidates
  missing from the manifest, zero phantom group-header counts.
- Zero ignored-but-included paths (no `requirements*.txt`, no `.env`, no `*.db`, no
  `interlock_projects/`).
- Ownership cross-link: 25 of the 54 modified files are cross-referenced in the V5 manifest;
  the remaining 29 are documented V6 WP files.
- No code references to `interlock_projects/` or `requirements*.txt` in the 107 paths.
- Manifest errata applied (docs-only, not staged): “51 untracked” → 53 with R1-verification
  note; `bandit -r app -c bandit.yaml` → `bandit -r app` (no `bandit.yaml` exists).
- `git diff --cached --name-only` count = **0** (nothing staged) at every checkpoint.
- HEAD = `145a3d9`; stash `stash@{0}` untouched; 60 `web/` deletions and
  `interlock_projects/` present and excluded exactly as required.

### 1.2 Gates on the exact candidate tree (recorded this run)

| Gate | Command | Result | Exit |
|------|---------|--------|------|
| Ruff | `ruff check app sdk` | All checks passed | 0 |
| Mypy | `mypy app` | Success: no issues in 311 source files | 0 |
| Bandit (project) | `bandit -r app` | 0 High / 0 Medium / 7 Low (49,464 LOC, 0 `#nosec`) | 1 (expected) |
| Bandit (CI parity) | `bandit -r app -ll` | no issues | 0 |
| Semgrep (CI parity, `p/security-audit` + `p/owasp-top-ten` + `p/python`) | `semgrep … app --quiet --json` | 6 findings, 0 errors — all in `token_revocation_service.py`, `auth.py`, `billing.py` (files the campaign never touched); **0 findings in any campaign-new file** | 0 |
| Whitespace | `git diff --check` | clean | 0 |
| Full suite (working tree) | `pytest tests -q --no-header --no-cov` | **2860 passed, 7 skipped, 0 failed** in 2277.44 s | 0 |
| Alembic head | `alembic heads` | single head `b4b471ffc2bd` | 0 |

Evidence: `logs/v6_gate_closure/v6_r_gates.txt`, `v6_r_semgrep_ci.json`,
`v6_r_closure_suite.txt` + `_exit.txt`.

### 1.3 Proposed manifest amendment (not yet in the manifest, requires approval together with §3/§4)

| Change | Files | New group membership |
|--------|-------|----------------------|
| +2 modified | `pyproject.toml`, `.env.example` (R2 remedy R-PKG, §2.3) | add to group C → manifest total becomes **109 paths** |
| +1 new | `INTERLOCK_V6_RELEASE_GATE_R1_R4.md` (this report; currently untracked) | add to group E (docs) → manifest total becomes **110 paths** |

(If M-PKG §5 is approved, its new file `alembic/versions/v6driftbf01_…py` becomes a
further +1 → 111 paths; it does not exist in the repository yet.)

### 1.4 R1 remaining action

Approve manifest A–F **verbatim** (with the §1.3 amendment if the §3.2/§4.2 remedies are
approved). Only then may staging begin (separate step, executed under its own authorization).
**Status: `PENDING APPROVAL`.**

---

## 2. R2 — Reproducible install from a fresh clone

**Definition:** documented install command verified in a clean venv from a fresh clone
succeeds **and the full suite passes there**.

### 2.1 What “fresh clone” means here (established, verified)

The candidate tree was built byte-exact from tracked HEAD + manifest overlay:
`git archive --format=zip HEAD` (677 tracked files, `web/` intact as committed, no `.env`,
no `requirements*.txt`, no `interlock_projects/`, no `*.db`) + exactly the 53 manifest new
files = **730 files**; `app/main.py` hash matches the working tree.
Location: `%TEMP%\opencode\v6_r2_candidate` (moved under the pre-approved `%TEMP%\opencode\`
area after system temp cleanup deleted the first candidate — see Disclosures §8).

### 2.2 Result under CURRENT tracked files: the documented procedure is broken — `FAIL` (empirical)

| # | Path | Command | Result | Exit |
|---|------|---------|--------|------|
| 1 | README step 3 (tracked `pyproject.toml` extras) | `python -m venv .venv-fresh` then `.venv-fresh\Scripts\python -m pip install -e ".[dev,security]"` | **`ResolutionImpossible`**: `cyclonedx-bom 3.2.0` requires `cyclonedx-python-lib>=2,<3` while `pip-audit 2.10.x` requires `>=5,<12` | 1 |
| 2 | CI path | `pip install -r requirements-dev.txt` | file is gitignored → **absent from any clone**; and even locally the lock is internally unresolvable (`semgrep 1.173.0` needs `pyjwt[crypto]~=2.13.0` vs pinned `pyjwt==2.15.0` → `ResolutionImpossible`) | 1 / absent |
| 3 | README step 4→5 after a successful install attempt | `cp .env.example .env` then `alembic upgrade head` | **`SettingsError: error parsing value for field "cors_origins"`** — the tracked `.env.example` value `CORS_ORIGINS=http://localhost:3000` is rejected by pydantic-settings (both 2.15.0 and 2.16.0, dotenv **and** env-var sources) | 1 |

Further empirical facts recorded along the way:

- Loose `semgrep>=1.100,<2.0` backtracks the resolver (1.181→1.111) into a semgrep **sdist
  build that refuses Windows** → install aborts; cause chain: semgrep ≤1.173 requires
  `pyjwt~=2.13.0`, and pip’s order-dependent backtracking commits `pyjwt 2.15.1` first.
- A fresh resolution pins `pyjwt 2.13.0` under `semgrep==1.173.0` → **14 fixable advisories**
  in the app’s JWT library (R4 violation — caught before any proposal was finalized).
- Fresh venv bootstrap ships `pip 24.0` (12 fixable advisories) and `setuptools 65.5.0`
  (8 fixable); both CI workflows already run upgrade steps that eliminate these
  (`ci.yml` L52 upgrades pip; `security.yml` L25 upgrades pip+setuptools).

### 2.3 Remedy package R-PKG (exact diffs, prepared — NOT applied to the repository)

**File 1 — `pyproject.toml` (2 lines):**

```diff
 [project.optional-dependencies]
 dev = [
@@
 security = [
     "pip-audit>=2.7,<3.0",
-    "cyclonedx-bom>=3.2,<4.0",
-    "semgrep>=1.100,<2.0",
+    "cyclonedx-bom>=7.0,<8.0",
+    "semgrep==1.181.0",
 ]
```

- `cyclonedx-bom>=7.0,<8.0` → resolves `cyclonedx-python-lib>=8,<12`, compatible with
  pip-audit 2.10.x (`>=5,<12`); verified latest `7.5.0` metadata.
- `semgrep==1.181.0` → newest release, ships Windows wheels, requires
  `pyjwt[crypto]>=2.15.0` (forces advisory-free PyJWT ≥2.15.1), and the exact pin makes the
  resolution deterministic on every platform (loose ranges reproduced the backtrack wall).

**File 2 — `.env.example` (1 line):**

```diff
-CORS_ORIGINS=http://localhost:3000
+CORS_ORIGINS=["http://localhost:3000"]
```

pydantic-settings JSON-decodes complex-typed fields from dotenv/env sources before field
validators run; only the JSON array form parses. Verified working under both 2.15.0 and
2.16.0 (`SETTINGS_OK ['http://localhost:3000']`).

No README change is required (procedure steps remain identical).

### 2.4 End-to-end verification of R-PKG on the candidate tree (recorded this run)

| Step | Command (in candidate, fresh venv) | Result | Exit / time |
|------|------------------------------------|--------|-------------|
| Resolution (exact README invocation) | `pip install --dry-run -e ".[dev,security]"` with R-PKG | `Would install PyJWT-2.15.1 … semgrep-1.181.0` | 0 |
| Real install | `.venv-fresh\Scripts\python -m pip install -e ".[dev,security]"` | Success | 0 / 304 s |
| Consistency | `python -m pip check` | No broken requirements found | 0 |
| Key versions (final env) | metadata query after R-PKG sync + `pip install --upgrade pip setuptools` | `pyjwt==2.15.1`, `semgrep==1.181.0`, `pip==26.2.1`, `setuptools==84.0.0`, `pydantic-settings==2.16.0`, `fastapi==0.141.1`, `starlette==1.8.0`, `virtualenv==21.14.7`, `pip-audit==2.10.1`, `cyclonedx-bom==7.5.0`, `pytest==9.1.1`, `ruff==0.17.1`, `mypy==1.20.2`, `bandit==1.9.4`, `alembic==1.20.0`, `sqlalchemy==2.1.4`, `pre-commit==4.7.0`, `cryptography==50.0.2`; `pip check` clean | 0 |
| README step 4 | `cp .env.example .env` (remedied example) | success | 0 |
| README step 5 | `alembic upgrade head` | applied to head, fresh SQLite, 8 s | 0 |
| — | `alembic current` | `b4b471ffc2bd (head)` | 0 |
| README step 6 | uvicorn on 127.0.0.1:8123 | startup complete, no warnings | 0 |
| Health | `GET /api/v1/health` | `200 {"status":"ok"}` | 0 |
| Readiness | `GET /api/v1/ready` | `200 {"status":"ready","db":"ok","redis":"disabled"}` | 0 |
| Full suite (candidate, run 1) | `pytest tests -q --no-header` (project addopts incl. coverage; env = remedy-v3 state) | **2860 passed, 7 skipped, 0 failed**, 3120.90 s (52:00), 24 warnings | 0 |
| Full suite (candidate, final env = R-PKG + final sync) | `pytest tests -q --no-header` | **2860 passed, 7 skipped, 0 failed**, 3039.81 s (50:39), 24 warnings | 0 |
| Post-suite candidate re-scan (generated files, overlay hashes, `web/` intact, exclusions) | scripted | **clean**: 54/54 modified files byte-identical to working tree; 53/53 manifest-untracked overlay files byte-identical (the only expected absent file is this report itself — a repo-level artifact created after the candidate build); `web/` = 60/60 = HEAD (intact); 0 `requirements*.txt`, 0 `interlock_projects/` files; generated artifacts isolated (`.coverage`, `coverage.xml`, `.env` (procedure copy), `intentlock.db`, `probe_check.db`, `logs/stress_scorecard.json`, `intentlock.egg-info/` ×5, `keys/` ×2 (app-startup key material), proposal migration ×1); `pyproject.toml` and `.env.example` diverge from both HEAD and worktree **only** by the declared R-PKG temp edits | — |

### 2.5 R2 remaining action

Apply approved R-PKG to the repository (2 files), re-run the fresh-clone procedure on the
committed tree, then R2 closes. **Status: `PENDING APPROVAL`**
(current tracked state = empirically `FAIL`; remedy proven on candidate).

---

## 3. R3 — First CI run on `master` green

**Definition:** the first CI run on `master` passes all gates.
**Acceptance** requires an approved commit, a separate push authorization, and honest,
non-weakened workflows.

### 3.1 Workflow defects identified (all pre-existing; none campaign-introduced)

All three workflow files parse as YAML (pyyaml, exit 0). Six defects:

| # | File | Defect | Evidence |
|---|------|--------|----------|
| D1 | `ci.yml` L50–54 | `pip install -r requirements-dev.txt` — file gitignored, absent in every clone; lock also unresolvable (semgrep/pyjwt) | §2.2 row 2; `.gitignore` L70–71 |
| D2 | `ci.yml` L97–102 | `alembic check` runs **without** `alembic upgrade head` → fails on any empty DB | local repro: `alembic check` on empty DB, exit 1 |
| D3 | model↔migration drift | even after `upgrade head`, `alembic check` fails (**33 operations**, V4-era) → D2’s fix alone is not enough | `logs/v6_gate_closure/v6_r_alembic_drift.txt` |
| D4 | `security.yml` L23–28 | same `requirements-dev.txt` install defect as D1 (plus redundant unpinned `pip install cyclonedx-bom`) | §2.2 row 2 |
| D5 | `security.yml` L46–47 | SBOM step runs `python -m cyclonedx-py` → **`No module named cyclonedx-py`** (verified against installed cyclonedx-bom 7.5.0; the console script `cyclonedx-py` works) | recorded this run, exit 1 / 0 |
| D6 | `docker-verify.yml` L20–40 | compose service `env_file: - .env` (`docker-compose.yml` L8–9) but `.env` is gitignored → absent from checkout → `docker compose build/up` fails | `.gitignore` L41; compose file inspection |

**Step-ordering constraint discovered during migration validation (factored into W2):** in
`ci.yml` the migration step (L97–102) currently runs **after** the test step (L78–87).
The test step’s autouse fixture runs `drop_all` + `init_db()` (= `create_all`) per test
against the same Postgres database, so by the time `alembic` would run, the database has
been created by SQLAlchemy, not by migrations (leftover native PG enum types from
`create_all` would also collide with migration-time `CREATE TYPE`). The migration step must
therefore run **before** the tests, on the virgin service database — the exact fresh-DB path
validated locally (§5.4). This ordering fact cannot be exercised locally without live
Postgres (gate G-1); it is stated here so the CI run’s outcome is explainable.

Non-defects examined: `setup-python` `cache: "pip"` is **safe** (setup-python README: pip
cache accepts `requirements.txt` **or** `pyproject.toml`, which is tracked).
Bare `pip-audit` in `security.yml` needs **no change and no `--ignore-vuln` flags**: with
D4 fixed and R-PKG applied, the CI environment contains no vulnerable packages (verified:
post-remedy fresh audit = 0 vulnerabilities, exit 0); the G-14 no-fix packages
(`ecdsa`, `python-jose`) live only in the gitignored runtime lock and never enter the CI
environment. Nothing is suppressed, no exit code is ignored, `alembic check` stays strict.

### 3.2 Exact workflow diffs (prepared — NOT applied)

**W1 — `ci.yml` install step:**

```diff
       - name: Install dependencies
         run: |
           python -m pip install --upgrade pip
-          pip install -r requirements-dev.txt
-          pip install -e .
+          pip install -e ".[dev,security]"
```

**W2 — `ci.yml` migration step: add `upgrade head` AND move the step before the tests
(keeps `alembic check` strict; green only after M-PKG §5):**

```diff
+      - name: Check database migrations
+        env:
+          DATABASE_URL: postgresql+psycopg2://intentlock:intentlock_test_secret@localhost:5432/intentlock_test
+        run: |
+          alembic upgrade head
+          alembic check
+          alembic current
+
       - name: Run tests with coverage
         env:
           DATABASE_URL: postgresql+psycopg2://intentlock:intentlock_test_secret@localhost:5432/intentlock_test
           REDIS_URL: redis://:intentlock_redis_test_secret@localhost:6379/0
           REDIS_ENABLED: "true"
           JWT_SECRET_KEY: test-secret-key-that-is-at-least-32-characters-long
           APP_ENV: test
           DEBUG: "true"
         run: |
           pytest --cov=app --cov=sdk --cov-report=xml --cov-report=term-missing
 
       - name: Upload coverage reports
         uses: codecov/codecov-action@v4
         with:
           files: ./coverage.xml
           flags: unittests
           name: codecov-umbrella
           fail_ci_if_error: false
-
-      - name: Check database migrations
-        env:
-          DATABASE_URL: postgresql+psycopg2://intentlock:intentlock_test_secret@localhost:5432/intentlock_test
-        run: |
-          alembic check
-          alembic current
```

(Migration checks must run on the virgin service database; running them after the test
step would compare migrations against a `create_all`-built schema — see the step-ordering
constraint in §3.1.)

**W3 — `security.yml` install step:**

```diff
       - name: Install dependencies
         run: |
           python -m pip install --upgrade pip setuptools
-          pip install -r requirements-dev.txt
-          pip install -e .
-          pip install cyclonedx-bom
+          pip install -e ".[dev,security]"
```

**W4 — `security.yml` SBOM step (module command → verified console script):**

```diff
       - name: Generate SBOM (CycloneDX)
         run: |
-          pip install cyclonedx-bom
-          python -m cyclonedx-py . --output sbom.json --format json
+          cyclonedx-py . --output sbom.json --format json
```

(cyclonedx-bom now arrives bounded via the `security` extra; `--help`/`--version` of the
7.5.0 console script verified exit 0. The `Run pip-audit`, `bandit -r app -ll`, semgrep,
`dependency-review-action`, and Trivy steps are unchanged.)

**W5 — `docker-verify.yml` (create the compose-required `.env` from the tracked example):**

```diff
+      - name: Create .env from tracked example (compose env_file requirement)
+        run: cp .env.example .env
+
       - name: Build Docker image
         run: docker compose build
```

Validation status: W1/W3 install command and W4 command validated empirically (locally, on
Linux-independent grounds: install exit 0; `cyclonedx-py --version` exit 0). W2 validated
on SQLite locally (`upgrade head` exit 0); its Postgres run happens in CI itself.
W5 is derived from documented compose behavior — **not** executed (Docker/external infra
unauthorized → `BLOCKED EXTERNALLY`, not simulated).

### 3.3 R3 remaining action

1. Approve R-PKG (§2.3) → apply → include manifest amendment (§1.3).
2. Approve W1–W5 (§3.2) and M-PKG (§4).
3. Approve manifest A–F → stage → commit (its own authorization).
4. Separately authorize push → observe first CI run on `master`.

**Status: `BLOCKED EXTERNALLY`.**

---

## 4. R4 — Remediate fixable advisories

**Definition:** pip-audit shows only no-fix advisories, each cross-referenced to G-14.

### 4.1 Audit matrix (all runs recorded, all pip-audit exits 1 as shown)

| Scope | Command | Findings | Disposition |
|-------|---------|----------|-------------|
| Current working venv (bare) | `pip-audit` | 12 advisories / 4 pkgs: `virtualenv 21.7.4` ×8 (fix ≤21.7.13 … latest 21.14.7), `ecdsa` ×2, `python-jose` ×2, `nltk` (local venv cruft from `safety`, in no manifest) | virtualenv → dev-lock remediation (approval); ecdsa/python-jose → **G-14 no-fix**; nltk → out of scope (no manifest) |
| Runtime lock (gitignored, read-only) | `pip-audit -r requirements.txt --no-deps` | 3 rows / 2 pkgs: `ecdsa PYSEC-2026-1325`, `python-jose PYSEC-2026-4298` | **only no-fix advisories** → G-14 cross-reference satisfied for the runtime release scope |
| Dev lock (gitignored, read-only) | `pip-audit -r requirements-dev.txt` | fails before audit: `ResolutionImpossible` (semgrep/pyjwt) | lock is unusable as an audit input; remediation = policy decision §4.3 |
| Fresh documented env (pre-remedy) | `pip-audit` in `.venv-fresh` | 34 advisories / 3 pkgs: `pip 24.0` ×12, `pyjwt 2.13.0` ×14 (fix 2.14/2.15), `setuptools 65.5.0` ×8 | all fixable → drove remedy R-PKG (§2.3): PyJWT → 2.15.1; pip/setuptools eliminated by both workflows’ existing upgrade steps |
| Fresh documented env (post-remedy, final) | `pip-audit` after R-PKG + `pip install --upgrade pip setuptools` (env: `pyjwt 2.15.1`, `pip 26.2.1`, `setuptools 84.0.0`) | **0 vulnerabilities** (`TOTAL_VULNS=0`, “No known vulnerabilities found”), 0 skipped | 0 |

`virtualenv` evidence: `pip index versions virtualenv` → installed 21.7.4 (lock line 522 of
the gitignored `requirements-dev.txt`), latest 21.14.7; pin only exists in the ignored lock.

### 4.2 Remediation package (smallest policy-compliant path — prepared, NOT applied)

1. **R-PKG (§2.3)** — resolves every fixable advisory reachable from the documented path:
   PyJWT → 2.15.1 (14 advisories fixed), cyclonedx/semgrep conflict removed, semgrep pinned
   to a Windows-wheeled release.
2. **CI upgrades (already present)** eliminate `pip`/`setuptools` bootstrap findings in CI.
3. **G-14 accepted-risk items** (`ecdsa PYSEC-2026-1325`, `python-jose PYSEC-2026-4298`) —
   no fix upstream; remain documented in the final report’s accepted-risk register G-14.
   They are *not* used to silence any gate: CI never installs them, and the local runtime-scope
   audit records them explicitly.
4. **Dev-lock policy (decision required, §6 item 5):** `requirements-dev.txt` cannot serve
   as an install source (unresolvable, gitignored). Proposed: retire it as an install/audit
   source in favor of the tracked extras path (it may remain on disk, untracked; regeneration
   or deletion is a separate, later decision under dependency-policy approval).

### 4.3 R4 remaining action

Approve R-PKG (+ optional dev-lock retirement decision). Acceptance evidence is prepared in
the candidate; final confirmation on the committed tree after approval.
**Status: `PENDING APPROVAL`.**

---

## 5. Migration-drift fix — proposal M-PKG (shown here BEFORE any file was created)

**Rule honored:** this precise proposal and its risks are presented in this document
**first**; only afterwards was the migration file created — in the temporary candidate
tree alone, for validation. No migration file exists in the repository, and none will
without approval. Nothing in the repository’s migration history is rewritten; `alembic
check` is not disabled or weakened.

### 5.1 Facts

- Drift = **33 autogenerate operations**, **entirely V4-era** (no V6 model in the list);
  V6’s three migrations cover all V6 additions. Evidence:
  `logs/v6_gate_closure/v6_r_alembic_drift.txt` (captured after `upgrade head`, exit 1).
  (The op list appears twice in that file — once in the `ERROR` line, once in the `FAILED`
  line; an earlier draft of this report double-counted it as 38. Unique ops: 2 add_table +
  11 add_column + 15 add_index + 4 remove_index + 1 modify_nullable = 33.)
- Tests cannot see it: the suite builds its schema via `Base.metadata.create_all` on
  `sqlite:///:memory:` (`tests/conftest.py`), bypassing migrations.
- **Structural finding — the eight “causal” tables**: migration `0010_causal_state_recovery`
  creates `state_checkpoints`, `causal_state_graphs`, `ai_changesets`, `resource_versions`,
  `state_deltas`, `recovery_confidences`, `durable_execution_steps`, `recovery_reports`,
  and a later migration drops them again (the “dropped-tables head” merged in
  `67080f3cfec6`). Alembic’s compare metadata (`alembic/env.py` imports only
  `models.user_model`, whose package `__init__.py` does **not** import
  `causal_state_models`) contains 30 tables and none of the eight; a pure
  `alembic upgrade head` database therefore ends with 30 app tables (+ `alembic_version`)
  and `alembic check` is green against it. The application process, however, does import
  the causal models (`sqlalchemy_causal_state_repositories.py`), so app-startup
  `init_db()`/`create_all` re-creates the eight tables in any database the app has
  touched — such mixed-provenance databases make `alembic check` report removal ops.
  This is pre-existing (neither the imports nor those migrations are campaign files); it
  is why the CI migration step must run on the virgin service database (W2 ordering, §3.1)
  and it is disclosed here rather than “fixed”, since changing `env.py` imports or those
  migrations is out of scope for this gate.
- Full operation inventory:
  - **add_table** (2): `identity_providers` (+`ix_identity_providers_tenant_id`),
    `sso_states` (+`ix_sso_states_state_token` unique, `ix_sso_states_tenant_id`)
  - **add_column** (11): `checkout_sessions.tenant_id/.customer_id`;
    `containment_events.affected_session_ids/.affected_token_ids/.affected_action_ids`;
    `execution_tokens.token_id`(→NN)/`.tenant_id`(→NN)/`.status`(→NN)/`.revoked_at`;
    `protected_actions.before_state_snapshot`;
    `recovery_executions.created_at`(→NN)
  - **modify_nullable** (1): `execution_tokens.expires_at` — the model declares
    `nullable=True` while the migrated database has it NOT NULL, so the op **relaxes**
    the column to nullable (a previous draft of this report had the direction backwards
    and proposed a wrong backfill; the migration below implements the correct direction)
  - **add_index** (15): `ix_identity_providers_tenant_id`, `ix_sso_states_state_token`
    (unique), `ix_sso_states_tenant_id`, `ix_agent_sessions_intent_id`,
    `ix_checkout_sessions_tenant_id`, `ix_containment_events_target_authority_id`,
    `ix_execution_tokens_status/_tenant_id/_token_id`(unique),
    `ix_invoices_subscription_id`, `ix_protected_actions_actor_user_id`,
    `ix_subscriptions_plan_id`, `ix_usage_records_period_end/_period_start`,
    `ix_webhook_events_event_type`
  - **remove_index** (4 stale): `ix_plans_tier`, `ix_recovery_evidence_idempotency_key`,
    `ix_usage_records_period`, `ix_user_mfa_user_id`

### 5.2 Proposed migration — exact validated source

File: `alembic/versions/v6driftbf01_v6_v5_model_drift_backfill.py`,
`down_revision=b4b471ffc2bd` → single head preserved. Design: **inspect-if-absent guards
on every operation** (fresh `alembic.Inspector` per check, so re-runs are no-ops);
model-accurate DDL for the two missing tables; add-nullable → fail-closed backfill →
batch-tighten for the new NOT NULL columns; `batch_alter_table` for SQLite compatibility;
the `expires_at` column is **relaxed** to nullable to match the model; the four stale
indexes are dropped only if present. The following is the complete file, validated as
described in §5.4:

```python
"""Guarded backfill of pre-V6 model<->migration drift.

Every operation is guarded by fresh inspection so re-runs are no-ops. Newly added
NOT NULL columns are backfilled before tightening (fail-closed: existing rows receive
token_id = row id, tenant_id 'unknown', status 'active', created_at = CURRENT_TIMESTAMP).
execution_tokens.expires_at is RELAXED to nullable to match the model. Uses
batch_alter_table for SQLite compatibility. Creates a single new head.

Revision ID: v6driftbf01
Revises: b4b471ffc2bd
Create Date: proposal (created in candidate tree for validation only)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v6driftbf01"
down_revision = "b4b471ffc2bd"
branch_labels = None
depends_on = None


def _insp() -> sa.Inspector:
    # Fresh inspector per call: avoids stale reflection caches between guarded steps.
    return sa.inspect(op.get_bind())


def _has_col(table: str, name: str) -> bool:
    return name in {c["name"] for c in _insp().get_columns(table)}


def _has_idx(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def upgrade() -> None:
    # ---------------------------------------------------------------- tables --
    if not _insp().has_table("identity_providers"):
        op.create_table(
            "identity_providers",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            sa.Column(
                "provider_type",
                sa.Enum("oidc", "saml", name="provider_type"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(length=255), nullable=True),
            sa.Column("issuer", sa.String(length=255), nullable=False),
            sa.Column("authorization_url", sa.String(length=1024), nullable=False),
            sa.Column("token_url", sa.String(length=1024), nullable=False),
            sa.Column("jwks_uri", sa.String(length=1024), nullable=False),
            sa.Column("client_id", sa.String(length=255), nullable=False),
            sa.Column("client_secret", sa.String(length=255), nullable=False),
            sa.Column("scopes", sa.String(length=512), nullable=False),
            sa.Column("attribute_mapping", sa.Text(), nullable=False),
            sa.Column("saml_sso_url", sa.String(length=1024), nullable=False),
            sa.Column("saml_entity_id", sa.String(length=255), nullable=False),
            sa.Column("saml_x509_cert", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.Enum("active", "inactive", "error", name="provider_status"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _insp().has_table("sso_states"):
        op.create_table(
            "sso_states",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(
                "state_token", sa.String(length=128), nullable=False, unique=True
            ),
            sa.Column("nonce", sa.String(length=128), nullable=False),
            sa.Column(
                "provider_type",
                sa.Enum("oidc", "saml", name="sso_provider_type"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(length=255), nullable=True),
            sa.Column("redirect_uri", sa.String(length=1024), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "pending", "authorized", "failed", "expired",
                    name="sso_state_status",
                ),
                nullable=False,
            ),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        )

    # -------------------------------------------------------------- columns --
    def add_col(table: str, column: sa.Column) -> None:
        if not _has_col(table, column.name):
            op.add_column(table, column)

    add_col("checkout_sessions", sa.Column("tenant_id", sa.String(length=64), nullable=True))
    add_col("checkout_sessions", sa.Column("customer_id", sa.String(length=128), nullable=True))
    add_col("containment_events", sa.Column("affected_session_ids", sa.Text(), nullable=True))
    add_col("containment_events", sa.Column("affected_token_ids", sa.Text(), nullable=True))
    add_col("containment_events", sa.Column("affected_action_ids", sa.Text(), nullable=True))
    add_col("execution_tokens", sa.Column("token_id", sa.String(length=64), nullable=True))
    add_col("execution_tokens", sa.Column("tenant_id", sa.String(length=64), nullable=True))
    add_col("execution_tokens", sa.Column("status", sa.String(length=32), nullable=True))
    add_col("execution_tokens", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    add_col("protected_actions", sa.Column("before_state_snapshot", sa.Text(), nullable=True))
    add_col("recovery_executions", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))

    # --------------------------------------------------- fail-closed backfills
    # (before tightening NOT NULL; no-ops on empty tables)
    op.execute(
        sa.text(
            "UPDATE execution_tokens SET token_id = CAST(id AS VARCHAR) "
            "WHERE token_id IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE execution_tokens SET tenant_id = 'unknown' WHERE tenant_id IS NULL"
        )
    )
    op.execute(
        sa.text("UPDATE execution_tokens SET status = 'active' WHERE status IS NULL")
    )
    op.execute(
        sa.text(
            "UPDATE recovery_executions SET created_at = CURRENT_TIMESTAMP "
            "WHERE created_at IS NULL"
        )
    )

    # --------------------------------------------- tighten / relax (batched) --
    # execution_tokens: 4 adds -> NOT NULL per model; expires_at relaxes to
    # nullable per model (DB was created NOT NULL by a pre-model change).
    with op.batch_alter_table("execution_tokens") as b:
        b.alter_column("token_id", existing_type=sa.String(length=64), nullable=False)
        b.alter_column("tenant_id", existing_type=sa.String(length=64), nullable=False)
        b.alter_column("status", existing_type=sa.String(length=32), nullable=False)
        b.alter_column("expires_at", existing_type=sa.DateTime(), nullable=True)

    with op.batch_alter_table("recovery_executions") as b:
        b.alter_column(
            "created_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )

    # --------------------------------------------------------------- indexes --
    if not _has_idx("identity_providers", "ix_identity_providers_tenant_id"):
        op.create_index(
            "ix_identity_providers_tenant_id", "identity_providers", ["tenant_id"]
        )
    if not _has_idx("sso_states", "ix_sso_states_state_token"):
        op.create_index(
            "ix_sso_states_state_token", "sso_states", ["state_token"], unique=True
        )
    if not _has_idx("sso_states", "ix_sso_states_tenant_id"):
        op.create_index("ix_sso_states_tenant_id", "sso_states", ["tenant_id"])
    if not _has_idx("agent_sessions", "ix_agent_sessions_intent_id"):
        op.create_index("ix_agent_sessions_intent_id", "agent_sessions", ["intent_id"])
    if not _has_idx("checkout_sessions", "ix_checkout_sessions_tenant_id"):
        op.create_index(
            "ix_checkout_sessions_tenant_id", "checkout_sessions", ["tenant_id"]
        )
    if not _has_idx("containment_events", "ix_containment_events_target_authority_id"):
        op.create_index(
            "ix_containment_events_target_authority_id",
            "containment_events",
            ["target_authority_id"],
        )
    if not _has_idx("execution_tokens", "ix_execution_tokens_status"):
        op.create_index("ix_execution_tokens_status", "execution_tokens", ["status"])
    if not _has_idx("execution_tokens", "ix_execution_tokens_tenant_id"):
        op.create_index(
            "ix_execution_tokens_tenant_id", "execution_tokens", ["tenant_id"]
        )
    if not _has_idx("execution_tokens", "ix_execution_tokens_token_id"):
        op.create_index(
            "ix_execution_tokens_token_id",
            "execution_tokens",
            ["token_id"],
            unique=True,
        )
    if not _has_idx("invoices", "ix_invoices_subscription_id"):
        op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])
    if not _has_idx("protected_actions", "ix_protected_actions_actor_user_id"):
        op.create_index(
            "ix_protected_actions_actor_user_id",
            "protected_actions",
            ["actor_user_id"],
        )
    if not _has_idx("subscriptions", "ix_subscriptions_plan_id"):
        op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    if not _has_idx("usage_records", "ix_usage_records_period_end"):
        op.create_index("ix_usage_records_period_end", "usage_records", ["period_end"])
    if not _has_idx("usage_records", "ix_usage_records_period_start"):
        op.create_index(
            "ix_usage_records_period_start", "usage_records", ["period_start"]
        )
    if not _has_idx("webhook_events", "ix_webhook_events_event_type"):
        op.create_index(
            "ix_webhook_events_event_type", "webhook_events", ["event_type"]
        )

    # ------------------------------------------------------ stale index drops --
    for table, name in [
        ("plans", "ix_plans_tier"),
        ("recovery_evidence", "ix_recovery_evidence_idempotency_key"),
        ("usage_records", "ix_usage_records_period"),
        ("user_mfa", "ix_user_mfa_user_id"),
    ]:
        if _has_idx(table, name):
            op.drop_index(name, table_name=table)


def downgrade() -> None:
    # Reverse order. Dropping columns discards data written to them (standard risk).
    # SQLite batch rebuild re-creates reflected indexes; indexes that reference a
    # column about to be dropped MUST be dropped first or the rebuild fails.
    for table, name in [
        ("execution_tokens", "ix_execution_tokens_status"),
        ("execution_tokens", "ix_execution_tokens_tenant_id"),
        ("execution_tokens", "ix_execution_tokens_token_id"),
        ("checkout_sessions", "ix_checkout_sessions_tenant_id"),
    ]:
        if _has_idx(table, name):
            op.drop_index(name, table_name=table)

    with op.batch_alter_table("recovery_executions") as b:
        b.drop_column("created_at")

    with op.batch_alter_table("execution_tokens") as b:
        b.drop_column("token_id")
        b.drop_column("tenant_id")
        b.drop_column("status")
        b.drop_column("revoked_at")
        b.alter_column("expires_at", existing_type=sa.DateTime(), nullable=False)

    for table, name, cols, unique in [
        ("identity_providers", "ix_identity_providers_tenant_id", ["tenant_id"], False),
        ("sso_states", "ix_sso_states_state_token", ["state_token"], True),
        ("sso_states", "ix_sso_states_tenant_id", ["tenant_id"], False),
        ("agent_sessions", "ix_agent_sessions_intent_id", ["intent_id"], False),
        ("checkout_sessions", "ix_checkout_sessions_tenant_id", ["tenant_id"], False),
        (
            "containment_events",
            "ix_containment_events_target_authority_id",
            ["target_authority_id"],
            False,
        ),
        ("execution_tokens", "ix_execution_tokens_status", ["status"], False),
        ("execution_tokens", "ix_execution_tokens_tenant_id", ["tenant_id"], False),
        ("execution_tokens", "ix_execution_tokens_token_id", ["token_id"], True),
        ("invoices", "ix_invoices_subscription_id", ["subscription_id"], False),
        (
            "protected_actions",
            "ix_protected_actions_actor_user_id",
            ["actor_user_id"],
            False,
        ),
        ("subscriptions", "ix_subscriptions_plan_id", ["plan_id"], False),
        ("usage_records", "ix_usage_records_period_end", ["period_end"], False),
        ("usage_records", "ix_usage_records_period_start", ["period_start"], False),
        ("webhook_events", "ix_webhook_events_event_type", ["event_type"], False),
    ]:
        if _has_idx(table, name):
            op.drop_index(name, table_name=table)

    for table in ("identity_providers", "sso_states"):
        if _insp().has_table(table):
            op.drop_table(table)

    with op.batch_alter_table("protected_actions") as b:
        b.drop_column("before_state_snapshot")
    with op.batch_alter_table("containment_events") as b:
        b.drop_column("affected_session_ids")
        b.drop_column("affected_token_ids")
        b.drop_column("affected_action_ids")
    with op.batch_alter_table("checkout_sessions") as b:
        b.drop_column("tenant_id")
        b.drop_column("customer_id")

    # Re-create the four stale indexes (only meaningful on databases that had them).
    for table, name, cols in [
        ("plans", "ix_plans_tier", ["tier"]),
        (
            "recovery_evidence",
            "ix_recovery_evidence_idempotency_key",
            ["idempotency_key"],
        ),
        ("usage_records", "ix_usage_records_period", ["period_start", "period_end"]),
        ("user_mfa", "ix_user_mfa_user_id", ["user_id"]),
    ]:
        if not _has_idx(table, name):
            op.create_index(name, table, cols)
```


### 5.3 Risks (explicit)

| Risk | Impact | Mitigation in design |
|------|--------|----------------------|
| `execution_tokens.expires_at`: migrated DB is NOT NULL, model is nullable | wrong-direction constraint work would both fail `alembic check` and churn data | migration **relaxes** to nullable (no data change); direction verified from the model source (`nullable=True`) and the autogenerate op tuple `(…, False, True)` |
| `recovery_executions.created_at` NN without model default; existing rows | `ADD … NOT NULL` fails on non-empty table | add nullable → fail-closed backfill (`CURRENT_TIMESTAMP`) → batch-tighten; no-op on empty tables |
| Existing rows with NULL in the four new `execution_tokens` NN columns | `SET NOT NULL` fails | fail-closed backfills before tightening: `token_id = CAST(id AS VARCHAR)` (unique by construction, unusable by any client = token stays dead), `tenant_id = 'unknown'`, `status = 'active'` |
| SQLite cannot `ALTER COLUMN`/drop constraints | local dev breakage | `batch_alter_table` (table rebuild); downgrade drops the four drift-created indexes **before** the batch drops (a first round-trip attempt failed on exactly this; fixed and re-validated, §5.4) |
| PG enum types (`provider_type`, `provider_status`, `sso_provider_type`, `sso_state_status`) | `create_table` fails if a type pre-exists on PG | on any database where the tables are absent the types were never created (migration history creates them together); with W2 ordering the migration runs on the virgin service DB. **Not PG-proven** — first CI run is the PG proof (G-1) |
| Dropping `ix_recovery_evidence_idempotency_key` | possible lookup perf change | index is stale per the model (autogenerate demands removal); perf impact not measurable without live infra — noted, monitored post-CI |
| New revision changes head | branching if another migration lands concurrently | `down_revision=b4b471ffc2bd` keeps a single head; conflict visible immediately in `alembic heads` |
| DDL differs from models by even one detail | `alembic check` still fails | DDL copied 1:1 from the models (the drift dump is model-derived); acceptance = `alembic check` **exit 0 after upgrade** (kept strict) |
| Downgrade discards data added to the new columns | standard lossy-downgrade exposure | documented; downgrade restores the four pre-drift indexes and is round-trip tested on SQLite |

### 5.4 Validation results (candidate tree only, executed this run)

| Step | Command | Result | Exit |
|------|---------|--------|------|
| Proposal shown | this document §5.1–5.3 written **before** the file was created anywhere | — | — |
| Fresh DB upgrade | `alembic upgrade head` (new `sqlite:///./probe_check.db`) | full chain incl. `b4b471ffc2bd → v6driftbf01`; 31 tables (30 app + `alembic_version`), 0 causal tables | 0 |
| **Acceptance** | `alembic check` (fresh, post-upgrade) | `No new upgrade operations detected` | **0** |
| Single head | `alembic heads` | `v6driftbf01 (head)` — exactly one | 0 |
| Round-trip | `alembic downgrade -1` → `alembic upgrade head` → `alembic check` | downgrade 0, re-upgrade 0, check 0 | 0/0/0 |
| README flow (final state) | `alembic upgrade head` + `alembic current` in candidate | head applied, `v6driftbf01 (head)` | 0/0 |
| Evidence | `logs/v6_gate_closure/v6_mig_check_fresh.txt`, `v6_mig_check_roundtrip.txt` | full check outputs recorded | — |

The first round-trip attempt failed inside SQLite’s batch rebuild (it re-created a unique
index on a column being dropped); the migration was amended to drop the four
drift-created indexes before the batch drops, then re-validated clean on a fresh database
(table above). The candidate’s application database, left in that partial state, was a
temp artifact and was deleted and rebuilt from scratch afterwards.

Postgres/Redis/live validations remain `BLOCKED EXTERNALLY` (infrastructure unauthorized —
gate G-1/G-2/G-3): the SQLite path is proven, the PG path is exercised by the first CI run.

---

## 6. Approval-decision list (smallest safe path forward)

1. **Approve manifest A–F verbatim** (107 verified paths) together with the §1.3
   amendment (→ 110 paths once item 2 is approved; → 111 if item 4 approves M-PKG)
   → enables staging (staging itself will be executed only under its own explicit
   authorization).
2. **Approve R-PKG** — 3 lines in 2 tracked files (`pyproject.toml` ×2, `.env.example` ×1).
3. **Approve W1–W5** — minimal workflow diffs (§3.2); no scan is removed, no exit code
   ignored, `alembic check` stays strict.
4. **Approve M-PKG** — one new guarded migration (§5); no history rewrite, no check removal.
5. **Decide dev-lock policy** — retire gitignored `requirements-dev.txt` as an install/audit
   source (recommended), or regenerate it separately later (dependency-policy decision).
6. **After 1–5:** apply, re-run gates + fresh-clone procedure on the committed tree, then
   **separately authorize push** → observe first CI run → R3 can close only on a green run.

Do not publish until R1–R4 are `PASS`.

---

## 7. Evidence index (`logs/v6_gate_closure/`, gitignored, 25 files)

- **Gates/suite (working tree):** `v6_r_gates.txt` (ruff/mypy/bandit/diff-check),
  `v6_r_semgrep_ci.json` + `v6_r_semgrep_stderr.txt` (6 findings, 0 in campaign files),
  `v6_r_closure_suite.txt` + `_exit.txt` (2860/7/0, exit 0, 2277.44 s).
- **Audits:** `v6_r_audit_bare.json` + `_exit.txt`, `v6_r_audit_runtime.json`,
  `v6_r_audit_dev.json` + `_exit.txt`, `v6_r2_pipaudit_fresh.json` (34/3 pre-remedy),
  `v6_r2_pipaudit_final.json` (**0 vulns, exit 0**).
- **Migrations:** `v6_r_alembic_drift.txt` (33 ops, UTF-16) + `_exit.txt` +
  `v6_r_alembic_drift.db` (the drifted DB snapshot),
  `v6_mig_check_fresh.txt` (M-PKG acceptance: check exit 0),
  `v6_mig_check_roundtrip.txt` (downgrade→upgrade→check, all exit 0).
- **R2 install chain:** `v6_r2_pip_install.txt` (ResolutionImpossible),
  `v6_r2_pip_install_remedy.txt` (semgrep Windows sdist wall),
  `v6_r2_pip_install_remedy2.txt`, `v6_r2_pip_install_remedy3.txt` (install exit 0, 304 s).
- **Candidate suites:** `v6_r2_candidate_suite.txt` + `_exit.txt` (2860/7/0, exit 0,
  3120.90 s), `v6_r2_candidate_suite_final.txt` + `_exit.txt` (2860/7/0, exit 0,
  3039.81 s).

## 8. Disclosures

1. **Historical temp evidence wiped:** automatic OS temp cleanup deleted the prior session’s
   `v6_*` campaign logs (and the first candidate tree) from `%TEMP%` after the V6 documents
   were written. Documented numbers in `INTERLOCK_V6_PHASE0_BASELINE.md` §8 /
   `INTERLOCK_V6_FINAL_REPORT.md` remain the record; nothing was re-fabricated. This run’s
   evidence was copied to the durable gitignored `logs/v6_gate_closure/`.
2. **Candidate location:** moved to `%TEMP%\opencode\v6_r2_candidate` (pre-approved temp
   area) after the cleanup event; contents built byte-exact from HEAD + manifest overlay.
3. **`.env` touch (this run):** a relative-path `[IO.File]` write intended for the candidate
   also rewrote the real `.env` once. Verified content-neutral: pattern did not match (no
   substitution), 2,987 bytes all ASCII, no BOM → byte-identical content; only mtime changed
   (00:13:43). The `.env` was never printed; subsequent operations used absolute paths.
4. **Suite timing:** the working-tree suite run took 2277.44 s vs the earlier 1254.86 s for
   identical counts (2860/7/0), attributed to concurrent audit/scan load during this run.
5. **Semgrep action behavior:** the 6 pre-existing findings do not fail CI (semgrep-action
   default is non-strict; CLI exit 0 recorded), and none are in campaign-touched files.
6. **Candidate post-suite scan:** the run generated artifacts only inside the candidate
   (`.coverage`, `coverage.xml`, procedure `.env`, `intentlock.db`, `probe_check.db`,
   `logs/stress_scorecard.json`, `intentlock.egg-info/` ×5 from `pip install -e`,
   `keys/` ×2 written by the app during the smoke startup, plus the proposal migration
   file). All were enumerated and isolated; every one of the 54 modified and 53 untracked
   manifest paths remains byte-identical to the working tree; `web/` = 60/60 = HEAD.
7. **Candidate app DB rebuilt:** the first downgrade round-trip attempt crashed inside
   SQLite’s batch rebuild, leaving that temp database in a partial state; the file was
   deleted and rebuilt from scratch, after which upgrade/check/round-trip all passed
   (§5.4). The repository’s own ignored `intentlock.db`, `keys/`, and `.pytest_tmp_sso.db`
   were verified untouched by this run (mtimes pre-date it; all gitignored).
8. **This report is a new untracked file** (`INTERLOCK_V6_RELEASE_GATE_R1_R4.md`); it is
   counted in §1.3’s manifest amendment. The repository otherwise remained at 54 modified
   + 53 untracked manifest paths, staged = 0, HEAD = `145a3d9`, `stash@{0}` intact, and
   the 60 `web/` deletions intact — re-verified at the end of this run.


---

## 9. Addendum — final product-completion mission (2026-10-16, later same day)

This section records the **second, independent verification pass** run under the final
product-completion mission. It supersedes nothing above; it adds new results and two
authorized changes (R-PKG v2 and the W4 defect correction). All results here are newly
measured; earlier numbers remain labeled as historical.

### 9.1 Two authorized changes applied after section 2/3

1. **R-PKG v2 — Semgrep removed from the installable extras (`pyproject.toml`).**
   Reason: the supported install path could not produce a clean audit. Every Semgrep release
   through the latest (1.181.0) pins `mcp==1.29.0`, which carries CVE-2026-59951 (fixed in
   `mcp` 1.30.0/2.2.0). Overriding the pin is impossible (`ResolutionImpossible`, verified by
   dry-run, exit 1). Per mission section 3.2 (order 2 — a reproducible tool-installation
   architecture that preserves security coverage), Semgrep was removed from the `[security]`
   extra; CI coverage is unchanged because both workflows invoke it through
   `semgrep/semgrep-action@v1`, which supplies its own Semgrep. Net diff vs HEAD for
   `pyproject.toml` remains 2 lines (`cyclonedx-bom>=7.0,<8.0`, `semgrep==1.181.0` → now only
   the cyclonedx line). Local scans are still possible in a separate, non-audited tool venv
   (documented in `SECURITY.md`).
2. **W4 defect correction (`security.yml` SBOM step).** The approved line
   `cyclonedx-py . --output sbom.json --format json` is invalid for cyclonedx-bom 7.5.0
   (reproduced: exit 2 — `.` is not a valid subcommand; `--output/--format` are not valid
   option names). Corrected to
   `cyclonedx-py environment --output-file sbom.json --output-format json`, verified exit 0
   producing a validated 110-component CycloneDX 1.6 SBOM. This is a defect correction inside
   the already-approved W4 scope ("generate SBOMs correctly"), not a scope expansion.

### 9.2 New verification results (all measured this pass)

| Check | Command | Result |
|-------|---------|--------|
| Working-tree suite | `pytest tests -q --no-header --no-cov` | **2860 passed / 7 skipped / 0 failed**, exit 0, 1535.59 s |
| Fresh-install suite (CI parity, with coverage) | `pytest tests -q --no-header` in fresh venv | **2860 passed / 7 skipped / 0 failed**, exit 0, 3243.58 s; coverage **83.52%** (threshold 80% passed) |
| Fresh documented install | `pip install -e ".[dev,security]"` | exit 0 |
| `pip check` (fresh) | `python -m pip check` | exit 0, no broken requirements |
| **Dependency audit (fresh, §3.3 gate)** | `python -m pip_audit` | **exit 0 — 0 known vulnerabilities / 110 dependencies** |
| Ruff | `ruff check app sdk` | exit 0 |
| MyPy | `mypy app sdk` | exit 0, 0 issues in 318 files |
| Bandit (CI parity) | `bandit -r app -ll` | exit 0 |
| Bandit (full) | `bandit -r app` | 7 Low findings (documented; exit 1 expected) |
| Semgrep (CI rule packs) | `semgrep scan --config p/security-audit p/owasp-top-ten p/python` | exit 0, 6 WARNING findings, 0 errors, 0 in release-touched files |
| SBOM | `cyclonedx-py environment …` | exit 0, 110 components, CycloneDX 1.6, validated |
| `git diff --check` | — | exit 0 |
| Alembic (fresh virgin DB) | `alembic upgrade head` / `current` / `heads` | exit 0; single head `b4b471ffc2bd` |
| Alembic round-trip | `downgrade -1` → `upgrade head` | exit 0 / exit 0 |
| `alembic check` (no M-PKG) | — | **FAIL (expected)** — 33-op drift, defect D3 |
| Startup smoke | uvicorn + `/api/v1/health`, `/api/v1/ready` | 200 `{"status":"ok"}`; 200 `{"status":"ready","db":"ok","redis":"disabled"}`; clean boot/shutdown |
| Benchmarks | `python scripts/run_benchmarks.py` | exit 0 (script defect fixed): authz 0.0083 ms, policy-eval 1.9453 ms, 1000 iters, 8-vCPU Intel |
| Migration data-safety (§5) | scenarios A/B on disposable SQLite | see `INTERLOCK_V6_MPKG_MIGRATION_REVIEW.md`; upgrade preserves all pre-existing data; **downgrade fails if any `expires_at IS NULL` row exists** (verified; recovery runbook provided) |
| Docker build/verify | — | **BLOCKED EXTERNALLY** (no Docker CLI on this host) |
| PostgreSQL runtime | — | **BLOCKED EXTERNALLY** (no PG service on this host) |

### 9.3 Gate status after this pass

- **R1 (commit plan):** `PENDING APPROVAL` — manifest verified 107/107 (+ amendments), but
  staging/commit is not authorized.
- **R2 (reproducible install):** `PASS — VERIFIED` on this host for the documented
  install → start → verify path (fresh env, full suite, smoke). Limitation: the release
  artifacts (wheel/sdist) do **not** contain `alembic/` migrations or `.env.example`
  (gap #4), so the migration step requires a source checkout until that is approved/fixed.
- **R3 (CI green):** `BLOCKED EXTERNALLY` — no commit/push authorization, so CI has not run.
- **R4 (dependency audit):** `PASS — VERIFIED` for the supported install path (0/110). The
  upstream Semgrep/`mcp` repin remains open but is no longer in the audited dependency graph.

### 9.4 New defects found and fixed this pass

- `scripts/run_benchmarks.py` crashed twice (self-approval guard tripped by
  `decided_by=None`; then the UUID-typed `decided_by` column given a string). Fixed with a
  distinct UUID approver; **no security logic changed**; benchmark now exits 0.
- README/QUICKSTART/sdk-README/ARCHITECTURE carried stale or false claims (wrong test
  counts, wrong Alembic head, nonexistent `pip install interlock`, "unauthenticated" intent
  endpoints, "production-validated" adapters). Corrected against measured behavior; the
  numeric table now reflects this pass's real runs.

### 9.5 Evidence index additions (`logs/v6_gate_closure/`)

`v6_final_baseline.txt`, `v6_final_upstream_facts.txt`, `v6_final_fresh_install.txt`,
`v6_final_fresh_pipcheck.txt`, `v6_final_fresh_pipaudit.json`, `v6_final_fresh_alembic_check.txt`,
`v6_final_sbom.json`, `v6_final_suite_wt.txt`, `v6_final_suite_candidate.txt`,
`v6_final_semgrep_ci.json`, `v6_final_benchmark_results.json`, `v6_mig_data_safety.txt`,
`v6_final_sdist.tar.gz`. New top-level reports: `INTERLOCK_V6_MPKG_MIGRATION_REVIEW.md`,
`INTERLOCK_V6_GAP_REGISTER.md`, `docs/operations/EVALUATOR_GUIDE.md`.

### 9.6 Preservation re-verified at end of pass

staged = 0; `stash@{0}` intact; 60 `web/` deletions intact; `interlock_projects/` present;
HEAD = `145a3d9`; modified (non-web) = 63 (= 56 baseline + 7 documentation/tooling files
edited this pass); untracked in scope = 57 (= 54 baseline + 3 new reports). No candidate
artifact (probe/bench/smoke/test DBs, `dist*`, `.venv-final`, `sbom.json`) exists in the
repository tree.
