import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities.surgical_recovery_types import (
    AdapterCapability,
    CompensationType,
    RecoveryAdapterType,
    RecoveryEvidence,
    Reversibility,
)
from app.domain.repositories.recovery_evidence_repository import (
    RecoveryEvidenceRepository,
)
from app.infrastructure.persistence.models.recovery_evidence_model import (
    RecoveryEvidenceModel,
)


class SQLAlchemyRecoveryEvidenceRepository(RecoveryEvidenceRepository):
    """SQLAlchemy adapter for RecoveryEvidenceRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_evidence_id(
        self, tenant_id: str, evidence_id: str
    ) -> RecoveryEvidence | None:
        stmt = select(RecoveryEvidenceModel).where(
            RecoveryEvidenceModel.tenant_id == tenant_id,
            RecoveryEvidenceModel.evidence_id == evidence_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def get_by_action_id(
        self, tenant_id: str, action_id: str
    ) -> RecoveryEvidence | None:
        stmt = select(RecoveryEvidenceModel).where(
            RecoveryEvidenceModel.tenant_id == tenant_id,
            RecoveryEvidenceModel.action_id == action_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_incident(
        self,
        tenant_id: str,
        incident_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryEvidence], int]:
        stmt = select(RecoveryEvidenceModel).where(
            RecoveryEvidenceModel.tenant_id == tenant_id,
            RecoveryEvidenceModel.incident_id == incident_id,
        )
        count_stmt = select(func.count()).select_from(RecoveryEvidenceModel).where(
            RecoveryEvidenceModel.tenant_id == tenant_id,
            RecoveryEvidenceModel.incident_id == incident_id,
        )
        total = self._session.scalar(count_stmt) or 0
        stmt = stmt.order_by(RecoveryEvidenceModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def list_by_root_action(
        self,
        tenant_id: str,
        root_action_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[RecoveryEvidence], int]:
        stmt = select(RecoveryEvidenceModel).where(
            RecoveryEvidenceModel.tenant_id == tenant_id,
            RecoveryEvidenceModel.root_action_id == root_action_id,
        )
        count_stmt = select(func.count()).select_from(RecoveryEvidenceModel).where(
            RecoveryEvidenceModel.tenant_id == tenant_id,
            RecoveryEvidenceModel.root_action_id == root_action_id,
        )
        total = self._session.scalar(count_stmt) or 0
        stmt = stmt.order_by(RecoveryEvidenceModel.created_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def save(self, evidence: RecoveryEvidence) -> RecoveryEvidence:
        stmt = select(RecoveryEvidenceModel).where(
            RecoveryEvidenceModel.evidence_id == evidence.evidence_id
        )
        model = self._session.scalar(stmt)
        if model is None:
            model = RecoveryEvidenceModel(
                evidence_id=evidence.evidence_id,
                action_id=evidence.action_id,
                tenant_id=evidence.tenant_id,
                agent_id=evidence.agent_id,
                authority_grant_id=evidence.authority_grant_id,
                parent_action_id=evidence.parent_action_id,
                root_action_id=evidence.root_action_id,
                correlation_id=evidence.correlation_id,
                incident_id=evidence.incident_id,
                target_system=evidence.target_system,
                target_resource=evidence.target_resource,
                action_type=evidence.action_type,
                before_state_reference=evidence.before_state_reference,
                after_state_reference=evidence.after_state_reference,
                request_payload_reference=evidence.request_payload_reference,
                response_payload_reference=evidence.response_payload_reference,
                compensation_payload=json.dumps(evidence.compensation_payload),
                compensation_type=evidence.compensation_type.value,
                recovery_adapter_type=evidence.recovery_adapter_type.value,
                idempotency_key=evidence.idempotency_key,
                dependency_edges=json.dumps(evidence.dependency_edges),
                reversibility_classification=evidence.reversibility_classification.value,
                state_version=evidence.state_version,
                state_hash=evidence.state_hash,
                resource_version=evidence.resource_version,
                verification_requirements=json.dumps(evidence.verification_requirements),
                recovery_metadata=json.dumps(evidence.recovery_metadata),
                evidence_hash=evidence.evidence_hash,
                adapter_capability=evidence.adapter_capability.value,
                created_at=evidence.created_at,
            )
            self._session.add(model)
        else:
            model.action_id = evidence.action_id
            model.agent_id = evidence.agent_id
            model.authority_grant_id = evidence.authority_grant_id
            model.parent_action_id = evidence.parent_action_id
            model.root_action_id = evidence.root_action_id
            model.correlation_id = evidence.correlation_id
            model.incident_id = evidence.incident_id
            model.target_system = evidence.target_system
            model.target_resource = evidence.target_resource
            model.action_type = evidence.action_type
            model.before_state_reference = evidence.before_state_reference
            model.after_state_reference = evidence.after_state_reference
            model.request_payload_reference = evidence.request_payload_reference
            model.response_payload_reference = evidence.response_payload_reference
            model.compensation_payload = json.dumps(evidence.compensation_payload)
            model.compensation_type = evidence.compensation_type.value
            model.recovery_adapter_type = evidence.recovery_adapter_type.value
            model.idempotency_key = evidence.idempotency_key
            model.dependency_edges = json.dumps(evidence.dependency_edges)
            model.reversibility_classification = evidence.reversibility_classification.value
            model.state_version = evidence.state_version
            model.state_hash = evidence.state_hash
            model.resource_version = evidence.resource_version
            model.verification_requirements = json.dumps(evidence.verification_requirements)
            model.recovery_metadata = json.dumps(evidence.recovery_metadata)
            model.evidence_hash = evidence.evidence_hash
            model.adapter_capability = evidence.adapter_capability.value
        self._session.flush()
        return self._to_entity(model)

    async def delete(self, tenant_id: str, evidence_id: str) -> bool:
        stmt = select(RecoveryEvidenceModel).where(
            RecoveryEvidenceModel.tenant_id == tenant_id,
            RecoveryEvidenceModel.evidence_id == evidence_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    @staticmethod
    def _to_entity(model: RecoveryEvidenceModel) -> RecoveryEvidence:
        def _safe_json(raw: str | None) -> list[str]:
            if not raw:
                return []
            try:
                data = json.loads(raw)
                return data if isinstance(data, list) else []
            except (ValueError, TypeError):
                return []

        def _safe_json_dict(raw: str | None) -> dict[str, object]:
            if not raw:
                return {}
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except (ValueError, TypeError):
                return {}

        return RecoveryEvidence(
            evidence_id=model.evidence_id,
            action_id=model.action_id,
            tenant_id=model.tenant_id,
            agent_id=model.agent_id,
            authority_grant_id=model.authority_grant_id,
            parent_action_id=model.parent_action_id,
            root_action_id=model.root_action_id,
            correlation_id=model.correlation_id,
            incident_id=model.incident_id or "",
            target_system=model.target_system,
            target_resource=model.target_resource or "",
            action_type=model.action_type,
            before_state_reference=model.before_state_reference,
            after_state_reference=model.after_state_reference,
            request_payload_reference=model.request_payload_reference,
            response_payload_reference=model.response_payload_reference,
            compensation_payload=_safe_json_dict(model.compensation_payload),
            compensation_type=CompensationType(model.compensation_type),
            recovery_adapter_type=RecoveryAdapterType(model.recovery_adapter_type),
            idempotency_key=model.idempotency_key or "",
            dependency_edges=_safe_json(model.dependency_edges),
            reversibility_classification=Reversibility.normalize(model.reversibility_classification),
            state_version=model.state_version,
            state_hash=model.state_hash,
            resource_version=model.resource_version,
            verification_requirements=_safe_json(model.verification_requirements),
            recovery_metadata=_safe_json_dict(model.recovery_metadata),
            evidence_hash=model.evidence_hash or "",
            adapter_capability=AdapterCapability(model.adapter_capability),
            created_at=model.created_at or datetime.now(UTC),
        )
