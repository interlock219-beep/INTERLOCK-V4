from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.forensic_types import (
    AuditLogEntry,
    EvidenceChainLink,
    MerkleTreeSnapshot,
)


class ForensicAuditRepository(ABC):
    """Persistence port for append-only forensic audit log entries."""

    @abstractmethod
    async def append_entry(self, tenant_id: str, entry: AuditLogEntry) -> AuditLogEntry: ...

    @abstractmethod
    async def get_entry(self, tenant_id: str, entry_id: str) -> AuditLogEntry | None: ...

    @abstractmethod
    async def list_entries(
        self,
        tenant_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[AuditLogEntry], int]: ...

    @abstractmethod
    async def list_by_event_type(
        self,
        tenant_id: str,
        event_type: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[AuditLogEntry], int]: ...

    @abstractmethod
    async def get_latest_entry(self, tenant_id: str) -> AuditLogEntry | None: ...

    @abstractmethod
    async def save_merkle_root(
        self,
        tenant_id: str,
        root_hash: str,
        tree_size: int,
        snapshot: MerkleTreeSnapshot | None = None,
    ) -> None: ...

    @abstractmethod
    async def get_latest_merkle_root(self, tenant_id: str) -> tuple[str, int] | None: ...

    @abstractmethod
    async def save_chain_link(
        self, tenant_id: str, link: EvidenceChainLink
    ) -> EvidenceChainLink: ...

    @abstractmethod
    async def list_chain_links(
        self,
        tenant_id: str,
        evidence_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[EvidenceChainLink], int]: ...

    @abstractmethod
    async def count_entries(self, tenant_id: str) -> int: ...


__all__ = ["ForensicAuditRepository"]
