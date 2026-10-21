# Interlock V5 — External Validation Runbook

**Status:** ready for operator execution. Nothing in this runbook has been executed
against real external systems in this campaign (see `INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md`
G-3/G-9). Every section states what was verified locally versus what requires an operator.

**Safety rules for all sections**

1. Use disposable, clearly-labeled test resources only (`interlock-v5-validation-*`).
2. Never point validation at production tenants, production data, or production endpoints.
3. Configuration is supplied by **variable name only** in this document — never commit or
   log secret values. Secrets are injected by the operator's secret manager.
4. Every section has an emergency-stop procedure; execute it before ending the session.
5. Charges: cloud sections may incur small charges on disposable resources — only with
   explicit user authorization beforehand.

**Notation:** *Local* = verified in this campaign on this machine.
*Operator* = requires an external system, credentials, or a second instance.

---

## 1. Cloud provider integration

**Scope:** `ExternalCapabilityDomain.CLOUD` contracts
(`app/domain/services/external_recovery_contracts.py`) and any cloud-backed recovery
targets declared by the `ExternalCapabilityRegistry`. There is **no live-validated cloud
recovery adapter** in this repository; cloud recovery is contract/simulation-only
(`ExternalCapabilityStatus.SIMULATION_ONLY` / `LOCAL_SAFE`).

**Test environment:** one sandbox cloud account (or an isolated project/subscription)
with no production resources. Minimum permissions: read-only listing plus
create/update/delete **only** on resources tagged `interlock-v5-validation`.

**Configuration variables (names only):** `CLOUD_PROVIDER`, `CLOUD_REGION`,
`CLOUD_CREDENTIALS_REF` (pointer into the operator secret manager),
`INTERLOCK_CLOUD_DRY_RUN=true|false`, `INTERLOCK_CLOUD_RESOURCE_TAG`.

**Disposable resources + cleanup:** create exactly one tagged VM/bucket/queue for the
round-trip; cleanup = delete every resource carrying the validation tag
(`cleanup: list tagged resources -> assert empty`).

**Required tests**

- *Positive:* declared contract flow for create-state capture → compensation →
  verification round-trip against the disposable resource.
- *Negative:* compensation issued for a non-existent resource id → must fail with
  a typed error, never report success.
- *Timeout:* inject a 60 s API delay (or throttling simulation) → orchestrator must
  surface failure/manual-required, never hang past step timeout.
- *Retry:* transient 500/throttle → adapter retries bounded by `max_retries`, then fails safe.
- *Permission denial:* validate with a principal lacking delete permission →
  compensation returns permission-denied, plan stops per stop conditions.
- *Partial failure:* two-resource plan where the second delete is denied → first
  compensation stays recorded, plan reports `partial`, no silent rollback claims.

**Evidence to pass:** per-test output showing request ids, resulting resource states,
adapter `CompensationResult`/`VerificationResult` payloads, and the final cleanup assert.

**Rollback / emergency stop:** `INTERLOCK_CLOUD_DRY_RUN=true` reverts the adapter to
simulation; delete all tagged resources; revoke the validation principal.

**Pass/fail criteria:** all six tests behave as specified; zero untagged resources
touched (verify via audit log); cleanup assert empty. **Local:** contract tests in
`tests/unit/test_external_recovery_contracts.py` (struct only). **Operator:** everything else.

---

## 2. Vault / KMS key management

**Scope:** `app/infrastructure/security/kms_key_manager.py` (`KMSKeyManager`), the
`KeyManager` interface it implements, and evidence/lease payload signing once G-4
(HMAC/KMS signing) is implemented. Local default key material stays in-process; the
provider-SDK path (e.g. AWS KMS via `boto3`) is unvalidated here.

**Test environment:** dev/staging KMS or Vault namespace. Minimum permissions:
`encrypt`/`decrypt`/`describe` on **one** dedicated test key
(`alias/interlock-v5-validation`); no key scheduling/deletion rights.

**Configuration variables (names only):** `INTERLOCK_KMS_PROVIDER`,
`INTERLOCK_KMS_KEY_ID`, `INTERLOCK_KMS_ENDPOINT`, `INTERLOCK_KMS_CREDENTIALS_REF`,
`INTERLOCK_KMS_TIMEOUT_SECONDS`, `INTERLOCK_KMS_MAX_RETRIES`.
(No secret values in config files or logs.)

**Disposable resources + cleanup:** one symmetric test key; cleanup = disable+schedule
deletion of that key (or delete the Vault test key); verify no other keys exist under
the validation prefix.

**Required tests**

- *Positive:* encrypt → decrypt round-trip; payload signed at evidence capture
  verifies with the public path.
- *Negative:* tampered ciphertext (one flipped byte) → decrypt must fail; evidence
  with invalid signature → verification reports tamper, never verifies.
