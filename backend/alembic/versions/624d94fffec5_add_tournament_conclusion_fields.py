"""add tournament conclusion fields

Revision ID: 624d94fffec5
Revises: cf1e325b1eac
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '624d94fffec5'
down_revision: Union[str, None] = 'cf1e325b1eac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column(
            "tournament_concluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "final_match_narrative",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("competitions", "final_match_narrative")
    op.drop_column("competitions", "tournament_concluded")
