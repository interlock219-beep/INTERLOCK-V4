"""add billing tables

Revision ID: 0004_add_billing_tables
Revises: 0003_add_tenant_id
Create Date: 2026-08-20 22:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_billing_tables"
down_revision: str | None = "0003_add_tenant_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "tier",
            sa.Enum("FREE", "PRO", "BUSINESS", "ENTERPRISE", name="plan_tier"),
            nullable=False,
        ),
        sa.Column("price_monthly_cents", sa.Integer(), nullable=False),
        sa.Column("price_yearly_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="usd"),
        sa.Column("features", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("limits", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plans_tier", "plans", ["tier"], unique=False)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "PAST_DUE",
                "CANCELED",
                "INCOMPLETE",
                "INCOMPLETE_EXPIRED",
                "TRIALING",
                "UNPAID",
                name="subscription_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "interval",
            sa.Enum("MONTHLY", "YEARLY", name="billing_interval"),
            nullable=False,
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("provider_subscription_id", sa.String(length=128), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"], unique=False)
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"], unique=False)
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"], unique=False)

    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_records_user_id", "usage_records", ["user_id"], unique=False)
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"], unique=False)
    op.create_index(
        "ix_usage_records_resource_type",
        "usage_records",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        "ix_usage_records_period",
        "usage_records",
        ["period_start", "period_end"],
        unique=False,
    )

    op.create_table(
        "checkout_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("provider_session_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("success_url", sa.String(length=512), nullable=False),
        sa.Column("cancel_url", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_checkout_sessions_provider_session_id",
        "checkout_sessions",
        ["provider_session_id"],
        unique=True,
    )
    op.create_index("ix_checkout_sessions_user_id", "checkout_sessions", ["user_id"], unique=False)

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_events_provider_event_id",
        "webhook_events",
        ["provider_event_id"],
        unique=True,
    )
    op.create_index("ix_webhook_events_processed", "webhook_events", ["processed"], unique=False)

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="usd"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_invoice_id", sa.String(length=128), nullable=True, unique=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"], unique=False)
    op.create_index("ix_invoices_status", "invoices", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_user_id", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_webhook_events_processed", table_name="webhook_events")
    op.drop_index("ix_webhook_events_provider_event_id", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index("ix_checkout_sessions_user_id", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_provider_session_id", table_name="checkout_sessions")
    op.drop_table("checkout_sessions")

    op.drop_index("ix_usage_records_period", table_name="usage_records")
    op.drop_index("ix_usage_records_resource_type", table_name="usage_records")
    op.drop_index("ix_usage_records_tenant_id", table_name="usage_records")
    op.drop_index("ix_usage_records_user_id", table_name="usage_records")
    op.drop_table("usage_records")

    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_tenant_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_plans_tier", table_name="plans")
    op.drop_table("plans")

    op.execute("DROP TYPE IF EXISTS plan_tier")
    op.execute("DROP TYPE IF EXISTS subscription_status")
    op.execute("DROP TYPE IF EXISTS billing_interval")
