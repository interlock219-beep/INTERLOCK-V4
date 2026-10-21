"""v6 shared lease and quota coordination backends

Revision ID: b4b471ffc2bd
Revises: a63190d7e268
Create Date: 2026-10-15 17:04:06.764861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4b471ffc2bd'
down_revision: Union[str, Sequence[str], None] = 'a63190d7e268'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the shared coordination tables (runbook §6/§7 backends)."""
    op.create_table(
        "plan_leases",
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("owner", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "fencing_token", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("plan_id"),
    )
    op.create_table(
        "quota_counters",
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "plans_today", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("day_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "active_compensations", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
    )


def downgrade() -> None:
    """Drop the coordination tables (opt-out returns to in-memory stores)."""
    op.drop_table("quota_counters")
    op.drop_table("plan_leases")
