"""v6 durable execution write_fence

Revision ID: a63190d7e268
Revises: 67080f3cfec6
Create Date: 2026-10-15 15:59:02.175900

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a63190d7e268'
down_revision: Union[str, Sequence[str], None] = '67080f3cfec6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the monotonic durable write fence (additive, backfilled to 0).

    Guarded: revision 3cebbede5768 drops ``durable_execution_steps`` during
    its own upgrade, and on fresh databases the table is re-created by
    ``Base.metadata.create_all`` at app startup (the pre-existing heal
    pattern for eight causal-state tables). The column is therefore added
    only when the table exists and lacks it, keeping ``alembic upgrade
    head`` green on every path.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "durable_execution_steps" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("durable_execution_steps")}
    if "write_fence" in columns:
        return
    op.add_column(
        "durable_execution_steps",
        sa.Column(
            "write_fence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Drop the write fence (fence state itself is not needed to read rows)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "durable_execution_steps" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("durable_execution_steps")}
    if "write_fence" not in columns:
        return
    op.drop_column("durable_execution_steps", "write_fence")
