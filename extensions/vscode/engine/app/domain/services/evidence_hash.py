"""Canonical recovery-evidence hashing — evidence hash spec **v2**.

Spec (normative, keep in sync with INTERLOCK_V6_EVIDENCE_V2_SPEC.md):

- **Preimage:** canonical JSON document containing *every* ``RecoveryEvidence``
  field **except** ``evidence_hash`` (non-self-referential).
- **Canonical JSON:** UTF-8 encoded, ``ensure_ascii=True`` (non-ASCII escaped,
  platform-stable), ``sort_keys=True``, separators ``(",", ":")`` (no
  whitespace), no floating-point locale effects (Python repr is shortest
  round-trip on all supported platforms).
- **Datetimes:** ISO-8601 in UTC with microsecond precision; naive datetimes
  are interpreted as UTC before conversion.
- **Enums:** serialized by ``.value`` (recursively canonicalized).
- **Absent optional fields:** serialized as explicit JSON ``null`` — absent is
  *not* the same as the empty string (they hash differently, by design).
- **Nested values:** dicts/lists recursively canonicalized (list order is
  semantic and preserved; sets are deterministically sorted by their canonical
  JSON form); any other non-JSON-native object is stringified with ``str()``.
  Payloads should be JSON-native for cross-platform determinism.
- **Hash:** SHA-256, lowercase hex, 64 characters.
- **Version marker:** ``recovery_metadata["evidence_hash_spec"] = "v2"``.
  Evidence *without* the marker is legacy **v1** and is verified only through
  the documented field-presence compatibility path — it is never silently
  reinterpreted as v2 (see ``evidence_verification_service``).

Threat model (read before relying on this): v2 hashing detects accidental
corruption and edits by actors who cannot recompute the canonical hash. It is
**not a signature**: an actor with write access to evidence storage who knows
this public specification can recompute a matching hash. Tamper-*proof*
evidence requires signed receipts backed by external key management
(KMS/Vault), tracked as an external-validation release blocker.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Final

from app.domain.entities.surgical_recovery_types import RecoveryEvidence

EVIDENCE_HASH_SPEC_KEY: Final = "evidence_hash_spec"
EVIDENCE_HASH_SPEC_V2: Final = "v2"
_SHA256_HEX_LENGTH: Final = 64


def is_sha256_hex(value: Any) -> bool:
    """True when *value* is a 64-char lowercase sha256 hex string."""
    return (
        isinstance(value, str)
        and len(value) == _SHA256_HEX_LENGTH
        and all(c in "0123456789abcdef" for c in value)
    )


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, datetime):
        return _to_utc_iso(value)
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def canonical_evidence_document(evidence: RecoveryEvidence) -> dict[str, Any]:
    """Return the canonical v2 document (all fields except ``evidence_hash``)."""
    document: dict[str, Any] = {}
    for spec in dataclasses.fields(evidence):
        if spec.name == "evidence_hash":
            continue
        document[spec.name] = _canonical_value(getattr(evidence, spec.name))
    return document


def canonical_evidence_json(evidence: RecoveryEvidence) -> str:
    """Return the canonical JSON preimage for the v2 hash."""
    return json.dumps(
        canonical_evidence_document(evidence),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def compute_evidence_hash_v2(evidence: RecoveryEvidence) -> str:
    """Compute the v2 SHA-256 hash for *evidence* (``evidence_hash`` excluded)."""
    preimage = canonical_evidence_json(evidence).encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()


def seal_evidence(evidence: RecoveryEvidence) -> RecoveryEvidence:
    """Stamp *evidence* with the v2 spec marker and canonical hash.

    Existing ``recovery_metadata`` entries are preserved; the original object
    is never mutated (``RecoveryEvidence`` is immutable).
    """
    metadata = dict(evidence.recovery_metadata or {})
    metadata[EVIDENCE_HASH_SPEC_KEY] = EVIDENCE_HASH_SPEC_V2
    staged = dataclasses.replace(
        evidence, recovery_metadata=metadata, evidence_hash=""
    )
    return dataclasses.replace(staged, evidence_hash=compute_evidence_hash_v2(staged))
