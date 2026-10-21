# INTERLOCK V6 — M-PKG MIGRATION REVIEW (READ-ONLY, NOT APPLIED)

**Status of the migration itself: `PENDING APPROVAL` — M-PKG is NOT in the repository and must not be
applied to any non-disposable database until the user authorizes it.**
This document is the mission section-5 review, produced from the migration source, live
drift evidence, and destructive testing performed **only on disposable SQLite databases**.

- Review date: 2026-10-16
- Migration file (candidate tree only): `v6driftbf01_v6_v5_model_drift_backfill.py` (300 lines,
  revision `v6driftbf01`, revises `b4b471ffc2bd`, creates a single new head)
- Test evidence: `logs/v6_gate_closure/v6_mig_data_safety.txt` (scenarios A/B),
  `v6_final_fresh_alembic_check.txt` (33-op drift WITHOUT M-PKG), prior validation in
  `INTERLOCK_V6_RELEASE_GATE_R1_R4.md` §5

---

## 1. What problem M-PKG solves (defect D3)

After the V6 schema code landed, `alembic check` on a migrated database reports **33 new upgrade
operations** (exit 1; evidence `v6_final_fresh_alembic_check.txt`): the ORM models define schema
that no migration ever applied — two whole tables, eleven columns, and fifteen indexes missing or
stale. The strict drift gate (`alembic check`, preserved in `ci.yml` W2) therefore fails on every
fresh database, and CI (R3) cannot go green until the drift is reconciled. The rules forbid hiding
this (removing/weakening `alembic check`, rewriting migration history), leaving exactly one honest
option: a forward migration that reconciles models ↔ migrations. That migration is M-PKG.

## 2. Complete operation inventory

### 2.1 Upgrade operations (all guarded — re-runs are no-ops)

| # | Operation | Target | Guard | Data effect |
|---|-----------|--------|-------|-------------|
| 1 | `create_table identity_providers` (19 cols, enums `provider_type`, `provider_status`) | new table | `has_table` | none (empty table) |
| 2 | `create_table sso_states` (12 cols, enums `sso_provider_type`, `sso_state_status`, unique `state_token`) | new table | `has_table` | none (empty table) |
| 3 | `add_column tenant_id VARCHAR(64) NULL` | checkout_sessions | column-exists | none |
| 4 | `add_column customer_id VARCHAR(128) NULL` | checkout_sessions | column-exists | none |
| 5–7 | `add_column affected_session_ids / affected_token_ids / affected_action_ids TEXT NULL` | containment_events | column-exists | none |
| 8 | `add_column token_id VARCHAR(64)` (nullable initially) | execution_tokens | column-exists | none |
| 9 | `add_column tenant_id VARCHAR(64)` (nullable initially) | execution_tokens | column-exists | none |
| 10 | `add_column status VARCHAR(32)` (nullable initially) | execution_tokens | column-exists | none |
| 11 | `add_column revoked_at DATETIME NULL` | execution_tokens | column-exists | none |
| 12 | `add_column before_state_snapshot TEXT NULL` | protected_actions | column-exists | none |
| 13 | `add_column created_at DATETIME` (nullable initially) | recovery_executions | column-exists | none |
| 14 | `UPDATE token_id = CAST(id AS VARCHAR) WHERE token_id IS NULL` | execution_tokens | SQL | **backfill** (row id) |
| 15 | `UPDATE tenant_id = 'unknown' WHERE tenant_id IS NULL` | execution_tokens | SQL | **backfill** (sentinel) |
| 16 | `UPDATE status = 'active' WHERE status IS NULL` | execution_tokens | SQL | **backfill** (sentinel) |
| 17 | `UPDATE created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL` | recovery_executions | SQL | **backfill** (timestamp) |
| 18 | `batch_alter`: token_id/tenant_id/status → NOT NULL | execution_tokens | batch (SQLite table rebuild) | none (all rows backfilled first) |
| 19 | `batch_alter`: expires_at → **NULLABLE** (relax) | execution_tokens | batch | none (widens) |
| 20 | `batch_alter`: created_at → NOT NULL | recovery_executions | batch | none (backfilled first) |
| 21–35 | `create_index` ×15 (see §4 list) | 11 tables | index-exists | none |
| 36–39 | `drop_index` ×4 stale (see §4) | plans, recovery_evidence, usage_records, user_mfa | index-exists | none (drops unused indexes, not data) |

