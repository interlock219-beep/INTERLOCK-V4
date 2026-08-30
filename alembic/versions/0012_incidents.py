"""add incidents table

Revision ID: 0012_incidents
Revises: 0011_agent_sessions
Create Date: 2026-08-27 22:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_incidents"
down_revision: str | None = "0011_agent_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="detected"),
        sa.Column("trigger", sa.Text(), nullable=False, server_default=""),
        sa.Column("session_ids", sa.Text(), nullable=True),
        sa.Column("affected_action_ids", sa.Text(), nullable=True),
        sa.Column("affected_resources", sa.Text(), nullable=True),
        sa.Column("blast_radius", sa.Text(), nullable=True),
        sa.Column("containment_state", sa.Text(), nullable=True),
        sa.Column("rollback_state", sa.Text(), nullable=True),
        sa.Column("verification_state", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_incidents_incident_id"), "incidents", ["incident_id"], unique=True
    )
    op.create_index(
        op.f("ix_incidents_tenant_id"), "incidents", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_incidents_agent_id"), "incidents", ["agent_id"], unique=False
    )
    op.create_index(
        op.f("ix_incidents_status"), "incidents", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_agent_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_tenant_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_incident_id"), table_name="incidents")
    op.drop_table("incidents")
