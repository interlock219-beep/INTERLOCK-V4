"""Add the recovery-credit tables (wallets, append-only ledger, reservations).

All operations are guarded by fresh inspection so re-runs are no-ops. The new
tables are plain creates; downgrade() drops exactly what upgrade() created, so
the round-trip is lossless for this revision.

PostgreSQL note: the ``plans.tier`` native enum gains 'STARTER' (the central
plan registry's Starter tier). SQLite stores the tier as VARCHAR(10), so no
constraint work is needed there. ``ALTER TYPE ... ADD VALUE`` requires
PostgreSQL 12+ when run inside the migration transaction.

Revision ID: cr01addcredits
Revises: v6driftbf01
Create Date: 2026-10-21
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "cr01addcredits"
down_revision = "v6driftbf01"
branch_labels = None
depends_on = None


def _insp() -> sa.Inspector:
    # Fresh inspector per call: avoids stale reflection caches between guarded steps.
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if not _insp().has_table("credit_wallets"):
        op.create_table(
            "credit_wallets",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("allocated", sa.Integer(), nullable=False),
            sa.Column("consumed", sa.Integer(), nullable=False),
            sa.Column("reserved", sa.Integer(), nullable=False),
            sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("is_enforced", sa.Boolean(), nullable=False),
            sa.Column("plan_tier", sa.String(length=32), nullable=False),
            sa.Column("plan_name", sa.String(length=64), nullable=False),
            sa.Column("subscription_id", sa.Uuid(), nullable=True),
            sa.Column(
                "provider_subscription_id", sa.String(length=128), nullable=True
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_credit_wallets_tenant_id",
            "credit_wallets",
            ["tenant_id"],
            unique=True,
        )

    if not _insp().has_table("credit_ledger"):
        op.create_table(
            "credit_ledger",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("balance_after", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=False),
            # The double-charge firewall: allocations are keyed by billing
            # period, consumptions by the recovery plan that earned them.
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("recovery_plan_id", sa.String(length=64), nullable=True),
            sa.Column("subscription_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key"),
        )
        op.create_index(
            "ix_credit_ledger_tenant_id", "credit_ledger", ["tenant_id"]
        )
        op.create_index(
            "ix_credit_ledger_created_at", "credit_ledger", ["created_at"]
        )

    if not _insp().has_table("credit_reservations"):
        op.create_table(
            "credit_reservations",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("recovery_plan_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_credit_reservations_tenant_id",
            "credit_reservations",
            ["tenant_id"],
        )
        op.create_index(
            "ix_credit_reservations_recovery_plan_id",
            "credit_reservations",
            ["recovery_plan_id"],
        )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TYPE plan_tier ADD VALUE IF NOT EXISTS 'STARTER'"))


def downgrade() -> None:
    # Reverse order: indexes first, then tables. Dropping the tables discards
    # wallet/ledger data (standard risk; restore from backups if regressing).
    for table, name in [
        ("credit_reservations", "ix_credit_reservations_recovery_plan_id"),
        ("credit_reservations", "ix_credit_reservations_tenant_id"),
        ("credit_ledger", "ix_credit_ledger_created_at"),
        ("credit_ledger", "ix_credit_ledger_tenant_id"),
        ("credit_wallets", "ix_credit_wallets_tenant_id"),
    ]:
        if name in {i["name"] for i in _insp().get_indexes(table)}:
            op.drop_index(name, table_name=table)

    for table in ("credit_reservations", "credit_ledger", "credit_wallets"):
        if _insp().has_table(table):
            op.drop_table(table)

    # The plan_tier 'STARTER' value is deliberately NOT removed on PostgreSQL:
    # enum values cannot be dropped while rows reference them, and SQLite
    # stores tiers as plain strings (no constraint to reverse).
