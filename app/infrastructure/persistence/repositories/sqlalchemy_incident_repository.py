from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.incident import Incident, IncidentSeverity, IncidentStatus
from app.domain.repositories.incident_repository import IncidentRepository
from app.infrastructure.persistence.models.incident_model import IncidentModel


class SQLAlchemyIncidentRepository(IncidentRepository):
    """SQLAlchemy adapter for IncidentRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_incident_id(
        self, tenant_id: str, incident_id: str
    ) -> Incident | None:
        stmt = select(IncidentModel).where(
            IncidentModel.tenant_id == tenant_id,
            IncidentModel.incident_id == incident_id,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Incident], int]:
        stmt = (
            select(IncidentModel)
            .where(
                IncidentModel.tenant_id == tenant_id,
                IncidentModel.agent_id == agent_id,
            )
            .order_by(IncidentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = self._session.scalars(stmt).all()
        count_stmt = select(IncidentModel).where(
            IncidentModel.tenant_id == tenant_id,
            IncidentModel.agent_id == agent_id,
        )
        total = len(self._session.scalars(count_stmt).all())
        return [self._to_entity(m) for m in models], total

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: IncidentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Incident], int]:
        stmt = select(IncidentModel).where(IncidentModel.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(IncidentModel.status == status.value)
        stmt = (
            stmt.order_by(IncidentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = self._session.scalars(stmt).all()
        count_stmt = select(IncidentModel).where(IncidentModel.tenant_id == tenant_id)
        if status is not None:
            count_stmt = count_stmt.where(IncidentModel.status == status.value)
        total = len(self._session.scalars(count_stmt).all())
        return [self._to_entity(m) for m in models], total

    async def save(self, incident: Incident) -> Incident:
        stmt = select(IncidentModel).where(
            IncidentModel.incident_id == incident.incident_id
        )
        model = self._session.scalar(stmt)
        if model is None:
            model = IncidentModel(
                incident_id=incident.incident_id,
                tenant_id=incident.tenant_id,
                agent_id=incident.agent_id,
                severity=incident.severity.value,
                status=incident.status.value,
                trigger=incident.trigger,
                session_ids=json.dumps(incident.session_ids) if incident.session_ids else None,
                affected_action_ids=(
                    json.dumps(incident.affected_action_ids)
                    if incident.affected_action_ids
                    else None
                ),
                affected_resources=(
                    json.dumps(incident.affected_resources)
                    if incident.affected_resources
                    else None
                ),
                blast_radius=json.dumps(incident.blast_radius) if incident.blast_radius else None,
                containment_state=(
                    json.dumps(incident.containment_state)
                    if incident.containment_state
                    else None
                ),
                rollback_state=(
                    json.dumps(incident.rollback_state)
                    if incident.rollback_state
                    else None
                ),
                verification_state=(
                    json.dumps(incident.verification_state)
                    if incident.verification_state
                    else None
                ),
                created_at=incident.created_at,
                resolved_at=incident.resolved_at,
            )
            self._session.add(model)
        else:
            model.status = incident.status.value
            model.severity = incident.severity.value
            model.trigger = incident.trigger
            model.session_ids = (
                json.dumps(incident.session_ids) if incident.session_ids else None
            )
            model.affected_action_ids = (
                json.dumps(incident.affected_action_ids)
                if incident.affected_action_ids
                else None
            )
            model.affected_resources = (
                json.dumps(incident.affected_resources)
                if incident.affected_resources
                else None
            )
            model.blast_radius = (
                json.dumps(incident.blast_radius) if incident.blast_radius else None
            )
            model.containment_state = (
                json.dumps(incident.containment_state)
                if incident.containment_state
                else None
            )
            model.rollback_state = (
                json.dumps(incident.rollback_state)
                if incident.rollback_state
                else None
            )
            model.verification_state = (
                json.dumps(incident.verification_state)
                if incident.verification_state
                else None
            )
            model.resolved_at = incident.resolved_at
        self._session.flush()
        return self._to_entity(model)

    async def update_status(
        self,
        tenant_id: str,
        incident_id: str,
        status: IncidentStatus,
        resolved_at: datetime | None = None,
    ) -> Incident | None:
        stmt = select(IncidentModel).where(
            IncidentModel.tenant_id == tenant_id,
            IncidentModel.incident_id == incident_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = status.value
        model.resolved_at = resolved_at or datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: IncidentModel) -> Incident:
        def _safe_json_list(raw: str | None) -> list[str]:
            if not raw:
                return []
            try:
                data = json.loads(raw)
                return data if isinstance(data, list) else []
            except (ValueError, TypeError):
                return []

        def _safe_json_dict(raw: str | None) -> dict[str, Any]:
            if not raw:
                return {}
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except (ValueError, TypeError):
                return {}

        return Incident(
            incident_id=model.incident_id,
            tenant_id=model.tenant_id,
            agent_id=model.agent_id,
            severity=IncidentSeverity(model.severity),
            status=IncidentStatus(model.status),
            trigger=model.trigger,
            session_ids=_safe_json_list(model.session_ids),
            affected_action_ids=_safe_json_list(model.affected_action_ids),
            affected_resources=_safe_json_list(model.affected_resources),
            blast_radius=_safe_json_dict(model.blast_radius),
            containment_state=_safe_json_dict(model.containment_state),
            rollback_state=_safe_json_dict(model.rollback_state),
            verification_state=_safe_json_dict(model.verification_state),
            created_at=model.created_at,
            resolved_at=model.resolved_at,
        )