### 2.2 Downgrade operations (reverse order)

1. Drop the 4 columns-dependent new indexes on execution_tokens/checkout_sessions
   (must precede the column drops below or the SQLite batch rebuild fails).
2. `batch_alter` drop `created_at` (recovery_executions) — **discards that column's data**.
3. `batch_alter` drop `token_id, tenant_id, status, revoked_at`; re-tighten `expires_at` NOT NULL
   — **discards those columns' data; the tighten can FAIL (see §7.1)**.
4. Drop 15 new indexes; drop tables `identity_providers`, `sso_states`
   (**create-then-drop lifecycle**; both are always empty at upgrade time, but any rows written
   after upgrade — real SSO provider configs — are destroyed by downgrade).
5. Drop `before_state_snapshot`; drop the 3 `affected_*` columns; drop checkout
   `tenant_id/customer_id` — **all discard data written to them**.
6. Re-create the 4 stale indexes (guarded), restoring the pre-M-PKG shape.

## 3. Drift-op ↔ model evidence mapping (all 33)

Every operation above maps 1:1 to a line of `alembic check`'s 33-op inventory
(`v6_final_fresh_alembic_check.txt`): 2 `add_table` (identity_providers, sso_states) + 11
`add_column` + 15 `add_index` + 4 `remove_index` + 1 `modify_nullable` = 33. The model sources
defining this schema: `app/infrastructure/persistence/models/` (`user_mfa`-era V4 models,
`identity_providers`/`sso_states` from the SSO feature, `execution_tokens`/`recovery_executions`
V6 fencing models, billing/usage models). No operation alters or drops any column that existed
before M-PKG; the only pre-existing constraint change is `expires_at NOT NULL → NULLABLE`
(a widening that matches the model, which allows tokens without expiry).

## 4. Index actions in detail

Created (15, all guarded by existence check):
`ix_identity_providers_tenant_id`, `ix_sso_states_state_token` (UNIQUE), `ix_sso_states_tenant_id`,
`ix_agent_sessions_intent_id`, `ix_checkout_sessions_tenant_id`,
`ix_containment_events_target_authority_id`, `ix_execution_tokens_status`,
`ix_execution_tokens_tenant_id`, `ix_execution_tokens_token_id` (UNIQUE), `ix_invoices_subscription_id`,
`ix_protected_actions_actor_user_id`, `ix_subscriptions_plan_id`, `ix_usage_records_period_end`,
`ix_usage_records_period_start`, `ix_webhook_events_event_type`.

Dropped as stale (4; models no longer define them): `ix_plans_tier`,
`ix_recovery_evidence_idempotency_key` (non-unique — no constraint lost),
`ix_usage_records_period` (composite, replaced by the two single-column indexes above),
`ix_user_mfa_user_id` (non-unique index over the PK column — no constraint lost).
**No dropped index carries uniqueness or a foreign key; no constraint is weakened anywhere in
the migration.** No foreign keys are added or dropped by M-PKG.

## 5. SQLite batching semantics (why and what it costs)

`batch_alter_table` is required because SQLite cannot ALTER COLUMN in place; alembic emulates it
by creating a temp table, copying all rows, dropping the original, and renaming. Consequences on
real databases:

- **Upgrade**: only steps 18–20 rebuild tables (execution_tokens, recovery_executions).
  On a large table this is a full copy — expect proportional time, temporary 2× disk usage,
  and a brief exclusive lock during the final rename. All other steps are incremental.
- **Downgrade**: rebuilds the same two tables plus column drops on 4 more tables — larger blast
  radius, same cost profile.
- On PostgreSQL (production-scope target), batch is unnecessary: native `ALTER TABLE` applies
  without table rebuilds, and DDL is transactional. **Not verified here — no PostgreSQL
  infrastructure is available on this host (BLOCKED EXTERNALLY).**

## 6. Test results (all on disposable SQLite DBs, this session)