- *Timeout:* endpoint blackholed (unroutable address) → operation fails within the
  configured timeout; service degrades per key-manager contract (no crash).
- *Retry:* inject one transient failure → bounded retry then typed error.
- *Permission denial:* principal without `decrypt` → typed permission error; recovery
  step becomes `requires_manual_action`/`failed`, never a false success.
- *Partial failure:* multi-key plan where one key is disabled mid-plan → first
  results retained, plan `partial`, resume path reports the unverifiable step honestly.

**Evidence to pass:** ciphertext/plaintext test vectors, error types per negative test,
latency for timeout test, audit-log entries for every KMS call with the test key id.

**Rollback / emergency stop:** unset `INTERLOCK_KMS_PROVIDER` (falls back to local
in-process key manager); disable the test key; revoke validation credentials.

**Pass/fail criteria:** round-trip passes; every failure mode fails *safe* (typed
error → honest step state) with zero fallback-to-success. **Local:** key-manager
unit tests with the in-process provider. **Operator:** provider-SDK path.

---

## 3. SIEM / evidence forwarding

**Scope:** `app/infrastructure/integrations/siem_adapter.py` — `SIEMAdapter` ABC with
`SplunkSIEMAdapter`, `QRadarSIEMAdapter`, `SentinelSIEMAdapter`, `MockSIEMAdapter`.
Forwarding of `RecoveryEvidence`/security events; integrity of the forwarded payload.

**Test environment:** one test index/sourcetype (Splunk), one test log (QRadar), one
test table (Sentinel). Minimum permissions: write to that index/log/table only; no
admin/capability changes.

**Configuration variables (names only):** `INTERLOCK_SIEM_PROVIDER`,
`INTERLOCK_SIEM_ENDPOINT`, `INTERLOCK_SIEM_INDEX`, `INTERLOCK_SIEM_TOKEN_REF`,
`INTERLOCK_SIEM_TLS_VERIFY`, `INTERLOCK_SIEM_TIMEOUT_SECONDS`,
`INTERLOCK_SIEM_BATCH_SIZE`.

**Disposable resources + cleanup:** test index/sourcetype created for the run; cleanup
= delete the test index / sourcetype; assert query returns zero validation events
after retention purge (or explicitly note retained-until-expiry).

**Required tests**

- *Positive:* N evidence events forwarded, queryable by `evidence_id` with fields
  intact (tenant, action, hash, outcome).
- *Negative:* malformed event (missing required field) → rejected locally with typed
  error; never silently dropped without a record.
- *Timeout:* endpoint unreachable → bounded failure; events are not acknowledged as
  delivered (no false "sent" state).
- *Retry:* transient 503 → bounded retry with backoff; duplicate-safe (event id
  dedupe on the receiver, assert no double-count).
- *Permission denial:* token without write on the test index → typed 403 → dead-letter
 /local queue, plan unaffected (forwarding failure must not corrupt recovery state).
- *Partial failure:* batch of 50 with 10 rejected → 40 reported, 10 listed with reasons.

**Evidence to pass:** receiver-side queries (counts + field samples) matched to sent
ids; dead-letter contents for denied/malformed; retry/duplicate report.

**Rollback / emergency stop:** unset `INTERLOCK_SIEM_PROVIDER` (forwarding off;
recovery continues, forwarding failures remain visible); rotate the validation token.

**Pass/fail criteria:** 100% of valid events queryable with intact fields; every
failure mode surfaces as an honest error — zero silent losses. **Local:** mock-adapter
contract tests. **Operator:** the three real providers.

---

## 4. PostgreSQL recovery

**Scope:** `app/infrastructure/recovery/database_recovery_adapter.py` — INSERT/UPDATE/
DELETE compensation against a real PostgreSQL database (the CI design already provisions
`postgres:16-alpine`; see `.github/workflows/ci.yml`). Identifier validation and
parameter binding are **Local**-verified; live round-trip is **Operator**-work.

**Test environment:** dedicated Postgres database `interlock_v5_validation`
(create/drop allowed) on a dev instance. Minimum permissions: `CONNECT` +
`SELECT/INSERT/UPDATE/DELETE` on schema `validation` only; no `DROP` on shared schemas;
no production credentials.

**Configuration variables (names only):** `DATABASE_URL` (test database),
`INTERLOCK_DB_SCHEMA=validation`, `INTERLOCK_DB_STATEMENT_TIMEOUT_MS`,
`INTERLOCK_DB_CONNECT_TIMEOUT_SECONDS`. (Credentials supplied by the operator's
secret store; never printed.)

**Disposable resources + cleanup:** `validation.recovery_probe` table seeded with
known rows; cleanup = `DROP SCHEMA validation CASCADE` + assert `to_regclass` is null.

**Required tests**

- *Positive:* insert/update/delete compensations restore byte-equal row states;
  `VerificationResult.verified=true` from an independent read.
