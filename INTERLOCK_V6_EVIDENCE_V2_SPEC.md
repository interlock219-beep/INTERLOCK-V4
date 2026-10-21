# INTERLOCK V6 — Canonical Evidence Hash Specification (v2) and v1 Compatibility

**Status:** implemented and tested in this V6 run (WP-1).
**Implementation:** `app/domain/services/evidence_hash.py` (canonical form,
hashing, sealing) and `EvidenceVerificationService.verify_evidence_integrity`
(`app/domain/services/evidence_verification_service.py`, spec dispatch).
**Tests:** `tests/unit/test_evidence_integrity_v2.py` (39 tests).

---

## 1. Why v2 exists

Before V6, every recovery adapter computed `evidence_hash` with its own
ad-hoc formula (for example `sha256(f"{action_id}:{json(tool_arguments)}")`),
and `verify_evidence_integrity` only checked field *presence* — it never
recomputed anything (defect class V5-D3). A modified evidence record
(tenant id, target resource, timestamps, compensation payload) passed
verification unchanged; this was reproduced as the RED precondition for this
work package.

## 2. Normative definition of spec v2

### 2.1 Version marker

- Stored in the existing `recovery_metadata` JSON column:
  `recovery_metadata["evidence_hash_spec"] = "v2"`.
- **No schema migration is required** (the column already exists and is
  round-trip stable).
- Evidence **without** the marker is **legacy v1** and is verified through
  the documented compatibility path only (§4). v1 evidence is never
  reinterpreted as v2.

### 2.2 Preimage (what is hashed)

- The canonical JSON document containing **every** `RecoveryEvidence` field
  **except `evidence_hash`** (non-self-referential; the hash can never be
  computed over itself).
- Field set (exact, fixed by `dataclasses.fields(RecoveryEvidence)`):
  `evidence_id`, `action_id`, `tenant_id`, `agent_id`, `authority_grant_id`,
  `parent_action_id`, `root_action_id`, `correlation_id`, `incident_id`,
  `created_at`, `target_system`, `target_resource`, `action_type`,
  `before_state_reference`, `after_state_reference`,
  `request_payload_reference`, `response_payload_reference`,
  `compensation_payload`, `compensation_type`, `recovery_adapter_type`,
  `idempotency_key`, `dependency_edges`,
  `reversibility_classification`, `state_version`, `state_hash`,
  `resource_version`, `verification_requirements`, `recovery_metadata`
  (including the v2 marker itself), `adapter_capability`.
- Adding a field to `RecoveryEvidence` automatically extends coverage
  (verified by the field-coverage test that iterates every dataclass field).

### 2.3 Canonical serialization rules

| Rule | Value |
|---|---|
| Encoding | UTF-8 |
| JSON | `sort_keys=True`, `separators=(",", ":")` (no whitespace), `ensure_ascii=True`, `allow_nan=False` |
| Datetimes | ISO-8601 UTC with microsecond precision; **naive datetimes are interpreted as UTC** |
| Enums | serialized by `.value` (recursively canonicalized) |
| Absent optionals | explicit JSON `null` — **absent ≠ empty string** (they hash differently, by design) |
| dict nesting | keys stringified, values recursively canonicalized, ordering by `sort_keys` |
| list/tuple | order preserved (list order is semantic for `dependency_edges`, `verification_requirements`) |
| set/frozenset | deterministically sorted by canonical JSON form |
| bytes | UTF-8 decode with `errors="replace"` |
| other objects | stringified with `str()` — payloads should be JSON-native for cross-platform determinism |
| Hash | SHA-256, lowercase hex, 64 characters |

`allow_nan=False` rejects NaN/Infinity (which would otherwise serialize as
non-standard tokens and silently diverge across consumers).

### 2.4 Sealing (capture side)

`seal_evidence(evidence) -> RecoveryEvidence`:

1. copies `recovery_metadata` (existing entries preserved) and sets the
   `v2` marker,
2. computes the canonical hash over the marker-stamped record with
   `evidence_hash=""`,
3. returns an **immutable** record with the hash stamped (the input is never
   mutated).

