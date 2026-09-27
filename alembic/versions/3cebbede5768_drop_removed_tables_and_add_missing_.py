"""drop_removed_tables_and_add_missing_column

Revision ID: 3cebbede5768
Revises: fc5e7844e4dd
Create Date: 2026-09-24 19:23:36.571773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3cebbede5768'
down_revision: Union[str, Sequence[str], None] = 'fc5e7844e4dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("protected_actions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("after_state_snapshot", sa.Text(), nullable=True))
    for table_name in (
        "state_deltas",
        "state_checkpoints",
        "durable_execution_steps",
        "recovery_reports",
        "ai_changesets",
        "causal_state_graphs",
        "recovery_confidences",
        "resource_versions",
    ):
        op.drop_table(table_name)


def downgrade() -> None:
    """Downgrade schema."""
    pass
