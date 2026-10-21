"""Guarded backfill of pre-V6 model<->migration drift.

Every operation is guarded by fresh inspection so re-runs are no-ops. Newly added
NOT NULL columns are backfilled before tightening (fail-closed: existing rows receive
token_id = row id, tenant_id 'unknown', status 'active', created_at = CURRENT_TIMESTAMP).
execution_tokens.expires_at is RELAXED to nullable to match the model. Uses
batch_alter_table for SQLite compatibility. Creates a single new head.

Revision ID: v6driftbf01
Revises: b4b471ffc2bd
Create Date: proposal (created in candidate tree for validation only)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v6driftbf01"
down_revision = "b4b471ffc2bd"
branch_labels = None
depends_on = None


def _insp() -> sa.Inspector:
    # Fresh inspector per call: avoids stale reflection caches between guarded steps.
    return sa.inspect(op.get_bind())


def _has_col(table: str, name: str) -> bool:
    return name in {c["name"] for c in _insp().get_columns(table)}


def _has_idx(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def upgrade() -> None:
    # ---------------------------------------------------------------- tables --
    if not _insp().has_table("identity_providers"):
        op.create_table(
            "identity_providers",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            sa.Column(
                "provider_type",
                sa.Enum("oidc", "saml", name="provider_type"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(length=255), nullable=True),
            sa.Column("issuer", sa.String(length=255), nullable=False),
            sa.Column("authorization_url", sa.String(length=1024), nullable=False),
            sa.Column("token_url", sa.String(length=1024), nullable=False),
            sa.Column("jwks_uri", sa.String(length=1024), nullable=False),
            sa.Column("client_id", sa.String(length=255), nullable=False),
            sa.Column("client_secret", sa.String(length=255), nullable=False),
            sa.Column("scopes", sa.String(length=512), nullable=False),
            sa.Column("attribute_mapping", sa.Text(), nullable=False),
            sa.Column("saml_sso_url", sa.String(length=1024), nullable=False),
            sa.Column("saml_entity_id", sa.String(length=255), nullable=False),
            sa.Column("saml_x509_cert", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.Enum("active", "inactive", "error", name="provider_status"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _insp().has_table("sso_states"):
        op.create_table(
            "sso_states",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(
                "state_token", sa.String(length=128), nullable=False, unique=True
            ),
            sa.Column("nonce", sa.String(length=128), nullable=False),
            sa.Column(
                "provider_type",
                sa.Enum("oidc", "saml", name="sso_provider_type"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(length=255), nullable=True),
            sa.Column("redirect_uri", sa.String(length=1024), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "pending", "authorized", "failed", "expired",
                    name="sso_state_status",
                ),
                nullable=False,
            ),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        )

    # -------------------------------------------------------------- columns --
    def add_col(table: str, column: sa.Column) -> None:
        if not _has_col(table, column.name):
            op.add_column(table, column)

    add_col("checkout_sessions", sa.Column("tenant_id", sa.String(length=64), nullable=True))
    add_col("checkout_sessions", sa.Column("customer_id", sa.String(length=128), nullable=True))
    add_col("containment_events", sa.Column("affected_session_ids", sa.Text(), nullable=True))
    add_col("containment_events", sa.Column("affected_token_ids", sa.Text(), nullable=True))
    add_col("containment_events", sa.Column("affected_action_ids", sa.Text(), nullable=True))
    add_col("execution_tokens", sa.Column("token_id", sa.String(length=64), nullable=True))
    add_col("execution_tokens", sa.Column("tenant_id", sa.String(length=64), nullable=True))
    add_col("execution_tokens", sa.Column("status", sa.String(length=32), nullable=True))
    add_col("execution_tokens", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    add_col("protected_actions", sa.Column("before_state_snapshot", sa.Text(), nullable=True))
    add_col("recovery_executions", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))

    # --------------------------------------------------- fail-closed backfills
    # (before tightening NOT NULL; no-ops on empty tables)
    op.execute(
        sa.text(
            "UPDATE execution_tokens SET token_id = CAST(id AS VARCHAR) "
            "WHERE token_id IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE execution_tokens SET tenant_id = 'unknown' WHERE tenant_id IS NULL"
        )
    )
    op.execute(
        sa.text("UPDATE execution_tokens SET status = 'active' WHERE status IS NULL")
    )
    op.execute(
        sa.text(
            "UPDATE recovery_executions SET created_at = CURRENT_TIMESTAMP "
            "WHERE created_at IS NULL"
        )
    )

    # --------------------------------------------- tighten / relax (batched) --
    # execution_tokens: 4 adds -> NOT NULL per model; expires_at relaxes to
    # nullable per model (DB was created NOT NULL by a pre-model change).
    with op.batch_alter_table("execution_tokens") as b:
        b.alter_column("token_id", existing_type=sa.String(length=64), nullable=False)
        b.alter_column("tenant_id", existing_type=sa.String(length=64), nullable=False)
        b.alter_column("status", existing_type=sa.String(length=32), nullable=False)
        b.alter_column("expires_at", existing_type=sa.DateTime(), nullable=True)

    with op.batch_alter_table("recovery_executions") as b:
        b.alter_column(
            "created_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )

    # --------------------------------------------------------------- indexes --
    if not _has_idx("identity_providers", "ix_identity_providers_tenant_id"):
        op.create_index(
            "ix_identity_providers_tenant_id", "identity_providers", ["tenant_id"]
        )
    if not _has_idx("sso_states", "ix_sso_states_state_token"):
        op.create_index(
            "ix_sso_states_state_token", "sso_states", ["state_token"], unique=True
        )
    if not _has_idx("sso_states", "ix_sso_states_tenant_id"):
        op.create_index("ix_sso_states_tenant_id", "sso_states", ["tenant_id"])
    if not _has_idx("agent_sessions", "ix_agent_sessions_intent_id"):
        op.create_index("ix_agent_sessions_intent_id", "agent_sessions", ["intent_id"])
    if not _has_idx("checkout_sessions", "ix_checkout_sessions_tenant_id"):
        op.create_index(
            "ix_checkout_sessions_tenant_id", "checkout_sessions", ["tenant_id"]
        )
    if not _has_idx("containment_events", "ix_containment_events_target_authority_id"):
        op.create_index(
            "ix_containment_events_target_authority_id",
            "containment_events",
            ["target_authority_id"],
        )
    if not _has_idx("execution_tokens", "ix_execution_tokens_status"):
        op.create_index("ix_execution_tokens_status", "execution_tokens", ["status"])
    if not _has_idx("execution_tokens", "ix_execution_tokens_tenant_id"):
        op.create_index(
            "ix_execution_tokens_tenant_id", "execution_tokens", ["tenant_id"]
        )
    if not _has_idx("execution_tokens", "ix_execution_tokens_token_id"):
        op.create_index(
            "ix_execution_tokens_token_id",
            "execution_tokens",
            ["token_id"],
            unique=True,
        )
    if not _has_idx("invoices", "ix_invoices_subscription_id"):
        op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])
    if not _has_idx("protected_actions", "ix_protected_actions_actor_user_id"):
        op.create_index(
            "ix_protected_actions_actor_user_id",
            "protected_actions",
            ["actor_user_id"],
        )
    if not _has_idx("subscriptions", "ix_subscriptions_plan_id"):
        op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    if not _has_idx("usage_records", "ix_usage_records_period_end"):
        op.create_index("ix_usage_records_period_end", "usage_records", ["period_end"])
    if not _has_idx("usage_records", "ix_usage_records_period_start"):
        op.create_index(
            "ix_usage_records_period_start", "usage_records", ["period_start"]
        )
    if not _has_idx("webhook_events", "ix_webhook_events_event_type"):
        op.create_index(
            "ix_webhook_events_event_type", "webhook_events", ["event_type"]
        )

    # ------------------------------------------------------ stale index drops --
    for table, name in [
        ("plans", "ix_plans_tier"),
        ("recovery_evidence", "ix_recovery_evidence_idempotency_key"),
        ("usage_records", "ix_usage_records_period"),
        ("user_mfa", "ix_user_mfa_user_id"),
    ]:
        if _has_idx(table, name):
            op.drop_index(name, table_name=table)


def downgrade() -> None:
    # Reverse order. Dropping columns discards data written to them (standard risk).
    # SQLite batch rebuild re-creates reflected indexes; indexes that reference a
    # column about to be dropped MUST be dropped first or the rebuild fails.
    for table, name in [
        ("execution_tokens", "ix_execution_tokens_status"),
        ("execution_tokens", "ix_execution_tokens_tenant_id"),
        ("execution_tokens", "ix_execution_tokens_token_id"),
        ("checkout_sessions", "ix_checkout_sessions_tenant_id"),
    ]:
        if _has_idx(table, name):
            op.drop_index(name, table_name=table)

    with op.batch_alter_table("recovery_executions") as b:
        b.drop_column("created_at")

    with op.batch_alter_table("execution_tokens") as b:
        b.drop_column("token_id")
        b.drop_column("tenant_id")
        b.drop_column("status")
        b.drop_column("revoked_at")
        b.alter_column("expires_at", existing_type=sa.DateTime(), nullable=False)

    for table, name, cols, unique in [
        ("identity_providers", "ix_identity_providers_tenant_id", ["tenant_id"], False),
        ("sso_states", "ix_sso_states_state_token", ["state_token"], True),
        ("sso_states", "ix_sso_states_tenant_id", ["tenant_id"], False),
        ("agent_sessions", "ix_agent_sessions_intent_id", ["intent_id"], False),
        ("checkout_sessions", "ix_checkout_sessions_tenant_id", ["tenant_id"], False),
        (
            "containment_events",
            "ix_containment_events_target_authority_id",
            ["target_authority_id"],
            False,
        ),
        ("execution_tokens", "ix_execution_tokens_status", ["status"], False),
        ("execution_tokens", "ix_execution_tokens_tenant_id", ["tenant_id"], False),
        ("execution_tokens", "ix_execution_tokens_token_id", ["token_id"], True),
        ("invoices", "ix_invoices_subscription_id", ["subscription_id"], False),
        (
            "protected_actions",
            "ix_protected_actions_actor_user_id",
            ["actor_user_id"],
            False,
        ),
        ("subscriptions", "ix_subscriptions_plan_id", ["plan_id"], False),
        ("usage_records", "ix_usage_records_period_end", ["period_end"], False),
        ("usage_records", "ix_usage_records_period_start", ["period_start"], False),
        ("webhook_events", "ix_webhook_events_event_type", ["event_type"], False),
    ]:
        if _has_idx(table, name):
            op.drop_index(name, table_name=table)

    for table in ("identity_providers", "sso_states"):
        if _insp().has_table(table):
            op.drop_table(table)

    with op.batch_alter_table("protected_actions") as b:
        b.drop_column("before_state_snapshot")
    with op.batch_alter_table("containment_events") as b:
        b.drop_column("affected_session_ids")
        b.drop_column("affected_token_ids")
        b.drop_column("affected_action_ids")
    with op.batch_alter_table("checkout_sessions") as b:
        b.drop_column("tenant_id")
        b.drop_column("customer_id")

    # Re-create the four stale indexes (only meaningful on databases that had them).
    for table, name, cols in [
        ("plans", "ix_plans_tier", ["tier"]),
        (
            "recovery_evidence",
            "ix_recovery_evidence_idempotency_key",
            ["idempotency_key"],
        ),
        ("usage_records", "ix_usage_records_period", ["period_start", "period_end"]),
        ("user_mfa", "ix_user_mfa_user_id", ["user_id"]),
    ]:
        if not _has_idx(table, name):
            op.create_index(name, table, cols)