- *Negative:* compensation against a missing row/table → typed failure; no
  half-reported success. SQL-injection probe: table/column names with quotes,
  comments, spaces → refused by `_validate_table_name`/`_validate_column_name`.
- *Timeout:* `SET statement_timeout` low + slow statement → typed timeout failure;
  connection released (no leaked sessions: assert `pg_stat_activity` count returns
  to baseline).
- *Retry:* kill connection mid-transaction (terminate backend) → bounded retry or
  typed failure; state not double-applied (idempotency key honored).
- *Permission denial:* revoke `DELETE` for the validation principal → permission
  error surfaces as failed/blocked step, plan stops per stop conditions.
- *Partial failure:* two-row plan, second row locked (`pg_advisory_lock`) → first
  compensation persisted, plan `partial`, resume completes the remainder without
  re-applying the first.

**Evidence to pass:** `EXPLAIN`/row snapshots before/after per test, error SQLSTATEs,
`pg_stat_activity` baseline comparison, cleanup assert.

**Rollback / emergency stop:** `DROP SCHEMA validation CASCADE`; unset `DATABASE_URL`
test value; never run against the application database.

**Pass/fail criteria:** every compensation byte-exact verifiable; all six failure
modes typed and fail-safe; zero objects left after cleanup. **Local:** adapter unit
tests (SQLite fixture) + identifier-validation tests. **Operator:** live PostgreSQL.

---

## 5. Kubernetes recovery

**Scope:** `ExternalCapabilityDomain.KUBERNETES` / `KUBERNETES_CONTAINMENT` contracts
in `external_recovery_contracts.py`. This repository contains **contract definitions
and contract tests only — no live Kubernetes adapter**; G-9 marks these
`external_validation_required`. This section validates the contract against a real
cluster when an adapter is implemented; until then it is the acceptance checklist for
that implementation.

**Test environment:** disposable cluster (kind/minikube or a dev namespace on an
existing cluster). Minimum RBAC: namespace-scoped `get/list/watch/create/delete` on
`pods`, `deployments`, `statefulsets` in namespace `interlock-v5-validation` only.

**Configuration variables (names only):** `KUBECONFIG` (path ref),
`INTERLOCK_K8S_NAMESPACE`, `INTERLOCK_K8S_CONTEXT`, `INTERLOCK_K8S_TIMEOUT_SECONDS`,
`INTERLOCK_K8S_GRACE_PERIOD_SECONDS`, `INTERLOCK_K8S_DRY_RUN`.

**Disposable resources + cleanup:** deployments/pods created under the validation
namespace with label `interlock-v5-validation`; cleanup = delete namespace (or delete
all labeled resources) + assert empty list.

**Required tests**

- *Positive:* capture pod state → compensate (scale/rollback) → verify observed
  generation matches expectation.
- *Negative:* compensate a non-existent workload → typed NotFound, no success claim.
- *Timeout:* API server delayed/unreachable → typed failure within timeout; no
  orphaned child processes.
- *Retry:* transient 429 from API server → bounded retry with backoff.
- *Permission denial:* RBAC without delete → Forbidden surfaces as failed step;
  plan halts per stop conditions.
- *Partial failure:* two-workload plan, second delete forbidden → first recorded,
  plan `partial`, resume-safe.

**Evidence to pass:** `kubectl get`/describe output before/after, controller
event logs, adapter result payloads, cleanup assert.

**Rollback / emergency stop:** delete validation namespace; revoke RBAC binding;
`INTERLOCK_K8S_DRY_RUN=true`.

**Pass/fail criteria:** behavior matches the contract for all six modes; zero
resources outside the validation namespace touched. **Local:** contract tests
(`tests/unit/test_external_recovery_contracts.py`). **Operator:** everything else —
*and the live adapter itself does not yet exist; this is a deliverable, not a config flip.*

---

## 6. Multi-instance lease coordination

**Scope:** `PlanLeaseStore` protocol (`app/domain/services/distributed_recovery_orchestrator.py`)
with the single implementation `InMemoryPlanLeaseStore` — **process-local** (G-1).
The protocol *is* the supported backend contract: a distributed implementation plugs in
without orchestrator changes. Redis is already part of the deployment surface
(`REDIS_URL` / `REDIS_ENABLED` in CI), so the reference backend is Redis.

**Test environment:** two OS processes (or two containers) of this application sharing
one Redis 7 instance; test plan id `validation-lease-plan`.

**Configuration variables (names only):** `REDIS_URL`, `REDIS_ENABLED=true`,
`INTERLOCK_LEASE_TTL_SECONDS`, `INTERLOCK_LEASE_BACKEND=redis`
*(backend selector to be introduced with the Redis implementation)*.

**Required tests** (against `RedisPlanLeaseStore`, to be implemented per contract):

