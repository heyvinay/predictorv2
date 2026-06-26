"""Add competitions.group_stage_winner_released release flag.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-26 12:00:00.000000

Admin-controlled release switch for the Group Stage Winner card +
broadcast (v2.181.0). Defaults FALSE so the card stays hidden until
the admin flips it from /admin at 7pm Malta on Sunday 28 June 2026.
server_default keeps existing rows valid without a data migration.
Mirrors the post_deadline_live pattern (v2.166.0).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column(
            "group_stage_winner_released",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("competitions", "group_stage_winner_released")
