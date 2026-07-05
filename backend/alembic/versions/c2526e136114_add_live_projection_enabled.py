"""add live_projection_enabled

Revision ID: c2526e136114
Revises: 2d3e4f5a6b7c
Create Date: 2026-07-05 23:17:02.723770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c2526e136114'
down_revision: Union[str, None] = '2d3e4f5a6b7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column(
            "live_projection_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("competitions", "live_projection_enabled")