Virgin database (`v6_final_candidate`, tracked files only):
`upgrade head` → exit 0; `alembic current` = `b4b471ffc2bd (head)` (single head;
`alembic heads` returns exactly one); `downgrade -1` → exit 0; re-`upgrade head` → exit 0.

Representative-data database (13 tables seeded, 37 rows, scenario A of `v6_mig_data_safety.txt`):

| Check | Result |
|---|---|
| `upgrade head` over populated tables | exit 0 |
| Pre-existing columns/rows byte-identical after upgrade | **PASS (0 problems)** |
| token_id backfill = row id, tenant_id = 'unknown', status = 'active' | **PASS (0 bad rows)** |
| created_at backfilled (0 NULLs) | PASS |
| 4 stale indexes dropped / 15 new indexes present | PASS (all probed) |
| identity_providers + sso_states created empty | PASS |
| `alembic check` = 0 **with data present** | **PASS** |
| Guarded re-run (stamp + re-upgrade over migrated DB) | **PASS — exit 0, zero schema/data change** |
| Unique token_id index vs CAST(id) values | no violation possible (ids unique) |
| Backup drill: file-copy while stopped → integrity_check ok, alembic current = pre-head, row counts match | **PASS** |
| Restore drill: restore copy → integrity ok, alembic current exit 0, data present | **PASS** |
| Clean round-trip with data (scenario B): downgrade → 0 leftover added columns, 4 stale indexes re-created, expires_at NOT NULL restored, pre-existing data intact, re-upgrade → check = 0 | **PASS** |

## 7. Rollback limitations and irreversible risks (empirically proven)

### 7.1 Hard limitation: downgrade fails if any `execution_tokens.expires_at IS NULL` row exists
M-PKG relaxes `expires_at` to nullable. Any token written without expiry after M-PKG (a state the
model explicitly allows) makes `downgrade` **fail** with
`IntegrityError: NOT NULL constraint failed: _alembic_tmp_execution_tokens.expires_at`
(evidence: scenario A). Verified residual state after the failure: alembic_version **unchanged**
(consistent bookkeeping), original tables and all row data **intact**, but the 4 indexes pre-dropped
by the downgrade sequence stay dropped and an empty `_alembic_tmp_*` table is left behind
(SQLite non-transactional DDL). **Verified recovery runbook**: drop leftover `_alembic_tmp_*`
tables → `alembic stamp b4b471ffc2bd` → `alembic upgrade head` (guarded re-run re-creates the
lost indexes) → `alembic check` = 0 → all rows intact including the NULL-expiry row.

### 7.2 Data destroyed by a clean downgrade (by design, disclosed)
Everything written to M-PKG-added columns: token_id/tenant_id/status/revoked_at
(execution_tokens), created_at (recovery_executions), before_state_snapshot (protected_actions),
affected_session_ids/affected_token_ids/affected_action_ids (containment_events), tenant_id/
customer_id (checkout_sessions), plus any rows in identity_providers/sso_states.
No pre-M-PKG data is ever touched by a downgrade (proven, scenario B).

### 73 Other residual risks
- **No history rewrite**: M-PKG is a new head after `b4b471ffc2bd`; the 3 pre-existing V6
  migrations and all earlier history are untouched. Single-head invariant proven.
- **No production-scale timing data**: rebuild cost on multi-million-row tables unmeasured
  (no representative dataset available). Run the backup drill + upgrade on a staging copy first.
- **PostgreSQL behavior unverified** on this host (no PG service; CI's postgres service will be
  the first real check after approval).
- Idempotency is defense-in-depth, not a license to re-run blindly: after a *partial* failure,
  follow the §7.1 runbook rather than re-running alembic directly.

## 8. Recommendation

M-PKG is necessary (D3 otherwise keeps R3/G6 red forever), correctly guarded, data-preserving on
upgrade (proven against populated databases), honest about its downgrade scope, and comes with a
verified recovery runbook for its one discovered failure mode. The decision requested:
**authorize adding `v6driftbf01` to the repository's migration set** (which then makes
`alembic check` pass in CI and completes G6), or decline and accept the drift gate as a documented
release blocker.
