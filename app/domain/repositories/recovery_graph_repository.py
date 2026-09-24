"""Tenant-scoped recovery graph repository port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.recovery_graph_types import (
    ConsistencyReport,
    CycleReport,
    GraphDiff,
    GraphSnapshot,
    RecoveryGraph,
)


class RecoveryGraphRepository(ABC):
    """Persistence port for the tenant-scoped recovery graph."""

    @abstractmethod
    async def get_graph(self, tenant_id: str, graph_id: str) -> RecoveryGraph | None: ...

    @abstractmethod
    async def get_by_incident(
        self,
        tenant_id: str,
        incident_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryGraph], int]: ...

    @abstractmethod
    async def get_by_root_action(
        self,
        tenant_id: str,
        root_action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryGraph], int]: ...

    @abstractmethod
    async def save(self, graph: RecoveryGraph) -> RecoveryGraph: ...

    @abstractmethod
    async def update_version(
        self,
        tenant_id: str,
        graph_id: str,
        version: int,
    ) -> RecoveryGraph | None: ...

    @abstractmethod
    async def snapshot(
        self,
        tenant_id: str,
        graph_id: str,
        version: int,
    ) -> GraphSnapshot | None: ...

    @abstractmethod
    async def diff(
        self,
        tenant_id: str,
        graph_id: str,
        from_version: int,
        to_version: int,
    ) -> GraphDiff | None: ...

    @abstractmethod
    async def check_consistency(
        self, tenant_id: str, graph_id: str
    ) -> ConsistencyReport: ...

    @abstractmethod
    async def check_cycles(
        self, tenant_id: str, graph_id: str
    ) -> CycleReport: ...

    @abstractmethod
    async def delete(self, tenant_id: str, graph_id: str) -> bool: ...


__all__ = ["RecoveryGraphRepository"]