from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

_DELIMITER = b"\x00"
_AUDIT_ENTRY_MAGIC = b"INTERLOCK-AUDIT-V1\x00"
_LEAF_PREFIX = b"leaf\x00"
_NODE_PREFIX = b"node\x00"


class AuditEventType(StrEnum):
    ACTION_EXECUTED = "action_executed"
    EVIDENCE_CAPTURED = "evidence_captured"
    RECOVERY_PLANNED = "recovery_planned"
    RECOVERY_EXECUTED = "recovery_executed"
    RECOVERY_VERIFIED = "recovery_verified"
    CONTAINMENT_INITIATED = "containment_initiated"
    CONTAINMENT_COMPLETED = "containment_completed"
    INCIDENT_DETECTED = "incident_detected"
    INCIDENT_RESOLVED = "incident_resolved"
    POLICY_CHANGE = "policy_change"
    ANOMALY_DETECTED = "anomaly_detected"
    STATE_CHECKPOINT = "state_checkpoint"
    EVIDENCE_CHAIN_LINK = "evidence_chain_link"


class AuditEventSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    """An append-only entry in the forensic audit log.

    Each entry is hashed and included as a leaf in a Merkle tree so that
    inclusion can be proven without trusting the log operator.
    """

    entry_id: str
    tenant_id: str
    event_type: AuditEventType
    severity: AuditEventSeverity
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    actor: str = "system"
    actor_identity_hash: str = ""
    resource_id: str = ""
    parent_entry_id: str | None = None
    chain_link_id: str | None = None
    event_data: dict[str, Any] = field(default_factory=dict)
    source_system: str = "interlock"
    schema_version: str = "1.0"

    @property
    def leaf_hash(self) -> str:
        """Compute the Merkle leaf hash for this audit entry."""
        return _hash_leaf(self.canonical_bytes())

    def canonical_bytes(self) -> bytes:
        """Serialize the entry deterministically for hashing."""
        import json

        payload = {
            "entry_id": self.entry_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "actor_identity_hash": self.actor_identity_hash,
            "resource_id": self.resource_id,
            "parent_entry_id": self.parent_entry_id,
            "chain_link_id": self.chain_link_id,
            "event_data": self.event_data,
            "source_system": self.source_system,
            "schema_version": self.schema_version,
        }
        encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return _AUDIT_ENTRY_MAGIC + encoded.encode("utf-8")


def _hash_leaf(data: bytes) -> str:
    return hashlib.sha256(_LEAF_PREFIX + data).hexdigest()


def _hash_node(left: str, right: str) -> str:
    left_bytes = bytes.fromhex(left)
    right_bytes = bytes.fromhex(right)
    return hashlib.sha256(_NODE_PREFIX + left_bytes + right_bytes).hexdigest()


@dataclass(frozen=True, slots=True)
class MerkleProof:
    """Proof that an audit entry is included in a Merkle tree."""

    entry_id: str
    tenant_id: str
    leaf_hash: str
    root_hash: str
    tree_size: int
    node_index: int
    path: list[str] = field(default_factory=list)
    path_directions: list[bool] = field(default_factory=list)

    def verify(self) -> bool:
        """Verify the inclusion proof against the stored root hash."""
        if len(self.path) != len(self.path_directions):
            return False
        current = self.leaf_hash
        for sibling, is_left in zip(self.path, self.path_directions):
            if is_left:
                current = _hash_node(current, sibling)
            else:
                current = _hash_node(sibling, current)
        return current == self.root_hash


@dataclass(frozen=True, slots=True)
class IntegrityProof:
    """Integrity proof for a chain of evidence entries.

    Demonstrates that a sequence of audit entries forms an unbroken,
    tamper-evident chain from a root entry to a leaf entry.
    """

    chain_id: str
    tenant_id: str
    root_entry_id: str
    leaf_entry_id: str
    root_hash: str
    chain_length: int
    entry_ids: list[str] = field(default_factory=list)
    entry_hashes: list[str] = field(default_factory=list)
    merkle_root: str = ""
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_valid: bool = False
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class EvidenceChainLink:
    """A link binding two evidence items in a forensic chain of custody."""

    link_id: str
    tenant_id: str
    parent_evidence_id: str
    child_evidence_id: str
    parent_hash: str
    child_hash: str
    link_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    linking_actor: str = "system"
    chain_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chain_entry_hash(self) -> str:
        """Hash of this chain link entry."""
        payload = (
            self.link_id + self.tenant_id + self.parent_evidence_id + self.child_evidence_id
            + self.parent_hash + self.child_hash + self.created_at.isoformat()
            + self.linking_actor
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MerkleTreeSnapshot:
    """A snapshot of a Merkle tree at a point in time."""

    snapshot_id: str
    tenant_id: str
    root_hash: str
    tree_size: int
    leaves: list[str] = field(default_factory=list)
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    root_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class AuditLogVerificationError(Exception):
    """Raised when audit log verification fails due to an integrity violation."""


__all__ = [
    "AuditEventSeverity",
    "AuditEventType",
    "AuditLogEntry",
    "AuditLogVerificationError",
    "EvidenceChainLink",
    "IntegrityProof",
    "MerkleProof",
    "MerkleTreeSnapshot",
]
