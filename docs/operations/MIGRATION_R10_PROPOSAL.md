# Migration history repair proposal (MIG-01 / MIG-02) — approval required

**Status: PROPOSAL. Nothing in the migration history has been modified, no
downgrade has been executed, and no database outside a disposable temporary
file has been touched.**

This document is the evidence-backed remediation proposal for the two open
migration findings. It is written for the owner to approve or reject.

---

## 1. What is actually broken (MIG-01)

**One migration has a `downgrade()` that does not invert its `upgrade()`:**

`alembic/versions/3cebbede5768_drop_removed_tables_and_add_missing_.py`

| | |
|---|---|
| `upgrade()` (lines 21–35) | adds the column `after_state_snapshot` to `protected_actions` **and drops eight tables**: `state_deltas`, `state_checkpoints`, `durable_execution_steps`, `recovery_reports`, `ai_changesets`, `causal_state_graphs`, `recovery_confidences`, `resource_versions` |
| `downgrade()` (lines 38–40) | `pass` — it re-creates nothing and drops nothing |

The downgrade of the revision *before* it,
`alembic/versions/0010_causal_state_recovery.py` (line 334 ff.), drops indexes
and tables that `3cebbede5768.upgrade()` had already removed:

```python
def downgrade() -> None:
    op.drop_index(op.f("ix_recovery_reports_incident_id"), table_name="recovery_reports")
    ...
    op.drop_table("recovery_reports")
```

### 1.1 Failure sequence A — `downgrade base` cannot complete

```
alembic downgrade base
  -> 3cebbede5768.downgrade()  = pass      (the eight tables stay gone)
  -> 0010.downgrade()          = drop_index(ix_recovery_reports_incident_id)
                                -> sqlite: no such index ix_recovery_reports_incident_id
  => FAILED, schema half-downgraded
```

Reproduced by `tests/integration/test_alembic_migration_safety.py::
TestAlembicFreshUpgrade::test_downgrade_base_then_upgrade_head_roundtrip`
(an `xfail` that documents the defect rather than hiding it).

### 1.2 Failure sequence B — a failed downgrade bricks BOTH directions

After sequence A the schema is half-applied but Alembic's version table still
points at a revision whose `upgrade()` will now fail:

```
alembic upgrade head
  -> 3cebbede5768.upgrade() -> add_column(after_state_snapshot)
                             -> duplicate column name: after_state_snapshot
  => FAILED
```

`alembic downgrade` also still fails. **Neither direction can proceed**;
recovery needs manual SQL surgery or a restore from a backup. This is the
worst variant because the operator is left with a half-migrated database and
no supported way forward.

### 1.3 Failure sequence C — a *successful* rollback silently bricks forward recovery

```
alembic downgrade fc5e7844e4dd      # exits 0
  -> 3cebbede5768.downgrade() = pass  (after_state_snapshot stays in place)
alembic upgrade head
  -> duplicate column name: after_state_snapshot
  => FAILED
```

This variant is the most dangerous because the operator is *told* the rollback
worked. Documented by
`TestAlembicFreshUpgrade::test_successful_partial_downgrade_must_not_brick_reupgrade`.

### 1.4 What is NOT broken

- The **graph is consistent**: `alembic heads` → one head (`v6driftbf01`);
  `alembic branches` → one branchpoint (`fc5e7844e4dd`) with two children
  (`0b481f00`, `3cebbede5768`) and one merge (`67080f3cfec6`).
- The **forward path is intact**: `alembic upgrade head` on a fresh database
  succeeds (the CI migration job does exactly this on every push).
- The defect is confined to the **downgrade** direction of one revision.

**Scope:** the filesystem recovery engine (the VS Code extension, the CLI and
the `intentlock` package) does **not** use this database. This is a
**control-plane server** defect.

## 2. MIG-02 — model/migration drift

`TestAlembicGraph::test_alembic_check_no_drift` is an `xfail` documenting
*"model/migration drift (33 ops) until M-PKG is approved and applied"*.

`alembic check` compares the models against the migration history; it reports
33 operations that the models have and the history does not (or vice versa).
Consequence: `.github/workflows/ci.yml` runs `alembic check` as a gate, so
**the CI migration gate cannot pass** until this is applied. The drift is
also the mechanism by which a migration like `3cebbede5768` goes unnoticed:
nothing cross-checks "the models still match what the history does".

## 3. Options

### Option A — forward-fix with a new repair revision (RECOMMENDED, no history rewrite)

Add a **new** revision on top of `v6driftbf01` whose `upgrade()` is
*idempotent and self-healing*:

