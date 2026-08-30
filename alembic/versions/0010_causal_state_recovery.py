"""add universal causal state recovery tables

Revision ID: 0010_causal_state_recovery
Revises: 0009_surgical_recovery
Create Date: 2026-08-25 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_causal_state_recovery"
down_revision: str | None = "0009_surgical_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- state_checkpoints table --
    op.create_table(
        "state_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False, server_default="full_state"),
        sa.Column("resource_version", sa.String(length=64), nullable=True),
        sa.Column("state_hash", sa.String(length=255), nullable=True),
        sa.Column("recoverable_fields", sa.Text(), nullable=True),
        sa.Column("version_token", sa.String(length=255), nullable=True),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("transaction_id", sa.String(length=255), nullable=True),
        sa.Column("snapshot_reference", sa.String(length=255), nullable=True),
        sa.Column("object_generation", sa.String(length=64), nullable=True),
        sa.Column("config_revision", sa.String(length=64), nullable=True),
        sa.Column("checkpoint_metadata", sa.Text(), nullable=True),
        sa.Column("checkpoint_hash", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_state_checkpoints_checkpoint_id"), "state_checkpoints", ["checkpoint_id"], unique=True
    )
    op.create_index(
        op.f("ix_state_checkpoints_tenant_id"), "state_checkpoints", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_state_checkpoints_action_id"), "state_checkpoints", ["action_id"], unique=False
    )
    op.create_index(
        op.f("ix_state_checkpoints_resource_id"), "state_checkpoints", ["resource_id"], unique=False
    )

    # -- resource_versions table --
    op.create_table(
        "resource_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("change_origin", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("causal_owner", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("state_hash", sa.String(length=255), nullable=True),
        sa.Column("external_version", sa.String(length=64), nullable=True),
        sa.Column("version_token", sa.String(length=255), nullable=True),
        sa.Column("action_id", sa.String(length=64), nullable=True),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("previous_version_id", sa.String(length=64), nullable=True),
        sa.Column("version_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_resource_versions_version_id"), "resource_versions", ["version_id"], unique=True
    )
    op.create_index(
        op.f("ix_resource_versions_tenant_id"), "resource_versions", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_resource_versions_resource_id"), "resource_versions", ["resource_id"], unique=False
    )
    op.create_index(
        op.f("ix_resource_versions_action_id"), "resource_versions", ["action_id"], unique=False
    )

    # -- state_deltas table --
    op.create_table(
        "state_deltas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delta_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("delta_type", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("before_version_id", sa.String(length=64), nullable=True),
        sa.Column("after_version_id", sa.String(length=64), nullable=True),
        sa.Column("changed_fields", sa.Text(), nullable=True),
        sa.Column("added_fields", sa.Text(), nullable=True),
        sa.Column("removed_fields", sa.Text(), nullable=True),
        sa.Column("before_values", sa.Text(), nullable=True),
        sa.Column("after_values", sa.Text(), nullable=True),
        sa.Column("is_safe_delta", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("delta_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_state_deltas_delta_id"), "state_deltas", ["delta_id"], unique=True
    )
    op.create_index(
        op.f("ix_state_deltas_tenant_id"), "state_deltas", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_state_deltas_resource_id"), "state_deltas", ["resource_id"], unique=False
    )

    # -- ai_changesets table --
    op.create_table(
        "ai_changesets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("changeset_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("root_action_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=False, server_default=""),
        sa.Column("causal_actions", sa.Text(), nullable=True),
        sa.Column("affected_resources", sa.Text(), nullable=True),
        sa.Column("before_references", sa.Text(), nullable=True),
        sa.Column("after_references", sa.Text(), nullable=True),
        sa.Column("current_references", sa.Text(), nullable=True),
        sa.Column("dependency_graph", sa.Text(), nullable=True),
        sa.Column("unrelated_mutations", sa.Text(), nullable=True),
        sa.Column("recoverability", sa.Text(), nullable=True),
        sa.Column("conflicts", sa.Text(), nullable=True),
        sa.Column("unknown_areas", sa.Text(), nullable=True),
        sa.Column("direct_changes", sa.Text(), nullable=True),
        sa.Column("indirect_changes", sa.Text(), nullable=True),
        sa.Column("dependent_changes", sa.Text(), nullable=True),
        sa.Column("external_effects", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_changesets_changeset_id"), "ai_changesets", ["changeset_id"], unique=True
    )
    op.create_index(
        op.f("ix_ai_changesets_tenant_id"), "ai_changesets", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_changesets_incident_id"), "ai_changesets", ["incident_id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_changesets_root_action_id"), "ai_changesets", ["root_action_id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_changesets_correlation_id"), "ai_changesets", ["correlation_id"], unique=False
    )

    # -- causal_state_graphs table --
    op.create_table(
        "causal_state_graphs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("graph_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("root_action_id", sa.String(length=64), nullable=False),
        sa.Column("nodes", sa.Text(), nullable=True),
        sa.Column("edges", sa.Text(), nullable=True),
        sa.Column("subgraph_extractions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_causal_state_graphs_graph_id"), "causal_state_graphs", ["graph_id"], unique=True
    )
    op.create_index(
        op.f("ix_causal_state_graphs_tenant_id"), "causal_state_graphs", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_causal_state_graphs_incident_id"), "causal_state_graphs", ["incident_id"], unique=False
    )
    op.create_index(
        op.f("ix_causal_state_graphs_root_action_id"),
        "causal_state_graphs",
        ["root_action_id"],
        unique=False,
    )

    # -- recovery_confidences table --
    op.create_table(
        "recovery_confidences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("confidence_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column(
            "level", sa.String(length=32), nullable=False, server_default="insufficient_evidence"
        ),
        sa.Column("before_state_available", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("after_state_available", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("current_state_available", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("adapter_support", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("version_match", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("drift_detected", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("conflict_detected", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("dependency_completeness", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("verification_capability", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("evidence_completeness", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("factors", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recovery_confidences_confidence_id"),
        "recovery_confidences",
        ["confidence_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_recovery_confidences_tenant_id"),
        "recovery_confidences",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recovery_confidences_plan_id"),
        "recovery_confidences",
        ["plan_id"],
        unique=False,
    )

    # -- durable_execution_steps table --
    op.create_table(
        "durable_execution_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("execution_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("execution_state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("target_system", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("target_resource", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("compensation_payload", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("verification_passed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("step_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_durable_execution_steps_step_id"),
        "durable_execution_steps",
        ["step_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_durable_execution_steps_plan_id"),
        "durable_execution_steps",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_durable_execution_steps_action_id"),
        "durable_execution_steps",
        ["action_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_durable_execution_steps_tenant_id"),
        "durable_execution_steps",
        ["tenant_id"],
        unique=False,
    )

    # -- recovery_reports table --
    op.create_table(
        "recovery_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=False),
        sa.Column("ai_changes_recovered", sa.Text(), nullable=True),
        sa.Column("ai_changes_failed", sa.Text(), nullable=True),
        sa.Column("unrelated_changes_preserved", sa.Text(), nullable=True),
        sa.Column("manual_recovery_required", sa.Text(), nullable=True),
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="manual_verification_required",
        ),
        sa.Column(
            "confidence_level",
            sa.String(length=32),
            nullable=False,
            server_default="insufficient_evidence",
        ),
        sa.Column("resource_results", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recovery_reports_report_id"), "recovery_reports", ["report_id"], unique=True
    )
    op.create_index(
        op.f("ix_recovery_reports_tenant_id"), "recovery_reports", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_recovery_reports_plan_id"), "recovery_reports", ["plan_id"], unique=False
    )
    op.create_index(
        op.f("ix_recovery_reports_incident_id"), "recovery_reports", ["incident_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recovery_reports_incident_id"), table_name="recovery_reports")
    op.drop_index(op.f("ix_recovery_reports_plan_id"), table_name="recovery_reports")
    op.drop_index(op.f("ix_recovery_reports_tenant_id"), table_name="recovery_reports")
    op.drop_index(op.f("ix_recovery_reports_report_id"), table_name="recovery_reports")
    op.drop_table("recovery_reports")

    op.drop_index(op.f("ix_durable_execution_steps_tenant_id"), table_name="durable_execution_steps")
    op.drop_index(op.f("ix_durable_execution_steps_action_id"), table_name="durable_execution_steps")
    op.drop_index(op.f("ix_durable_execution_steps_plan_id"), table_name="durable_execution_steps")
    op.drop_index(op.f("ix_durable_execution_steps_step_id"), table_name="durable_execution_steps")
    op.drop_table("durable_execution_steps")

    op.drop_index(op.f("ix_recovery_confidences_plan_id"), table_name="recovery_confidences")
    op.drop_index(op.f("ix_recovery_confidences_tenant_id"), table_name="recovery_confidences")
    op.drop_index(op.f("ix_recovery_confidences_confidence_id"), table_name="recovery_confidences")
    op.drop_table("recovery_confidences")

    op.drop_index(op.f("ix_causal_state_graphs_root_action_id"), table_name="causal_state_graphs")
    op.drop_index(op.f("ix_causal_state_graphs_incident_id"), table_name="causal_state_graphs")
    op.drop_index(op.f("ix_causal_state_graphs_tenant_id"), table_name="causal_state_graphs")
    op.drop_index(op.f("ix_causal_state_graphs_graph_id"), table_name="causal_state_graphs")
    op.drop_table("causal_state_graphs")

    op.drop_index(op.f("ix_ai_changesets_correlation_id"), table_name="ai_changesets")
    op.drop_index(op.f("ix_ai_changesets_root_action_id"), table_name="ai_changesets")
    op.drop_index(op.f("ix_ai_changesets_incident_id"), table_name="ai_changesets")
    op.drop_index(op.f("ix_ai_changesets_tenant_id"), table_name="ai_changesets")
    op.drop_index(op.f("ix_ai_changesets_changeset_id"), table_name="ai_changesets")
    op.drop_table("ai_changesets")

    op.drop_index(op.f("ix_state_deltas_resource_id"), table_name="state_deltas")
    op.drop_index(op.f("ix_state_deltas_tenant_id"), table_name="state_deltas")
    op.drop_index(op.f("ix_state_deltas_delta_id"), table_name="state_deltas")
    op.drop_table("state_deltas")

    op.drop_index(op.f("ix_resource_versions_action_id"), table_name="resource_versions")
    op.drop_index(op.f("ix_resource_versions_resource_id"), table_name="resource_versions")
    op.drop_index(op.f("ix_resource_versions_tenant_id"), table_name="resource_versions")
    op.drop_index(op.f("ix_resource_versions_version_id"), table_name="resource_versions")
    op.drop_table("resource_versions")

    op.drop_index(op.f("ix_state_checkpoints_resource_id"), table_name="state_checkpoints")
    op.drop_index(op.f("ix_state_checkpoints_action_id"), table_name="state_checkpoints")
    op.drop_index(op.f("ix_state_checkpoints_tenant_id"), table_name="state_checkpoints")
    op.drop_index(op.f("ix_state_checkpoints_checkpoint_id"), table_name="state_checkpoints")
    op.drop_table("state_checkpoints")
