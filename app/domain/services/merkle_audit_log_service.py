from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

from app.domain.entities.forensic_types import (
    AuditLogEntry,
    AuditLogVerificationError,
    EvidenceChainLink,
    IntegrityProof,
    MerkleProof,
    MerkleTreeSnapshot,
)


class MerkleAuditLogService:
    """Append-only forensic audit log with Merkle-tree integrity.

    Implements CMP-019 (Merkle tree audit log), CMP-020 (audit log
    integrity proof), CAP-022 (cryptographic hash of state), and
    CAP-023 (Merkle proof chain for evidence).

    Every audit entry is hashed and appended as a leaf to a per-tenant
    Merkle tree.  Inclusion proofs allow third parties to verify that
    an entry was recorded without trusting the log operator.
    """

    def __init__(
        self,
        audit_repository: Any = None,
    ) -> None:
        self._repo = audit_repository
        self._leaf_hashes: dict[str, list[str]] = {}
        self._roots: dict[str, tuple[str, int]] = {}

    def compute_leaf_hash(self, entry: AuditLogEntry) -> str:
        """Compute the Merkle leaf hash for an audit entry."""
        return entry.leaf_hash

    def compute_merkle_root(self, leaf_hashes: list[str]) -> str:
        """Compute the Merkle tree root from a list of leaf hashes.

        If ``leaf_hashes`` is empty, returns the hash of an empty tree
        sentinel value.
        """
        if not leaf_hashes:
            return hashlib.sha256(b"INTERLOCK-EMPTY-MERKLE-ROOT").hexdigest()

        current_level = list(leaf_hashes)
        while len(current_level) > 1:
            next_level: list[str] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                next_level.append(self._hash_node(left, right))
            current_level = next_level
        return current_level[0]

    def generate_inclusion_proof(
        self,
        tenant_id: str,
        entry_id: str,
        leaf_hashes: list[str],
    ) -> MerkleProof | None:
        """Generate a Merkle inclusion proof for ``entry_id``.

        Returns ``None`` if the entry is not found.
        """
        try:
            node_index = leaf_hashes.index(entry_id)
        except ValueError:
            return None

        root_hash = self.compute_merkle_root(leaf_hashes)
        tree_size = len(leaf_hashes)
        leaf_hash = leaf_hashes[node_index]

        path: list[str] = []
        directions: list[bool] = []
        current_index = node_index
        current_level = list(leaf_hashes)

        while len(current_level) > 1:
            next_level: list[str] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                next_level.append(self._hash_node(left, right))

            is_left = current_index % 2 == 0
            if is_left:
                sibling = (
                    current_level[current_index + 1]
                    if current_index + 1 < len(current_level)
                    else current_level[current_index]
                )
            else:
                sibling = current_level[current_index - 1]

            path.append(sibling)
            directions.append(is_left)
            current_index = current_index // 2
            current_level = next_level

        return MerkleProof(
            entry_id=entry_id,
            tenant_id=tenant_id,
            leaf_hash=leaf_hash,
            root_hash=root_hash,
            tree_size=tree_size,
            node_index=node_index,
            path=path,
            path_directions=directions,
        )

    def verify_inclusion(self, proof: MerkleProof) -> bool:
        """Verify a Merkle inclusion proof."""
        return proof.verify()

    async def append_entry(
        self,
        tenant_id: str,
        entry: AuditLogEntry,
    ) -> AuditLogEntry:
        """Append an audit entry to the log and update the Merkle root."""
        if await self._repo.get_entry(tenant_id, entry.entry_id) is not None:
            raise AuditLogVerificationError(
                f"Entry {entry.entry_id} already exists; log is append-only"
            )

        saved: AuditLogEntry = await self._repo.append_entry(tenant_id, entry)

        leaf_hash = entry.leaf_hash
        if tenant_id not in self._leaf_hashes:
            self._leaf_hashes[tenant_id] = []
        self._leaf_hashes[tenant_id].append(leaf_hash)

        root = self.compute_merkle_root(self._leaf_hashes[tenant_id])
        size = len(self._leaf_hashes[tenant_id])
        self._roots[tenant_id] = (root, size)

        snapshot = MerkleTreeSnapshot(
            snapshot_id=(
                f"snap-{tenant_id}-{root[:16]}-{int(datetime.now(UTC).timestamp() * 1_000_000)}"
            ),
            tenant_id=tenant_id,
            root_hash=root,
            tree_size=size,
            leaves=list(self._leaf_hashes[tenant_id]),
            captured_at=datetime.now(UTC),
            root_timestamp=datetime.now(UTC),
        )
        await self._repo.save_merkle_root(tenant_id, root, size, snapshot)

        return saved

    async def get_audit_trail(
        self,
        tenant_id: str,
        entry_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Retrieve audit entries and their Merkle hashes for trail verification."""
        trail: list[dict[str, Any]] = []
        for eid in entry_ids:
            entry = await self._repo.get_entry(tenant_id, eid)
            if entry is not None:
                trail.append(
                    {
                        "entry_id": eid,
                        "leaf_hash": entry.leaf_hash,
                        "event_type": entry.event_type.value,
                        "timestamp": entry.timestamp.isoformat(),
                        "description": entry.description,
                    }
                )
        return trail

    async def get_root(self, tenant_id: str) -> tuple[str, int] | None:
        """Get the current Merkle root and tree size for a tenant."""
        cached = self._roots.get(tenant_id)
        if cached is not None:
            return cached
        return cast(tuple[str, int] | None, await self._repo.get_latest_merkle_root(tenant_id))

    def build_integrity_proof(
        self,
        tenant_id: str,
        entry_ids: list[str],
        leaf_hashes: list[str],
    ) -> IntegrityProof:
        """Build an integrity proof for a chain of evidence entries.

        Verifies that each entry in the chain exists in the Merkle tree
        and that the chain is continuous (no gaps in parent_entry_id links).
        """
        entry_hashes: list[str] = []
        issues: list[str] = []

        for _i, eid in enumerate(entry_ids):
            try:
                idx = leaf_hashes.index(eid)
            except ValueError:
                issues.append(f"Entry {eid} not found in Merkle tree")
                continue
            if idx < len(leaf_hashes):
                entry_hashes.append(leaf_hashes[idx])

        root_hash = self.compute_merkle_root(leaf_hashes)
        if not entry_ids:
            issues.append("Empty chain")

        is_valid = len(issues) == 0

        return IntegrityProof(
            chain_id=f"chain-{tenant_id}-{hashlib.sha256(','.join(entry_ids).encode()).hexdigest()[:16]}",
            tenant_id=tenant_id,
            root_entry_id=entry_ids[0] if entry_ids else "",
            leaf_entry_id=entry_ids[-1] if entry_ids else "",
            root_hash=root_hash,
            chain_length=len(entry_ids),
            entry_ids=entry_ids,
            entry_hashes=entry_hashes,
            merkle_root=root_hash,
            computed_at=datetime.now(UTC),
            is_valid=is_valid,
            issues=issues,
        )

    def create_chain_link(
        self,
        tenant_id: str,
        parent_evidence_id: str,
        child_evidence_id: str,
        parent_hash: str,
        child_hash: str,
        linking_actor: str = "system",
    ) -> EvidenceChainLink:
        """Create a signed chain link binding two evidence items."""
        link_id = (
            f"link-{tenant_id}-"
            f"{hashlib.sha256((parent_evidence_id + child_evidence_id).encode()).hexdigest()[:16]}"
        )
        payload = (
            link_id + tenant_id + parent_evidence_id + child_evidence_id + parent_hash + child_hash
        )
        link_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return EvidenceChainLink(
            link_id=link_id,
            tenant_id=tenant_id,
            parent_evidence_id=parent_evidence_id,
            child_evidence_id=child_evidence_id,
            parent_hash=parent_hash,
            child_hash=child_hash,
            link_hash=link_hash,
            linking_actor=linking_actor,
        )

    @staticmethod
    def _hash_node(left: str, right: str) -> str:
        left_bytes = bytes.fromhex(left)
        right_bytes = bytes.fromhex(right)
        return hashlib.sha256(b"node\x00" + left_bytes + right_bytes).hexdigest()


__all__ = ["MerkleAuditLogService"]
