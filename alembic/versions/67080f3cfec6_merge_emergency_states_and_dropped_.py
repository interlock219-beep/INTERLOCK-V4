"""Merge emergency states and dropped-tables heads

Revision ID: 67080f3cfec6
Revises: 0b481f00, 3cebbede5768
Create Date: 2026-10-15 07:50:58.332041

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '67080f3cfec6'
down_revision: str | Sequence[str] | None = ('0b481f00', '3cebbede5768')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
