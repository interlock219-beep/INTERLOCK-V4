"""add_emergency_states_table

Revision ID: 0b481f00
Revises: fc5e7844e4dd
Create Date: 2026-09-26 21:11:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0b481f00"
down_revision: str | None = "fc5e7844e4dd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "emergency_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("emergency_deny_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("emergency_allow_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_details", sa.Text(), nullable=True),
        sa.Column("activated_by", sa.String(length=255), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by", sa.String(length=255), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approval_ids", sa.Text(), nullable=True),
        sa.Column("affected_sessions", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index(op.f("ix_emergency_states_tenant_id"), "emergency_states", ["tenant_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_emergency_states_tenant_id"), table_name="emergency_states")
    op.drop_table("emergency_states")
