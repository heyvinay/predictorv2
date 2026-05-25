"""merge_main_into_sheets_after_branch

Revision ID: 8081fc184d75
Revises: 255ab40f3270, 5a8c1e2f3b09
Create Date: 2026-05-25 14:39:24.938153

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '8081fc184d75'
down_revision: Union[str, None] = ('255ab40f3270', '5a8c1e2f3b09')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
