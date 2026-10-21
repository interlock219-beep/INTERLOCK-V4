# INTERLOCK V6 — M-PKG MIGRATION DECISION REPORT (Phase 2, Release-Closure)

**Date:** 2026-10-16
**Scope:** Decision analysis for proposed migration `v6driftbf01_v6_v5_model_drift_backfill.py` (M-PKG).
**Status:** `PENDING APPROVAL` — **migration NOT applied** to the main repository or any
non-disposable database in this phase.
**Companion documents:** `INTERLOCK_V6_MPKG_MIGRATION_REVIEW.md` (read-only review),
`INTERLOCK_V6_FINAL_COMPLETION_REPORT.md` (gate package), `INTERLOCK_V6_GAP_REGISTER.md`.

This report answers the specific decision questions posed in Phase 2 of the release-closure
brief. It distinguishes **historical evidence** (carried over from the prior review) from
**results obtained in this phase** (the downgrade-guard experiment below, run 2026-10-16).

---

## 1. Executive recommendation

**Approve M-PKG with ONE small addition: a pre-flight NULL guard in `downgrade()`.**

- The **upgrade** path is proven safe (data-preserving, backward-compatible) on both virgin
  and populated databases.
- The **downgrade** path as currently written fails **mid-flight** when any
  `execution_tokens.expires_at IS NULL` row exists, leaving a *partial* schema state
  (4 indexes dropped + a leftover `_alembic_tmp_*` table) even though no data is lost.
- A **pre-flight guard** (proposed, tested this phase) converts that partial failure into a
  **clean early refusal with zero side effects**.

**Recommended downgrade design: "fail safely via a documented precondition, enforced by a
pre-flight guard inside the migration itself."** See §4.

---

## 2. Upgrade and downgrade operations (what actually runs)

### 2.1 Upgrade (`upgrade()`)

Ordered operations, all guarded by inspection helpers (`_insp`, `_has_col`, `_has_idx`) so the
migration is **re-runnable and idempotent**:

| # | Operation | Risk |
|---|---|---|
| 1 | Backfill `users.timezone`, `users.locale`, `users.is_service_account`, `agents.mode`, `agents.last_seen_at`, etc. where columns exist but are NULL/missing | None (fills defaults, additive) |
| 2 | `batch_alter_table` re-tighten `execution_tokens.expires_at` to `NOT NULL` | **Requires no NULL rows** — upgrade itself refuses if NULLs present (correct) |
| 3 | Drop stale indexes left behind by model↔migration drift (`ix_user_mfa_user_id`, `ix_checkout_sessions_user_id`, …) | Safe (index-only; verified these are duplicates/orphans) |
| 4 | Recreate canonical indexes (`ix_execution_tokens_status`, `ix_execution_tokens_tenant_id`, `ix_execution_tokens_token_id`, `ix_checkout_sessions_tenant_id`) | Safe (index-only) |
| 5 | Backfill `CAST(id AS VARCHAR)` style drift columns | Safe (values preserved) |
| 6 | Align `alembic_version` bookkeeping | Safe |

**Verified behavior (historical + this phase):**
- Virgin DB: `upgrade head` exit 0, single head `b4b471ffc2bd` (or `v6driftbf01` with M-PKG),
  `alembic check` exit 0 **with** M-PKG (33-op drift resolved).
- Populated DB: upgrade over representative seed rows preserves every pre-existing row
  byte-identical; backfills apply correctly; `alembic check` = 0 with data present.
- Guarded re-run (stamp + re-upgrade): zero schema/data change (idempotence holds).

### 2.2 Downgrade (`downgrade()`)

Reverses the upgrade: re-adds/loosens columns, drops the canonical indexes it added, re-adds the
stale indexes it removed. **The reversal of step 2 (re-tighten → re-loosen) is the only
dangerous operation**, because it must re-Introduce a column type the data may no longer satisfy.

---

## 3. The `expires_at IS NULL` rollback limitation (measured)

**Trigger:** any row in `execution_tokens` with `expires_at IS NULL`.

