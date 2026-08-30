from abc import ABC, abstractmethod

from app.domain.entities.surgical_recovery_types import RecoveryEvidence


class RecoveryEvidenceRepository(ABC):
    """Persistence port for RecoveryEvidence aggregate."""

    @abstractmethod
    async def get_by_evidence_id(
        self, tenant_id: str, evidence_id: str
    ) -> RecoveryEvidence | None: ...

    @abstractmethod
    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None: ...

    @abstractmethod
    async def list_by_incident(
        self,
        tenant_id: str,
        incident_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryEvidence], int]: ...

    @abstractmethod
    async def list_by_root_action(
        self,
        tenant_id: str,
        root_action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryEvidence], int]: ...

    @abstractmethod
    async def save(self, evidence: RecoveryEvidence) -> RecoveryEvidence: ...

    @abstractmethod
    async def delete(self, tenant_id: str, evidence_id: str) -> bool: ...