- *Positive:* process A acquires, executes, releases; process B's acquire fails while
  held (`already_running`) and succeeds after release with `fencing_token = prev + 1`.
- *Negative:* release forged by non-owner → no effect (owner check).
- *Timeout:* A's TTL expires without renewal → B takes over with a new fencing token;
  A's late renewal fails.
- *Retry:* Redis blip (brief `NOSCRIPT`/timeout) → bounded retry; either outcome
  (acquired or explicit refusal) — never a silent double-acquire.
- *Permission denial:* Redis user limited to non-lease keys → lease ops fail typed;
  execution refuses to start (fail-closed, never "assume lease held").
- *Partial failure:* A dies mid-plan (kill -9) → step states remain as last recorded;
  B takeover resumes without re-running SUCCEEDED steps; fencing token recorded in
  execution results for audit.

**Evidence to pass:** both processes' logs correlated by plan id + fencing token;
`TTL` assertions from Redis (`PTTL`); kill/resume transcript.

**Rollback / emergency stop:** stop process B; `INTERLOCK_LEASE_BACKEND=memory`
(fallback to in-process store); flush validation keys (`DEL` pattern-prefixed).

**Pass/fail criteria:** identical semantics to `InMemoryPlanLeaseStore` contract tests
(the in-process suite is the executable specification), proven across processes.
**Local:** full in-process contract test suite. **Operator:** the Redis-backed run —
*blocked until a `RedisPlanLeaseStore` is implemented (G-1); its contract tests must
reuse the same suite as the in-memory store.*

---

## 7. Multi-instance quota reservation

**Scope:** `TenantQuotaService` (`app/domain/services/tenant_quota_service.py`) with the
backend contract `QuotaCounterStore` (specified + in-process implementation in this
campaign; distributed implementation **marked incomplete until validated**, G-2).
The in-process store's behavior is the executable specification.

**Test environment:** two application processes sharing one Redis 7 instance; tenant
`validation-quota-tenant` with policy `plans_per_day=3`, `max_concurrent_compensations=1`.

**Configuration variables (names only):** `REDIS_URL`, `REDIS_ENABLED=true`,
`INTERLOCK_QUOTA_BACKEND=redis` *(selector to be introduced with the implementation)*,
`INTERLOCK_QUOTA_WINDOW=24h`.

**Required tests** (against `RedisQuotaCounterStore`, to be implemented):

- *Positive:* 3 plan creations admitted, 4th rejected with `QuotaExceededError`;
  concurrent-compensation slot admits exactly one holder across processes.
- *Negative:* no policy registered → unlimited (unchanged semantics), asserted
  explicitly so the default never flips to blocking.
- *Timeout:* Redis unreachable → quota decisions **fail closed** with typed error
  (documented choice: deny rather than bypass limits); recovery ops surface 429/503.
- *Retry:* transient Redis error during reservation → bounded retry; a lost
  reservation is either fully applied or fully absent (no ghost increments).
- *Permission denial:* Redis user without `INCR`/`EXPIRE` → typed error → fail closed.
- *Partial failure:* reservation granted, operation fails before `end_compensation`
  (simulate crash) → TTL/window expiry releases the slot (no permanent leak); assert
  slot available after window in both processes.

**Evidence to pass:** admission ledger per process, Redis `INCR`/`PTTL` traces,
crash/recovery transcript showing slot release.

**Rollback / emergency stop:** stop the second process; `INTERLOCK_QUOTA_BACKEND=memory`
(fallback); `DELETE` validation tenant keys.

**Pass/fail criteria:** cross-process behavior equals the in-process contract tests;
fail-closed under backend outage; no leaked slots. **Local:** in-process contract tests
+ quota service tests. **Operator:** Redis-backed run — *blocked until
`RedisQuotaCounterStore` is implemented (G-2).*

---

## Summary — local vs operator

| Integration | Verified locally (this campaign) | Requires operator |
|---|---|---|
| Cloud | contract tests (structure), simulation modes | all six behavior tests, cleanup, audit-log review |
| Vault/KMS | in-process key manager unit tests | provider-SDK round-trips, audit evidence |
| SIEM | mock-adapter contract tests | Splunk/QRadar/Sentinel runs, receiver queries |
| PostgreSQL | adapter unit tests, identifier validation, CI service definition | live six-mode suite on disposable schema |
| Kubernetes | contract tests only (no live adapter exists) | implement adapter first, then six-mode run |
| Multi-instance lease | `PlanLeaseStore` protocol + full in-process contract suite | implement `RedisPlanLeaseStore`, then cross-process run |
| Multi-instance quota | `QuotaCounterStore` contract + in-process suite | implement `RedisQuotaCounterStore`, then cross-process run |

**Gate rule:** no integration may be called "validated" until its Operator column is
executed with attached evidence. Local results are labeled *contract-tested* only.