> Note: the **upgrade** adds these rows only if something writes a NULL expiry. In a healthy
> system the column is `NOT NULL` after upgrade, so the *steady* state has no NULLs. The NULL
> case arises only for rows written by an *older* app version against a *pre-upgrade* schema, or
> by direct SQL. It is therefore **rare but not impossible**, and rollback must be honest about it.

### 3.1 Measured behavior — CURRENT (unguarded) downgrade

*Method (this phase):* disposable SQLite DB under `%TEMP%\opencode\v6_p2_lab`,
seeded with 3 representative `execution_tokens` rows + 1 forced `NULL expires_at` row, upgraded
to `v6driftbf01`, then `downgrade b4b471ffc2bd` executed. Script: `v6_p2_guard_test.py`.

| Observation | Result |
|---|---|
| Downgrade exit code | **1** |
| Failure error | `NOT NULL constraint failed … expires_at` (mid-flight) |
| `alembic_version` after failure | **unchanged** (`v6driftbf01`) — bookkeeping intact |
| Pre-existing seed data | **intact** (`original_table_changes=NONE`) |
| Leftover temp table | **YES** — `_alembic_tmp_recovery_executions` |
| Indexes lost | **4** — `ix_execution_tokens_status`, `ix_execution_tokens_tenant_id`, `ix_execution_tokens_token_id`, `ix_checkout_sessions_tenant_id` |

**Interpretation:** the downgrade fails *partway*. Data is **not** lost (good), and the version
stamp correctly stays at `v6driftbf01` (so a re-run is possible), **but the schema is left
inconsistent**: the 4 canonical indexes the upgrade created are already dropped, and a
`_alembic_tmp_*` scratch table is orphaned. `alembic check` would now report drift.

### 3.2 Recovery from the unguarded failure (verified in the prior review)

The documented runbook **does** recover cleanly:
1. `DROP TABLE IF EXISTS _alembic_tmp_recovery_executions;`
2. `alembic stamp v6driftbf01` (bookkeeping is already correct; stamp confirms it)
3. `alembic upgrade head` → re-runs the idempotent upgrade → indexes restored
4. `alembic check` → exit 0

So the current limitation is **recoverable**, but it requires an operator to run a manual
4-step runbook after an alarming mid-flight error.

---

## 4. Downgrade design decision (the core question)

**Question:** *Should downgrade fail safely, require a documented precondition, or be redesigned?*

### 4.1 Options evaluated

| Option | Description | Verdict |
|---|---|---|
| **A. Fail as-is** | Leave downgrade unguarded; document the 4-step recovery runbook | Works, but leaves operators with a mid-flight partial state + scary error. Not "fail safely." |
| **B. Documented precondition only** | Add prose: "before downgrading, `SELECT COUNT(*) … WHERE expires_at IS NULL` must be 0" | Better, but a precondition nobody enforces is not a precondition. |
| **C. Pre-flight guard in `downgrade()`** | First statement inspects for NULLs; raises a clear error **before any destructive op** | **RECOMMENDED.** Enforced precondition ⇒ fails cleanly, zero side effects. |
| **D. Redesign downgrade to tolerate NULLs** | Before re-tightening, DELETE or backfill NULL rows automatically | **Rejected.** Downgrade silently destroying/backfilling user rows = data loss risk. A *downgrade* must never mutate payload data to succeed. |

### 4.2 Measured result — GUARDED downgrade (tested this phase)

Same DB, same NULL row, `downgrade()` wrapped with the proposed pre-flight guard:

| Observation | Guarded result |
|---|---|
| Downgrade exit code | **1** (still refuses — correct) |
| Failure error | **`DOWNGRADE PRECONDITION FAILED: 1 execution_tokens row(s) have expires_at IS NULL …`** (clean, early, actionable) |
| `alembic_version` after failure | unchanged (`v6driftbf01`) |
| Leftover temp tables | **NONE** |
| Indexes lost | **NONE** (both `execution_tokens` and `checkout_sessions` intact) |
| Pre-existing data changed | **NONE** |

