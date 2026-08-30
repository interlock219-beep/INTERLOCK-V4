from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class DiscoveryEventModel(Base):
    __tablename__ = "discovery_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    discovery_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    discovery_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovered", index=True
    )
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    resource_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    finding_severity: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    finding_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
