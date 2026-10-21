# INTERLOCK V5 — ADAPTER CAPABILITY MATRIX

**Date:** 2026-10-14 · **gate re-verification 2026-10-15:** all registry,
lab, and adapter suites re-run green after the release-gate fixes
(V5-14..V5-21); matrix claims unchanged.
**Generated with:** `RecoveryAdapterRegistry.validate_contract` +
`RecoveryCertificationLab` (`tests/unit/test_v5_adapter_registry.py`,
`tests/unit/test_recovery_certification_lab.py`)

---

## 1. HOW TO READ THIS MATRIX

- **Contract:** every adapter must pass the V5 contract battery (identity,
  async protocol surface, legacy trio, known capability value). `PASS` = 0
  contract problems.
- **Certification mode:**
  - `behavioral` — real capture → drift → simulate → compensate → verify
    round-trips plus adversarial probes ran inside an isolated temporary
    workspace.
  - `contract_only` — contract conformance only; the adapter needs live
    external systems that were not available. Reported as
    `external_validation_required`, never as behaviorally certified.
- **Scope of `PRODUCTION_VALIDATED` claims:** for the three new V5 adapters
  the capability value is scoped to the *tested local scope* documented in
  this matrix. External integrations (cloud, Vault/KMS, SIEM, ticketing,
  Postgres, k8s) are **not** covered by that claim.

## 2. ADAPTER REGISTRY (V5)

| Adapter | Type | Resource scope | Contract | Certification mode | Scope | Unit tests |
|---|---|---|---|---|---|---|
| `environment_recovery` | ENVIRONMENT | `env:<VAR>` process environment | PASS | behavioral (8 probes) | contract+behavioral — tested local scope | 15 |
| `archive_recovery` | ARCHIVE | `archive:<path>` tar.gz snapshot sets | PASS | behavioral (7 probes) | contract+behavioral — tested local scope | 13 |
| `hosts_recovery` | DNS_HOSTS | `dns:<hostname>` hosts-file entries | PASS | behavioral (6 probes) | contract+behavioral — tested local scope | 13 |
| `config_recovery` | CONFIG_ROLLBACK | `config:<file>` configuration files | PASS | behavioral (6 probes) | contract+behavioral — tested local scope | 42 (incl. traversal regression) |
| `filesystem_recovery` | FILE_VERSION | `file:<path>` file content/metadata | PASS | behavioral (5 probes) | contract+behavioral — tested local scope | 20 |
| `database_recovery` | (V4) | database records | PASS (registry) | contract_only | external validation required | `test_database_recovery_adapter.py` |
| `mock` | MOCK | synthetic targets | PASS | contract_only | test double — never production | used across suites |

Registry contract tests: `tests/unit/test_v5_adapter_registry.py` — 15/15 pass,
including capability-matrix generation, duplicate-name rejection,
non-async-protocol rejection, and selection-by-resource behavior.

## 3. DECLARED CAPABILITIES (declarations are asserted truthful by tests)

| Adapter | before | after | current | delta | drift | simulate | compensate | verify | idempotent | versioning | safe merge | merge safety |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| environment_recovery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | MERGE_CONDITIONAL |
| archive_recovery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | MERGE_CONDITIONAL |
| hosts_recovery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | MERGE_CONDITIONAL |
| config_recovery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | MERGE_CONDITIONAL |
| filesystem_recovery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | MERGE_CONDITIONAL |
| mock | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | MERGE_SAFE |

`supports_safe_merge=False` everywhere real (non-mock) is deliberate: V5
never auto-merges conflicting external state.

## 4. DRIFT / CONFLICT SEMANTICS (orchestrator contract)

The `DistributedRecoveryOrchestrator` allows a compensation to proceed when
`detect_drift` returns `NO_DRIFT` **or** `INSUFFICIENT_EVIDENCE`, and blocks
on `DRIFT_DETECTED`/`RESOURCE_MISSING`/errors. V5 canonical semantics used by
the new adapters:

| Situation | Result |
|---|---|
| Current state == recorded before-state | `NO_DRIFT` (not yet applied, or already restored) |
| Current state == recorded after-state | `NO_DRIFT` (expected post-action state) |
| After-state recorded, current matches neither | `DRIFT_DETECTED` (external change) |
| No after-state recorded, current differs from before | `INSUFFICIENT_EVIDENCE` — deviation may be the protected action's own effect; compensation proceeds under authorization + conflict gates |
| No before-state recorded at all | `INSUFFICIENT_EVIDENCE` (fail-open for compensation only; execution still fails closed without a before-state) |

