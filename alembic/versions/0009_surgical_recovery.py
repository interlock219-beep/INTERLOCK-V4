"""add surgical recovery tables and extend existing tables

Revision ID: 0009_surgical_recovery
Revises: 0008_agent_control_plane
Create Date: 2026-08-24 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_surgical_recovery"
down_revision: str | None = "0008_agent_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- Extend protected_actions table --
    op.add_column(
        "protected_actions",
        sa.Column("workflow_step", sa.Integer(), nullable=True),
    )
    op.add_column(
        "protected_actions",
        sa.Column("execution_depth", sa.Integer(), nullable=True),
    )
    op.add_column(
        "protected_actions",
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "protected_actions",
        sa.Column("approval_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "protected_actions",
        sa.Column("recovery_plan_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_protected_actions_recovery_plan_id"),
        "protected_actions",
        ["recovery_plan_id"],
        unique=False,
    )

    # -- Extend recovery_plans table --
    op.add_column(
        "recovery_plans",
        sa.Column("plan_version", sa.String(length=32), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("plan_hash", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("topological_order", sa.Text(), nullable=True),
    )
    op.add_column(
        "recovery_plans",
        sa.Column(
            "dependency_graph_reference", sa.String(length=255), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("execution_status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "recovery_plans",
        sa.Column(
            "approval_policy", sa.String(length=32), nullable=False, server_default="single_approval"
        ),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("approval_threshold", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("stop_conditions", sa.Text(), nullable=True),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("compensation_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("incident_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("root_action_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("affected_action_ids", sa.Text(), nullable=True),
    )

    # -- Create recovery_evidence table --
    op.create_table(
        "recovery_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("authority_grant_id", sa.String(length=64), nullable=True),
        sa.Column("parent_action_id", sa.String(length=64), nullable=True),
        sa.Column("root_action_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=True),
        sa.Column("target_system", sa.String(length=255), nullable=False),
        sa.Column("target_resource", sa.String(length=255), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("before_state_reference", sa.String(length=255), nullable=True),
        sa.Column("after_state_reference", sa.String(length=255), nullable=True),
        sa.Column("request_payload_reference", sa.String(length=255), nullable=True),
        sa.Column("response_payload_reference", sa.String(length=255), nullable=True),
        sa.Column("compensation_payload", sa.Text(), nullable=True),
        sa.Column(
            "compensation_type",
            sa.String(length=32),
            nullable=False,
            server_default="reverse_operation",
        ),
        sa.Column(
            "recovery_adapter_type",
            sa.String(length=32),
            nullable=False,
            server_default="unsupported",
        ),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("dependency_edges", sa.Text(), nullable=True),
        sa.Column(
            "reversibility_classification",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("state_version", sa.String(length=64), nullable=True),
        sa.Column("state_hash", sa.String(length=255), nullable=True),
        sa.Column("resource_version", sa.String(length=64), nullable=True),
        sa.Column("verification_requirements", sa.Text(), nullable=True),
        sa.Column("recovery_metadata", sa.Text(), nullable=True),
        sa.Column("evidence_hash", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "adapter_capability",
            sa.String(length=32),
            nullable=False,
            server_default="unsupported",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recovery_evidence_evidence_id"),
        "recovery_evidence",
        ["evidence_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_recovery_evidence_action_id"),
        "recovery_evidence",
        ["action_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_evidence_tenant_id"),
        "recovery_evidence",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_evidence_parent_action_id"),
        "recovery_evidence",
        ["parent_action_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_evidence_root_action_id"),
        "recovery_evidence",
        ["root_action_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_evidence_correlation_id"),
        "recovery_evidence",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_evidence_idempotency_key"),
        "recovery_evidence",
        ["idempotency_key"],
        unique=False,
    )

    # -- Create recovery_executions table --
    op.create_table(
        "recovery_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("compensation_type", sa.String(length=32), nullable=False),
        sa.Column("target_system", sa.String(length=255), nullable=False),
        sa.Column("target_resource", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "execution_order", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "execution_state",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("external_outcome", sa.String(length=255), nullable=True),
        sa.Column(
            "verification_passed",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("verification_details", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recovery_executions_execution_id"),
        "recovery_executions",
        ["execution_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_recovery_executions_plan_id"),
        "recovery_executions",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_executions_action_id"),
        "recovery_executions",
        ["action_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_executions_tenant_id"),
        "recovery_executions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_executions_idempotency_key"),
        "recovery_executions",
        ["idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    # Drop recovery_executions table
    op.drop_index(
        op.f("ix_recovery_executions_idempotency_key"), table_name="recovery_executions"
    )
    op.drop_index(
        op.f("ix_recovery_executions_tenant_id"), table_name="recovery_executions"
    )
    op.drop_index(
        op.f("ix_recovery_executions_action_id"), table_name="recovery_executions"
    )
    op.drop_index(
        op.f("ix_recovery_executions_plan_id"), table_name="recovery_executions"
    )
    op.drop_index(
        op.f("ix_recovery_executions_execution_id"), table_name="recovery_executions"
    )
    op.drop_table("recovery_executions")

    # Drop recovery_evidence table
    op.drop_index(
        op.f("ix_recovery_evidence_idempotency_key"), table_name="recovery_evidence"
    )
    op.drop_index(
        op.f("ix_recovery_evidence_correlation_id"), table_name="recovery_evidence"
    )
    op.drop_index(
        op.f("ix_recovery_evidence_root_action_id"), table_name="recovery_evidence"
    )
    op.drop_index(
        op.f("ix_recovery_evidence_parent_action_id"), table_name="recovery_evidence"
    )
    op.drop_index(op.f("ix_recovery_evidence_tenant_id"), table_name="recovery_evidence")
    op.drop_index(op.f("ix_recovery_evidence_action_id"), table_name="recovery_evidence")
    op.drop_index(op.f("ix_recovery_evidence_evidence_id"), table_name="recovery_evidence")
    op.drop_table("recovery_evidence")

    # Remove columns from recovery_plans table
    op.drop_column("recovery_plans", "affected_action_ids")
    op.drop_column("recovery_plans", "root_action_id")
    op.drop_column("recovery_plans", "incident_id")
    op.drop_column("recovery_plans", "compensation_summary")
    op.drop_column("recovery_plans", "stop_conditions")
    op.drop_column("recovery_plans", "approval_threshold")
    op.drop_column("recovery_plans", "approval_policy")
    op.drop_column("recovery_plans", "execution_status")
    op.drop_column("recovery_plans", "dependency_graph_reference")
    op.drop_column("recovery_plans", "topological_order")
    op.drop_column("recovery_plans", "plan_hash")
    op.drop_column("recovery_plans", "plan_version")

    # Remove columns from protected_actions table
    op.drop_index(
        op.f("ix_protected_actions_recovery_plan_id"), table_name="protected_actions"
    )
    op.drop_column("protected_actions", "recovery_plan_id")
    op.drop_column("protected_actions", "approval_deadline")
    op.drop_column("protected_actions", "requires_approval")
    op.drop_column("protected_actions", "execution_depth")
    op.drop_column("protected_actions", "workflow_step")
