from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class EmergencyStateModel(Base):
    __tablename__ = "emergency_states"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)
    emergency_deny_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_allow_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_sessions: Mapped[str | None] = mapped_column(Text, nullable=True)
