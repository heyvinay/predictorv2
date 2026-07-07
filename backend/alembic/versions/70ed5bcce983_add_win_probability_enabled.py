"""add win_probability_enabled

Revision ID: 70ed5bcce983
Revises: c2526e136114
Create Date: 2026-07-07 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '70ed5bcce983'
down_revision: Union[str, None] = 'c2526e136114'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column(
            "win_probability_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("competitions", "win_probability_enabled")