1. If `protected_actions.after_state_snapshot` exists → drop it (it is a
   duplicate left behind by a failed/partial downgrade).
2. Re-create any of the eight tables that `3cebbede5768.upgrade()` dropped
   **and** that a later revision needs — only the ones the current models
   actually reference; the four that were *deliberately* removed stay
   removed.
3. Its `downgrade()` is a clean no-op (it introduced nothing that must be
   undone).

**Why this is the safest option**

- Historical revisions are **not** rewritten: an environment that already
  applied them keeps its history and gains a repair step.
- The repair is **idempotent**: it is safe to run on a healthy database, on a
  half-downgraded one, and on a fresh one.
- It converts a *bricked* database into a recoverable one without manual SQL.

**Known limitation (must be disclosed)**: it does **not** make
`downgrade base` work. A downgrade below `3cebbede5768` remains impossible.
The product must therefore state a **supported downgrade boundary**
explicitly (see Option C) until Option B is approved.

### Option B — repair the historical `downgrade()` (needs explicit approval)

Give `3cebbede5768.downgrade()` a real inverse: re-create the eight tables
with their original columns/indexes and drop the added column.

- **Pro:** `downgrade base` becomes possible again; the history is coherent.
- **Con:** it rewrites the meaning of a revision that may already be applied
  in some environments (the divergence between "already applied" and "now
  applied" is exactly what makes a mixed fleet inconsistent).
- It is defensible **only** because the product has never been published
  (no PyPI release, no released migration history) — the owner should
  confirm that no environment outside the development machines exists.

### Option C — declare and guard the boundary (complements A or B)

State plainly in `docs/operations/SUPPORTED_PLATFORMS.md` and the operator
runbook:

> Downgrades are not supported below revision `3cebbede5768`. The server
> supports forward migrations only; a failed migration is recovered by
> restoring a backup, not by downgrading.

and add a **pre-flight guard** so an operator who tries gets a clear refusal
instead of a half-migrated database: before any downgrade runs, check that the
target revision's `downgrade()` is non-trivial (not `pass`) and that every
table the target chain still drops actually exists.

## 4. Validation plan (disposable databases only)

**Never run any of this against a real database.** The rehearsal is
scriptable and uses a throwaway file:

```bash
# 1. Fresh disposable database (SQLite file in a temp directory)
DB=$(mktemp -d)/rehearsal.db
export DATABASE_URL="sqlite:///$DB"

# 2. Forward path (must stay green)
alembic upgrade head
alembic current

# 3. Reproduce the defect on the disposable copy (expected to fail today)
alembic downgrade base        # expect: no such index ix_recovery_reports_incident_id

# 4. Apply the candidate repair on the disposable copy
alembic upgrade head

# 5. Verify the repaired state
alembic check                 # expect: no new drift beyond the documented 33 ops
alembic current

# 6. Repeat against a PostgreSQL instance in CI (the same disposable pattern
#    the existing `lint-and-test` job uses), then drop it.
```

The repository already contains the disposable rehearsals that prove the
defect (`tests/integration/test_alembic_migration_safety.py`, four `xfail`
tests). The repair should turn them green — **not** by deleting them, but by
making the behaviour correct.

## 5. Compatibility implications

| Change | Compatibility |
|---|---|
| Option A (new repair revision) | Every existing environment gains one more forward step. Environments that never downgraded are unaffected. Environments that half-downgraded are repaired. No historical revision changes. |
| Option B (rewrite history) | Environments that already applied `3cebbede5768` keep the same schema, but the *meaning* of the revision changes; a mixed fleet (some rewritten, some not) must be re-based. Acceptable only while the product is unpublished. |
| Option C (declare + guard) | No schema change. An operator who previously attempted a downgrade now gets a clear refusal instead of a half-migrated database. |

## 6. What is needed from the owner

1. **Approve one option** (A, B, or A + C).
2. **Confirm the deployment reality**: does any environment outside the
   development machines exist where a migration has already been applied?
   (The answer decides whether Option B is even admissible.)
3. **Confirm the downgrade boundary** that should be published to operators
   (Option C).

## 7. What was done in the meantime (no approval needed)

- The four `xfail` tests that document the defect remain in place, visible,
  and are reported on every integration run. They are **not** hidden and
  **not** asserted green.
- No migration file was modified.
- No downgrade was executed against any database.
- The CI migration gate (`alembic upgrade head` + `alembic check`) continues
  to report the truth: it fails on `alembic check` until the drift is
  applied, which is the honest signal.
