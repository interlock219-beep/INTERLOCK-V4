"""create agent control plane tables

Revision ID: 0008_agent_control_plane
Revises: 0007_add_mfa_and_sessions
Create Date: 2026-08-23 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_agent_control_plane"
down_revision: str | None = "0007_add_mfa_and_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("parent_agent_id", sa.String(length=255), nullable=True),
        sa.Column("agent_type", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("trust_level", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column(
            "risk_classification",
            sa.String(length=32),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("environment", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("version", sa.String(length=64), nullable=False, server_default="1.0"),
        sa.Column("creator", sa.String(length=255), nullable=True),
        sa.Column(
            "registration_method",
            sa.String(length=32),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("root_human_sponsor", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_tools", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agents_agent_id"), "agents", ["agent_id"], unique=True)
    op.create_index(op.f("ix_agents_tenant_id"), "agents", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_agents_status"), "agents", ["status"], unique=False)
    op.create_index(op.f("ix_agents_parent_agent_id"), "agents", ["parent_agent_id"], unique=False)
    op.create_index(op.f("ix_agents_owner_user_id"), "agents", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_agents_creator"), "agents", ["creator"], unique=False)
    op.create_index(
        op.f("ix_agents_registration_method"),
        "agents",
        ["registration_method"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agents_root_human_sponsor"),
        "agents",
        ["root_human_sponsor"],
        unique=False,
    )

    op.create_table(
        "authority_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("grant_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("grantor_agent_id", sa.String(length=255), nullable=False),
        sa.Column("grantee_agent_id", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delegation_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parent_authority_id", sa.String(length=64), nullable=True),
        sa.Column("root_authority_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_authority_grants_grant_id"), "authority_grants", ["grant_id"], unique=True
    )
    op.create_index(
        op.f("ix_authority_grants_tenant_id"), "authority_grants", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_authority_grants_grantee_agent_id"),
        "authority_grants",
        ["grantee_agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_authority_grants_grantor_agent_id"),
        "authority_grants",
        ["grantor_agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_authority_grants_resource"), "authority_grants", ["resource"], unique=False
    )
    op.create_index(
        op.f("ix_authority_grants_status"), "authority_grants", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_authority_grants_expires_at"), "authority_grants", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_authority_grants_parent_authority_id"),
        "authority_grants",
        ["parent_authority_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_authority_grants_root_authority_id"),
        "authority_grants",
        ["root_authority_id"],
        unique=False,
    )

    op.create_table(
        "protected_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("authority_grant_id", sa.String(length=64), nullable=True),
        sa.Column("tool", sa.String(length=255), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("policy_version", sa.String(length=32), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("parent_action_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_id", sa.String(length=64), nullable=True),
        sa.Column("reversibility", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("before_state_ref", sa.String(length=255), nullable=True),
        sa.Column("after_state_ref", sa.String(length=255), nullable=True),
        sa.Column("tool_arguments", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("decision_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_protected_actions_action_id"), "protected_actions", ["action_id"], unique=True
    )
    op.create_index(
        op.f("ix_protected_actions_tenant_id"), "protected_actions", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_protected_actions_agent_id"), "protected_actions", ["agent_id"], unique=False
    )
    op.create_index(op.f("ix_protected_actions_tool"), "protected_actions", ["tool"], unique=False)
    op.create_index(
        op.f("ix_protected_actions_resource"), "protected_actions", ["resource"], unique=False
    )
    op.create_index(
        op.f("ix_protected_actions_action_type"), "protected_actions", ["action_type"], unique=False
    )
    op.create_index(
        op.f("ix_protected_actions_status"), "protected_actions", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_protected_actions_correlation_id"),
        "protected_actions",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_protected_actions_parent_action_id"),
        "protected_actions",
        ["parent_action_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_protected_actions_workflow_id"), "protected_actions", ["workflow_id"], unique=False
    )
    op.create_index(
        op.f("ix_protected_actions_authority_grant_id"),
        "protected_actions",
        ["authority_grant_id"],
        unique=False,
    )

    op.create_table(
        "containment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("containment_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("target_agent_id", sa.String(length=255), nullable=False),
        sa.Column("target_authority_id", sa.String(length=64), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("initiated_by", sa.String(length=255), nullable=False),
        sa.Column("authorized_by", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("affected_agent_ids", sa.Text(), nullable=True),
        sa.Column("affected_authority_ids", sa.Text(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("result_details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_containment_events_containment_id"),
        "containment_events",
        ["containment_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_containment_events_tenant_id"), "containment_events", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_containment_events_target_agent_id"),
        "containment_events",
        ["target_agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_containment_events_status"), "containment_events", ["status"], unique=False
    )

    op.create_table(
        "recovery_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("incident_action_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("outcome", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("simulation_result", sa.Text(), nullable=True),
        sa.Column("steps", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("executed_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recovery_plans_plan_id"), "recovery_plans", ["plan_id"], unique=True)
    op.create_index(
        op.f("ix_recovery_plans_tenant_id"), "recovery_plans", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_recovery_plans_incident_action_id"),
        "recovery_plans",
        ["incident_action_id"],
        unique=False,
    )
    op.create_index(op.f("ix_recovery_plans_status"), "recovery_plans", ["status"], unique=False)

    op.create_table(
        "discovery_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("discovery_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "discovery_status", sa.String(length=32), nullable=False, server_default="discovered"
        ),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("resource_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("resource_metadata", sa.Text(), nullable=True),
        sa.Column("finding_severity", sa.String(length=32), nullable=False, server_default="info"),
        sa.Column("finding_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_discovery_events_discovery_id"), "discovery_events", ["discovery_id"], unique=True
    )
    op.create_index(
        op.f("ix_discovery_events_tenant_id"), "discovery_events", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_discovery_events_source"), "discovery_events", ["source"], unique=False
    )
    op.create_index(
        op.f("ix_discovery_events_discovery_status"),
        "discovery_events",
        ["discovery_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_events_agent_id"), "discovery_events", ["agent_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_discovery_events_agent_id"), table_name="discovery_events")
    op.drop_index(op.f("ix_discovery_events_discovery_status"), table_name="discovery_events")
    op.drop_index(op.f("ix_discovery_events_source"), table_name="discovery_events")
    op.drop_index(op.f("ix_discovery_events_tenant_id"), table_name="discovery_events")
    op.drop_index(op.f("ix_discovery_events_discovery_id"), table_name="discovery_events")
    op.drop_table("discovery_events")

    op.drop_index(op.f("ix_recovery_plans_status"), table_name="recovery_plans")
    op.drop_index(op.f("ix_recovery_plans_incident_action_id"), table_name="recovery_plans")
    op.drop_index(op.f("ix_recovery_plans_tenant_id"), table_name="recovery_plans")
    op.drop_index(op.f("ix_recovery_plans_plan_id"), table_name="recovery_plans")
    op.drop_table("recovery_plans")

    op.drop_index(op.f("ix_containment_events_status"), table_name="containment_events")
    op.drop_index(op.f("ix_containment_events_target_agent_id"), table_name="containment_events")
    op.drop_index(op.f("ix_containment_events_tenant_id"), table_name="containment_events")
    op.drop_index(op.f("ix_containment_events_containment_id"), table_name="containment_events")
    op.drop_table("containment_events")

    op.drop_index(op.f("ix_protected_actions_authority_grant_id"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_workflow_id"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_parent_action_id"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_correlation_id"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_status"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_action_type"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_resource"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_tool"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_agent_id"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_tenant_id"), table_name="protected_actions")
    op.drop_index(op.f("ix_protected_actions_action_id"), table_name="protected_actions")
    op.drop_table("protected_actions")

    op.drop_index(op.f("ix_authority_grants_root_authority_id"), table_name="authority_grants")
    op.drop_index(op.f("ix_authority_grants_parent_authority_id"), table_name="authority_grants")
    op.drop_index(op.f("ix_authority_grants_expires_at"), table_name="authority_grants")
    op.drop_index(op.f("ix_authority_grants_status"), table_name="authority_grants")
    op.drop_index(op.f("ix_authority_grants_resource"), table_name="authority_grants")
    op.drop_index(op.f("ix_authority_grants_grantor_agent_id"), table_name="authority_grants")
    op.drop_index(op.f("ix_authority_grants_grantee_agent_id"), table_name="authority_grants")
    op.drop_index(op.f("ix_authority_grants_tenant_id"), table_name="authority_grants")
    op.drop_index(op.f("ix_authority_grants_grant_id"), table_name="authority_grants")
    op.drop_table("authority_grants")

    op.drop_index(op.f("ix_agents_owner_user_id"), table_name="agents")
    op.drop_index(op.f("ix_agents_parent_agent_id"), table_name="agents")
    op.drop_index(op.f("ix_agents_status"), table_name="agents")
    op.drop_index(op.f("ix_agents_tenant_id"), table_name="agents")
    op.drop_index(op.f("ix_agents_agent_id"), table_name="agents")
    op.drop_table("agents")
