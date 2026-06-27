"""Add competitions.knockout_scoring_enabled gate flag.

Revision ID: 0a1b2c3d4e5f
Revises: f8a9b0c1d2e3
Create Date: 2026-06-28 00:00:00.000000

Admin-controlled gate for knockout-stage advancement points (v2.181.1).
Defaults FALSE so no advancement payouts settle until the admin flips
the switch from /admin — typically right after the group-stage winner
is announced. Mirrors the group_stage_winner_released pattern
(f8a9b0c1d2e3) and the post_deadline_live pattern (d6e7f8a9b0c1).

server_default keeps existing rows valid without a data migration.
Distinct from group_stage_winner_released by design — that flag gates
the dashboard card + champion broadcast; this flag gates the scoring
engine's advancement-points payout. They typically flip together but
are intentionally separable so an admin can announce the champion
without committing the engine to pay knockout points if the bracket
seeding still needs review.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column(
            "knockout_scoring_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("competitions", "knockout_scoring_enabled")