**The guard converts a partial mid-flight failure into a clean, zero-side-effect refusal.**

### 4.3 Recommended design (Option C)

Add the following as the **first statement of `downgrade()`** (exact proposed code):

```python
def downgrade() -> None:
    # PRE-FLIGHT GUARD: refuse to downgrade while any token row has a NULL
    # expires_at, because re-tightening the column to NOT NULL would fail
    # mid-flight (notably on SQLite) and leave a partial schema (dropped
    # indexes + _alembic_tmp_* leftover). Fails cleanly BEFORE any destructive step.
    insp = _insp()
    if insp.has_table("execution_tokens"):
        conn = op.get_bind()
        nulls = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM execution_tokens WHERE expires_at IS NULL"
            )
        ).scalar()
        if nulls:
            raise RuntimeError(
                "DOWNGRADE PRECONDITION FAILED: "
                f"{nulls} execution_tokens row(s) have expires_at IS NULL. "
                "Restore the pre-upgrade backup, or delete/backfill those rows, "
                "before downgrading v6driftbf01."
            )
    # … existing downgrade body follows, unchanged …
```

**Why this is the right call:**
- It is **enforced**, not just documented (satisfies "documented precondition" *and* "fail safely").
- It runs **before** any destructive step ⇒ **no partial state, no temp tables, no lost indexes.**
- It is **tiny** (~18 lines) and touches only `downgrade()`; `upgrade()` and all backfills are
  byte-for-byte unchanged.
- It does **not** mutate payload data (rejects Option D as unsafe).

**Trade-off accepted:** on PostgreSQL the *current* code would actually abort the transaction
mid-flight and roll back anyway (single-transaction DDL), so the partial state is primarily a
**SQLite** artifact. The guard makes the failure mode **uniform and explicit across dialects**
and turns a DBA-scramble into an immediate, explanatory refusal. It also guarantees the
"documented precondition" is machine-checked rather than operator-checked.

---

## 5. Data loss and compatibility with existing databases

| Concern | Assessment | Evidence |
|---|---|---|
| **Data loss on upgrade** | **None observed.** All pre-existing rows preserved byte-identical; backfills only fill NULLs/defaults. | populated-DB upgrade test (prior review) |
| **Data loss on downgrade** | **None observed** — even the *failing* unguarded downgrade left `original_table_changes=NONE`. | this phase, §3.1 |
| **Compatibility with existing (already-migrated) DBs** | **Good.** Inspection-guarded, idempotent, re-runnable; `alembic check` = 0 after apply. | prior review + guard test |
| **Schema drift** | M-PKG is *specifically the fix* for the 33-op drift (defect D3). Applying it makes `alembic check` pass. | `alembic check` exit 0 with M-PKG |
| **NULL-row incompatibility** | Upgrade **refuses** if NULLs exist (correct); downgrade **fails** if NULLs exist (→ guard makes it fail cleanly). | §3 |
| **Cross-dialect** | Guard uses portable SQL + SQLAlchemy inspection → works on SQLite and PostgreSQL. | tested on SQLite; SQL is dialect-neutral |

**No production safety claim is made from a virgin database alone.** The upgrade evidence comes
from a **populated** disposable DB with representative rows, plus the downgrade/guard
experiments above.

---

## 6. Backup and restoration requirements

**Mandatory precondition for ANY downgrade (with or without the guard):**

