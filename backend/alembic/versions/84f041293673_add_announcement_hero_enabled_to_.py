"""add announcement_hero_enabled to competition

Revision ID: 84f041293673
Revises: 1b2c3d4e5f6a
Create Date: 2026-07-01 10:19:01.162128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '84f041293673'
down_revision: Union[str, None] = '1b2c3d4e5f6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'competitions',
        sa.Column('announcement_hero_enabled', sa.Boolean(), nullable=False,
                  server_default=sa.text('true'))
    )


def downgrade() -> None:
    op.drop_column('competitions', 'announcement_hero_enabled')
