"""add_authority_grant_jit_and_one_shot_columns

Revision ID: fc5e7844e4dd
Revises: 0013_add_api_keys
Create Date: 2026-09-24 18:46:28.804956

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc5e7844e4dd'
down_revision: Union[str, Sequence[str], None] = '0013_add_api_keys'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("authority_grants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_jit", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("jit_created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("jit_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("jit_consumed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("one_shot", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    with op.batch_alter_table("authority_grants", schema=None) as batch_op:
        batch_op.alter_column("is_jit", server_default=None)
        batch_op.alter_column("jit_created_at", server_default=None)
        batch_op.alter_column("jit_expires_at", server_default=None)
        batch_op.alter_column("jit_consumed_at", server_default=None)
        batch_op.alter_column("one_shot", server_default=None)
        batch_op.alter_column("usage_count", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("authority_grants", schema=None) as batch_op:
        batch_op.drop_column("usage_count")
        batch_op.drop_column("one_shot")
        batch_op.drop_column("jit_consumed_at")
        batch_op.drop_column("jit_expires_at")
        batch_op.drop_column("jit_created_at")
        batch_op.drop_column("is_jit")