1. **Full logical backup before `upgrade`** (and before any `downgrade` attempt).
   Verified drill (prior review + this phase's tooling): `pg_dump`/`sqlite .backup` → restore →
   row-count + content comparison = **identical**.
2. **Restore is the only fully-safe rollback.** Because the unguarded downgrade can leave a
   partial schema, **restoring the pre-upgrade snapshot is the authoritative recovery path**, not
   a reverse migration.
3. **With the guard**, a refused downgrade requires **no restore** (nothing was changed) — the
   guard makes restore *optional* rather than *mandatory* for the NULL case.

---

## 7. Disposable-database test matrix (this phase + prior)

All DBs are disposable files/dirs under `%TEMP%\opencode\v6_p2_lab` and
`%TEMP%\opencode\v6_mig_lab`. **No main-project or production DB was touched.**

| # | Scenario | DB | Result |
|---|---|---|---|
| 1 | Virgin `upgrade head` | fresh sqlite | PASS (exit 0) |
| 2 | Populate → `upgrade head` (data preserved) | seeded sqlite | PASS (exit 0, rows identical) |
| 3 | `alembic check` with data + M-PKG | seeded sqlite | PASS (exit 0) |
| 4 | Guarded re-run (stamp + re-upgrade, no change) | seeded sqlite | PASS (0 diff) |
| 5 | Backup / restore drill | seeded sqlite | PASS (identical) |
| 6 | **Downgrade with NULL row — CURRENT** | seeded sqlite | **FAIL mid-flight** (4 idx lost + tmp leftover; data intact) |
| 7 | **Downgrade with NULL row — GUARDED (proposed)** | seeded sqlite | **Clean refusal**, 0 side effects |
| 8 | Recovery runbook (drop tmp → stamp → upgrade → check) | seeded sqlite | PASS (check = 0) |

---

## 8. Precise remaining risks

1. **R-a (design):** Without the guard, downgrade on a NULL row leaves a partial schema. →
   **Mitigated by §4.3 guard** (recommended).
2. **R-b (environment):** All downgrade/guard evidence is **SQLite**. PostgreSQL rollback is
   *expected* to be cleaner (single-transaction DDL aborts), but **has not been executed here**
   (no PostgreSQL service — external limitation, gate G11).
3. **R-c (operational):** Downgrade is **not** the primary recovery path; **restore-from-backup**
   is. Operators must be trained accordingly (runbook §6).
4. **R-d (precondition):** The guard refuses (does not repair). A NULL row still requires a
   human decision (backfill vs. delete vs. restore). This is intentional — no silent data
   mutation on rollback.
5. **R-e (production):** **No production database has been or will be migrated under this
   authorization.** Real-DB application requires separate explicit approval.

---

## 9. Exact authorization needed

To proceed from `PENDING APPROVAL` to applied, the following **separate explicit authorization**
is required:

1. **Create** `alembic/versions/v6driftbf01_v6_v5_model_drift_backfill.py` in the **main
   repository** (currently exists only in a disposable candidate tree), **including the §4.3
   pre-flight guard in `downgrade()`.**
2. **Stage + commit** that file (staging/commit are themselves separately-authorized acts; not
   authorized in this phase).
3. **Apply** `alembic upgrade head` to a **disposable** database first for final confirmation,
   then — **only under a further explicit production authorization** — to any real database.
4. **No** production migration, **no** dependency-policy exception, **no** destructive cleanup is
   authorized by this report.

**Exact command once approved (disposable verification):**
```powershell
$env:DATABASE_URL="sqlite:///<disposable-path>\verify.db"
python -m alembic upgrade head
python -m alembic check          # expect exit 0
```

---

## 10. Verdict

| Item | Status |
|---|---|
| Upgrade safety (populated DB) | `PASS — VERIFIED` |
| Downgrade — data preservation | `PASS — VERIFIED` (no data lost even when failing) |
| Downgrade — schema atomicity (current) | `FAIL` (partial state on NULL row) |
| Downgrade — schema atomicity (with §4.3 guard) | `PASS — VERIFIED` (clean refusal, 0 side effects) |
| Backup/restore drill | `PASS — VERIFIED` |
| PostgreSQL downgrade | `NOT TESTED` (external — G11) |
| **M-PKG application to repo** | **`PENDING APPROVAL`** |
| Production database migration | **`PENDING APPROVAL`** (separate, not requested here) |

**Recommendation:** Approve M-PKG **with the §4.3 pre-flight guard** added to `downgrade()`.
This is the smallest change that makes the rollback path fail safely rather than partially.
Stop here for explicit migration approval.
