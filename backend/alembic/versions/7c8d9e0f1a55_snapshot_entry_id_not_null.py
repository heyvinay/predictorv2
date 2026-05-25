"""Task D — make leaderboard_snapshots.entry_id NOT NULL.

Revision ID: 7c8d9e0f1a55
Revises: 6a7b8c9d0e33
Create Date: 2026-05-16 22:30:00.000000

Task A landed the `entry_id` column on `leaderboard_snapshots` as nullable
because the snapshot service was still user-keyed at that point. Task D
rewrites the snapshot service to write entry-keyed rows, so the column
can now be required.

Greenfield: no production data, and any pre-Task-D snapshot rows would
have a null entry_id. Those rows are deleted before the NOT NULL flip so
the constraint can be applied safely.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7c8d9e0f1a55"
down_revision: Union[str, None] = "6a7b8c9d0e33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Any snapshot row without an entry_id pre-dates Task D's entry-keyed
    # snapshot writes. Delete them so the NOT NULL constraint can be
    # applied. Greenfield: no production data depends on these rows.
    op.execute(
        "DELETE FROM leaderboard_snapshots WHERE entry_id IS NULL"
    )
    op.alter_column(
        "leaderboard_snapshots",
        "entry_id",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "leaderboard_snapshots",
        "entry_id",
        nullable=True,
    )
