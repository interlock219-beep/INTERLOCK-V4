from __future__ import annotations

from app.domain.entities.forensic_types import (
    AuditLogEntry,
    EvidenceChainLink,
    MerkleTreeSnapshot,
)
from app.domain.repositories.forensic_audit_repository import ForensicAuditRepository


class InMemoryForensicAuditRepository(ForensicAuditRepository):
    """In-memory implementation of :class:`ForensicAuditRepository`.

    Suitable for unit tests and single-process deployments.  Entries are
    stored in insertion order to preserve append-only semantics.
    """

    def __init__(self) -> None:
        self._entries: dict[str, list[AuditLogEntry]] = {}
        self._index: dict[str, AuditLogEntry] = {}
        self._merkle_roots: dict[str, tuple[str, int]] = {}
        self._snapshots: dict[str, list[MerkleTreeSnapshot]] = {}
        self._chain_links: list[EvidenceChainLink] = []

    async def append_entry(self, tenant_id: str, entry: AuditLogEntry) -> AuditLogEntry:
        if tenant_id not in self._entries:
            self._entries[tenant_id] = []
        self._entries[tenant_id].append(entry)
        self._index[entry.entry_id] = entry
        return entry

    async def get_entry(self, tenant_id: str, entry_id: str) -> AuditLogEntry | None:
        entry = self._index.get(entry_id)
        if entry is not None and entry.tenant_id == tenant_id:
            return entry
        return None

    async def list_entries(
        self,
        tenant_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[AuditLogEntry], int]:
        entries = self._entries.get(tenant_id, [])
        total = len(entries)
        page = entries[offset : offset + limit]
        return page, total

    async def list_by_event_type(
        self,
        tenant_id: str,
        event_type: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[AuditLogEntry], int]:
        entries = [e for e in self._entries.get(tenant_id, []) if e.event_type.value == event_type]
        total = len(entries)
        page = entries[offset : offset + limit]
        return page, total

    async def get_latest_entry(self, tenant_id: str) -> AuditLogEntry | None:
        entries = self._entries.get(tenant_id, [])
        return entries[-1] if entries else None

    async def save_merkle_root(
        self,
        tenant_id: str,
        root_hash: str,
        tree_size: int,
        snapshot: MerkleTreeSnapshot | None = None,
    ) -> None:
        self._merkle_roots[tenant_id] = (root_hash, tree_size)
        if snapshot is not None:
            if tenant_id not in self._snapshots:
                self._snapshots[tenant_id] = []
            self._snapshots[tenant_id].append(snapshot)

    async def get_latest_merkle_root(self, tenant_id: str) -> tuple[str, int] | None:
        return self._merkle_roots.get(tenant_id)

    async def save_chain_link(self, tenant_id: str, link: EvidenceChainLink) -> EvidenceChainLink:
        self._chain_links.append(link)
        return link

    async def list_chain_links(
        self,
        tenant_id: str,
        evidence_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[EvidenceChainLink], int]:
        matches = [
            link
            for link in self._chain_links
            if link.tenant_id == tenant_id
            and (link.parent_evidence_id == evidence_id or link.child_evidence_id == evidence_id)
        ]
        total = len(matches)
        page = matches[offset : offset + limit]
        return page, total

    async def count_entries(self, tenant_id: str) -> int:
        return len(self._entries.get(tenant_id, []))


__all__ = ["InMemoryForensicAuditRepository"]
