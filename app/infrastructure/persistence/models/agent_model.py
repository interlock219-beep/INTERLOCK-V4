from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.database import Base


class AgentModel(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    parent_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    trust_level: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_classification: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0")
    creator: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    registration_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", index=True
    )
    root_human_sponsor: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    connected_tools: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_metadata: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
