from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class IncidentModel(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="detected", index=True)
    trigger: Mapped[str] = mapped_column(Text, nullable=False, default="")
    session_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_action_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_resources: Mapped[str | None] = mapped_column(Text, nullable=True)
    blast_radius: Mapped[str | None] = mapped_column(Text, nullable=True)
    containment_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