All 11 production adapters plus the `RecoveryAdapter` base class now return
`seal_evidence(RecoveryEvidence(...))` from `capture_recovery_evidence`
(adapter-parity is a test in the suite above). The ad-hoc per-adapter hash
formulas were removed.

### 2.5 Verification (read side)

`verify_evidence_integrity` keeps all legacy field-presence checks and adds a
spec dispatch on `recovery_metadata["evidence_hash_spec"]`:

| Marker state | Classification (`hash_spec` in result) | Behavior |
|---|---|---|
| absent | `v1-legacy` | field-presence checks only; **never claims v2** |
| `"v2"` | `v2` | recompute canonical hash; mismatch / missing / non-64-hex hash → reject (fail closed) |
| `"corrupt-storage"` (injected by repository load when the column exists but does not parse) | `corrupt-storage` | reject with storage-integrity issue (fail closed — silent downgrade to v1 is refused) |
| any other value (incl. non-string) | `unsupported:<value>` | reject (fail closed) |
| `recovery_metadata` not an object | `malformed` | reject (fail closed) |

The result dict gained one key, `hash_spec`; all pre-existing keys
(`evidence_id`, `integrity_ok`, `issues`, `state_hash`, `reversibility`,
`verified`) are unchanged, so existing API responses and consumers remain
backward compatible (the REST response model filters additional keys).

### 2.6 Persistence fidelity

Verified by round-trip tests against `SQLAlchemyRecoveryEvidenceRepository`:

- `incident_id` is stored/loaded **exactly** (the previous load-time
  `or ""` collapsed `None` → `""`, which changed the canonical document and
  failed recomputation after a faithful round-trip; this was fixed).
- `recovery_metadata` (with the marker) round-trips as JSON.
- UTC `created_at` round-trips to an identical canonical timestamp on
  SQLite (both aware-UTC and naive-load forms canonicalize to the same
  string). Evidence timestamps are expected to be UTC app-wide.

## 3. Threat model (honest limits — read before relying on v2)

v2 provides **tamper-evidence against naive modification**: an editor who
changes a stored field without recomputing the canonical hash is detected
(field-level coverage proven by test). It also detects accidental storage
corruption.

It is **not a signature and not immutable storage**:

- An actor with write access to evidence storage *and* knowledge of this
  public specification can recompute a valid hash over modified content.
- An attacker can strip the `v2` marker (downgrade to `v1-legacy`); the
  verifier stays *honest* about which spec was applied (it never mislabels
  v1 as v2), but the weaker path then applies. This limitation is pinned by
  an explicit test.
- A corrupt `recovery_metadata` column is rejected (§2.5) rather than
  silently downgraded.

Tamper-*proof* evidence requires signed receipts backed by external key
management (KMS/Vault) with key rotation — a production-gap item requiring
external validation; it is not claimed here.

## 4. v1 compatibility and rollout

- **Readers:** evidence written before V6 has no marker → field-presence
  path (`hash_spec == "v1-legacy"`). No reinterpretation, no backfill
  required.
- **Writers:** every `capture_recovery_evidence` implementation seals v2
  as of this run.
- **Upgrade path:** `seal_evidence()` on a legacy record upgrades it to v2
  (tested); a future backfill job may re-seal stored v1 evidence **only** if
  the original record content is guaranteed unmodified (re-sealing
  re-establishes integrity only from that point).
- **Rollout behavior:** mixed v1/v2 stores verify correctly (both
  round-trip tests pass); unsupported future spec markers fail closed so a
  rollback to older readers cannot silently mis-verify new evidence.

## 5. Evidence

| Item | Result |
|---|---|
| WP-1 unit suite | `pytest tests/unit/test_evidence_integrity_v2.py -q --no-header --no-cov` → **39 passed, exit 0** |
| RED precondition | tampered v2 record accepted: `integrity_ok=True, issues=[]` recorded before the fix; collection RED `ModuleNotFoundError` for the absent feature |
| Field coverage | every dataclass field except `evidence_hash` mutates the hash (test-enforced) |
| Adapter parity | all 11 adapters + base class seal v2 with matching recomputation (test-enforced) |
| Persistence | v2 and v1 round-trips + corrupt-column rejection (test-enforced) |
| Lint/type | `ruff check app sdk` clean including this change |
