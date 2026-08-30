"""add agent sessions table

Revision ID: 0011_agent_sessions
Revises: 0010_causal_state_recovery
Create Date: 2026-08-27 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_agent_sessions"
down_revision: str | None = "0010_causal_state_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("intent_id", sa.String(length=64), nullable=True),
        sa.Column("policy_version", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("risk_level", sa.String(length=32), nullable=False, server_default="low"),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("parent_session_id", sa.String(length=64), nullable=True),
        sa.Column("session_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_sessions_session_id"), "agent_sessions", ["session_id"], unique=True
    )
    op.create_index(
        op.f("ix_agent_sessions_tenant_id"), "agent_sessions", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_agent_sessions_agent_id"), "agent_sessions", ["agent_id"], unique=False
    )
    op.create_index(
        op.f("ix_agent_sessions_status"), "agent_sessions", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_agent_sessions_correlation_id"), "agent_sessions", ["correlation_id"], unique=False
    )
    op.create_index(
        op.f("ix_agent_sessions_parent_session_id"), "agent_sessions", ["parent_session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_sessions_parent_session_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_correlation_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_status"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_agent_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_tenant_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_session_id"), table_name="agent_sessions")
    op.drop_table("agent_sessions")