Conflict checks mirror the V4 config-adapter precedent: without a recorded
after-state there is nothing to conflict against → `NO_CONFLICT`; with one,
a third state → `CONCURRENT_MUTATION`.

**Hosts adapter is hostname-scoped:** drift/conflict compare only the lines
resolving the action's hostname; unrelated hosts-file entries changing is not
drift for this compensation (the restore preserves unrelated entries).

**Note (documented divergence):** the legacy planning-service execution path
(`RecoveryPlanningService._execute_with_protocol_adapters`) still blocks on
*any* drift status other than `NO_DRIFT`, while the V5 orchestrator passes
`INSUFFICIENT_EVIDENCE`. The new adapters are wired through the V5
orchestrator path; the divergence is registered in
`INTERLOCK_V5_PRODUCTION_GAP_MATRIX.md`.

## 5. SECURITY CONTROLS PER ADAPTER

| Control | env | archive | hosts | config | filesystem |
|---|---|---|---|---|---|
| Tenant isolation (`_verify_tenant_isolation`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Authorization fail-closed (`_verify_compensation_authorization`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Idempotency-key enforcement | ✅ | ✅ | ✅ | ✅ | ✅ |
| Input validation | var-name charset (`[A-Za-z_][A-Za-z0-9_]*`, no `=`/NUL/newline) | absolute path, NUL, root, allowed-roots | hostname charset (no space/slash/`#`/NUL) | `..`/NUL traversal | `..` traversal |
| Write containment at execute time | name-pattern + allowed prefixes | archive must stay in state-dir; target re-validated against allowed-roots | payload `hosts_path` must equal configured file | payload path must resolve inside config dir (**new V5 hardening**) | base-path + traversal (**V4**) |
| Atomic writes | n/a (environ) | ✅ temp+replace | ✅ temp+replace | ✅ temp+replace | ✅ |
| Value redaction in results | ✅ hash-only surfaces | hash-only state refs | hash-only state refs | hash-based refs | hash-based refs |
| Deny-by-default allow-list | `allowed_prefixes` (capture refuses) | `allowed_roots` | single configured file | config-dir scoped | base-path scoped |

## 6. CERTIFICATION PROBES (behavioral)

| Adapter | Probes | What they prove |
|---|---|---|
| environment_recovery | 8 | capture w/ redaction, full drift contract, restore of set value, verify, value redaction, var-name injection, idempotency, tenant guard |
| archive_recovery | 7 | snapshot creation, file restore round-trip, verify, tampered-archive refusal, path-containment, insufficient-drift semantics, tenant guard |
| hosts_recovery | 6 | byte-exact CRLF restore, verify, hostname-scoped drift, conflict semantics, hostname injection, write-redirection refusal |
| config_recovery | 6 | content restore round-trip, verify, drift (unchanged/changed), restore-deleted, traversal guard |
| filesystem_recovery | 5 | content restore round-trip, verify, restore-deleted, idempotency, traversal guard |

All probe results: `tests/unit/test_recovery_certification_lab.py` (8/8) —
including that a *crashing* probe is reported as a failure rather than a pass,
and that contract-only adapters never receive fabricated behavioral results.

## 7. KNOWN LIMITATIONS (per adapter)

- **environment_recovery:** process-local (`os.environ`/injected mapping);
  values live in the compensation payload (required for restore) — payload
  access must be restricted to the evidence store's access controls.
- **archive_recovery:** symlinks inside snapshotted directories are skipped
  (counted, excluded from the manifest digest so verification round-trips);
  gzip is not deduplicated across actions.
- **hosts_recovery:** a fully deleted hosts file is *not* fabricated
  automatically (`REQUIRES_MANUAL_ACTION` — other entries would be lost);
  no DNS-server interaction, file-level only.
- **config_recovery:** evidence capture must occur after the action with the
  pre-action before-state supplied by the pipeline (V4 semantic, now honored
  via the `before_snapshot` parameter/action snapshot); `config_dir`
  provenance relies on evidence-store integrity (see gap matrix).
- **filesystem_recovery:** default capture preserves metadata/ownership/
  ACL/xattrs — measured ~63 ms per capture (see benchmark report); disabling
  preserve flags trades fidelity for speed.
