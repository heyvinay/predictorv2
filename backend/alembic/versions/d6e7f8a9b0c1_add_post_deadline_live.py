"""Add competitions.post_deadline_live release flag.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-11 16:00:00.000000

Admin-controlled release switch for the post-deadline pages (v2.166.0).
Defaults FALSE so the deadline passing no longer auto-opens the V4
dashboard / results / leaderboard — the admin flips it from /admin once
the post-deadline clean-up is done. server_default keeps existing rows
valid without a data migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column(
            "post_deadline_live",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("competitions", "post_deadline_live")
