# INTERLOCK V6 — STAGE 1 FINAL MIGRATION DECISION SUMMARY (M-PKG + downgrade guard)

**Date:** 2026-10-16 · **Stage:** 1 of the final migration/CI/release brief (read-only review)
**Status:** `PENDING APPROVAL` — **M-PKG NOT applied to the repository or any non-disposable database.**
**Repository:** `F:\Desktop_Data_2026\Desktop\INTERLOCK V4` · branch `master` · HEAD `145a3d9` (unchanged)
**Evidence (isolated, this stage):** `%TEMP%\opencode\v6_s1_lab\` — `s1_static_log.txt`,
`s1_dynamic_log.txt`, `s1_final_checks_log.txt`, disposable `db_*.db`, guarded/unguarded labs.
Scripts: `v6_s1_static.py`, `v6_s1_dynamic.py`, `v6_s1_final_checks.py` (all under `%TEMP%\opencode\`).

This summary supersedes nothing; it **adds Stage-1 evidence and corrects four prose defects** found
in `INTERLOCK_V6_MPKG_DECISION_REPORT.md` (see §4). Prior reports are left intact.

---

## 1. What was reviewed (exact artifacts)

| Artifact | Path | SHA-256 |
|---|---|---|
| **M-PKG as proposed** (300 lines, CRLF) | `%TEMP%\opencode\v6_r2_candidate\alembic\versions\v6driftbf01_v6_v5_model_drift_backfill.py` | `b739b3a9b46e0541832c623d1610b25f49b09217226eab27239c15144dc2b0de` |
| **M-PKG + guard (exact content for approval)** (319 lines) | `%TEMP%\opencode\v6_s1_lab\alembic_guarded\versions\v6driftbf01_v6_v5_model_drift_backfill.py` | `aaefd79107a497f6e81b41f755b2b3fad005e6fc123eaae6a63e0a6b7e8613e4` |
| **Repo target path (on approval)** | `F:\Desktop_Data_2026\Desktop\INTERLOCK V4\alembic\versions\v6driftbf01_v6_v5_model_drift_backfill.py` | (file does not exist in repo yet) |

The guard is a **single 19-line insertion (4 comment + 15 code)** as the first statement of
`downgrade()`, exactly per decision report §4.3. Proof (static): removing that block from the
guarded file restores the original **byte-for-byte** ⇒ nothing else changed; `revision` /
`down_revision` / `branch_labels` / `depends_on` identical; both files compile.

## 2. The seven review questions — results

| # | Question | Status | Evidence (this stage) |
|---|---|---|---|
| 1 | Guard checks affected rows **before any** schema/index/table mutation | **PASS — VERIFIED** | Guard is first statement; first destructive call occurs after it; runtime: refusal snapshot diff = **NONE** (D3) |
| 2 | Affected rows exist ⇒ downgrade refuses cleanly, no side effects | **PASS — VERIFIED** | D3: exit **1**, `RuntimeError: DOWNGRADE PRECONDITION FAILED: 1 execution_tokens row(s)…`; all tables/rows/indexes/version byte-identical before vs after; **0** `_alembic_tmp_*`; `alembic current` still `v6driftbf01 (head)` |
| 3 | No affected rows ⇒ downgrade completes successfully | **PASS — VERIFIED** | D4: exit **0**; 0 leftover added columns; 4 stale indexes re-created; 15 new indexes/2 new tables removed; `expires_at` NOT NULL restored; pre-existing rows intact; `current` = `b4b471ffc2bd` |
| 4 | upgrade → downgrade → upgrade round trip on a disposable DB | **PASS — VERIFIED** | D4: re-`upgrade head` exit **0**, strict `alembic check` exit **0**, final state = first upgrade's state except `recovery_executions.created_at` re-derived by design |
| 5 | Existing data preserved on all supported paths | **PASS — VERIFIED** | D2: 38 seeded rows / 13 tables, **0** problems after upgrade, backfills exact (`token_id`=id, `tenant_id`='unknown', `status`='active', `created_at` 0 NULLs); D3 zero-effect refusal; D4 **0** problems after downgrade + re-upgrade; D5 data intact even through the *unguarded* failure; restore drills identical (both) |
| 6 | No history rewrite; Alembic still one head | **PASS — VERIFIED** | Repo heads = `['b4b471ffc2bd']` single; with M-PKG: `alembic heads` exit 0, output exactly `['v6driftbf01 (head)']`, history = 20 revisions, first line `b4b471ffc2bd -> v6driftbf01 (head)`; the 19 existing revision files are **content-identical** repo↔candidate (12 differ only in line endings of the candidate *copy*); M-PKG is a new head, not a modification |
| 7 | Backup/restore instructions match actual rollback limits | **FAIL → corrected here** (backup/restore **PASS — VERIFIED**; decision-report §3.2 runbook **FAIL**) | Drills: file-copy-while-stopped and `sqlite3` online `.backup` both → integrity ok + content identical; restore = full rollback of schema **and** data; restore-after-failure = exact pre-failure state. **But** the recovery runbook in decision report §3.2 (`stamp v6driftbf01` → `upgrade head` → `check`) is **proven broken** (D5 Runbook A: 4 indexes still missing, `alembic check` exit ≠ 0). The runbook in migration review §7.1 (`stamp b4b471ffc2bd` → `upgrade head` → `check`) is **proven working** (D5 Runbook B: `check` exit **0**, data intact) |

## 3. Measured failure baseline (unguarded, re-verified fresh — D5)

Reproduces decision report §3.1 exactly: downgrade exit **1**;
`IntegrityError: NOT NULL constraint failed: _alembic_tmp_execution_tokens.expires_at`;
leftover table **`_alembic_tmp_recovery_executions`**; **4 indexes lost**
(`ix_execution_tokens_status`, `_tenant_id`, `_token_id`, `ix_checkout_sessions_tenant_id`);
`alembic_version` unchanged; **no data lost**. This is precisely the state the guard prevents.

## 4. Documentation defects found (decision report ≠ code ≠ measurement)

The migration **code is correct**; the following prose in `INTERLOCK_V6_MPKG_DECISION_REPORT.md` is not:

| Location | Claim | Reality (code + measured) |
|---|---|---|
| §2.1 row 1 | Upgrade backfills `users.timezone`, `users.locale`, `agents.mode`, … | M-PKG touches **no** `users`/`agents` columns; backfills are `execution_tokens.token_id/tenant_id/status` + `recovery_executions.created_at` only (review §2.1 is correct) |
| §2.1 row 2 | Upgrade **re-tightens `expires_at` to NOT NULL** and "refuses if NULLs present" | Upgrade **RELAXES `expires_at` to nullable** (model-aligned); no NULL refusal exists in `upgrade()` — D2 measured `expires_at` nullable after upgrade |
| §3 note, §5 "NULL-row incompatibility" | "column is NOT NULL after upgrade"; "Upgrade refuses if NULLs exist" | Both inherit the same inversion; only **downgrade** re-tightens, which is why the guard exists |
| §3.2 runbook | `stamp v6driftbf01` → `upgrade head` → `check` = 0 | **Proven false** (D5 Runbook A): no-op upgrade leaves indexes missing, `check` ≠ 0. Correct runbook = review §7.1 `stamp b4b471ffc2bd` (D5 Runbook B: `check` = 0) |

**Decision impact: none negative** — the upgrade is *safer* than §2.1 describes (additive + widening
only), the downgrade risk and guard recommendation are exactly as verified, and §3.1/§6/§7 behavior
claims all reproduced. No unexplained destructive effect was found; nothing requires stopping beyond
the approval stop that Stage 2 mandates.

## 5. Risks carried into the decision

1. **Downgrade destroys M-PKG-added data by design** (disclosed): values written to
   `token_id/tenant_id/status/revoked_at`, `created_at`, `before_state_snapshot`, `affected_*`,
   `tenant_id/customer_id` (checkout), **and any rows in `identity_providers`/`sso_states`**
   written after upgrade. No pre-M-PKG row data is ever touched (proven, D4/D5).
2. **Rollback of record = restore from backup**, not downgrade (both drills verified this stage);
   with the guard, a refused downgrade needs **no** restore (zero side effects, D3).
3. **NULL-expiry rows must be humanly decided** (backfill/delete/restore) — the guard refuses, never repairs.
4. **`NOT TESTED`: PostgreSQL** — all evidence is SQLite; PG transactional DDL should fail *and roll
   back* more cleanly, but no PG exists here (**BLOCKED EXTERNALLY**, G11; CI's `postgres:16`
   service is the first real check after approval).
5. **No production-scale timing** — table-rebuild cost on large tables unmeasured; run backup +
   upgrade on a staging copy first.
6. Guard covers the **only** re-tightening operation in `downgrade()` (`expires_at`); all other
   steps are drops (no data-dependent failure mode found in review of the body).

## 6. Repository state after Stage 1 (read-only proof)

`HEAD 145a3d9` · **staged = 0** · `stash@{0}` intact · `web/` deletions = **60** · modified
(non-web) = **64** · untracked in-scope = **61** (62 including this file) · artifact leaks = **NONE** ·
no `git add`/commit/push/tag · no `.env` opened · `requirements-dev.txt` untouched · all lab DBs,
builds and logs isolated under `%TEMP%\opencode\v6_s1_lab\`.

## 7. Decision requested (Stage 2 — explicit approval required)

**Recommended: APPROVE** applying M-PKG **with the §4.3 guard** exactly as hashed above:

1. Create `F:\Desktop_Data_2026\Desktop\INTERLOCK V4\alembic\versions\v6driftbf01_v6_v5_model_drift_backfill.py`
   with the guarded content (SHA-256 `aaefd791…e8613e4`).
2. This authorizes **only** the file's creation + Stage-3 verification (tests, lint, security,
   packaging, disposable-DB Alembic round trips). It does **not** authorize staging, committing,
   pushing, publishing, deploying, or migrating any production/non-disposable database.
3. Recovery runbook of record = review §7.1 (`stamp b4b471ffc2bd`), **not** decision report §3.2.
