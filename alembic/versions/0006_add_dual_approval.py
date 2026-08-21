"""add dual approval and revocation columns

Revision ID: 0006_add_dual_approval
Revises: 0005_add_account_lockout
Create Date: 2026-08-21 10:30:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_add_dual_approval"
down_revision: str | None = "0005_add_account_lockout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("approval_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "approval_requests",
        sa.Column("required_approvers", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("approval_requests", "required_approvers")
    op.drop_column("approval_requests", "approval_count")
