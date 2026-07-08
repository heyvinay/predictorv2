"""Remove what-if bracket simulator trivia gate + daily run cap columns.

Revision ID: cf1e325b1eac
Revises: 70ed5bcce983
Create Date: 2026-07-08 00:00:00.000000

Removes the one-time trivia unlock and daily run-cap columns added in
2d3e4f5a6b7c — the gate and the run limit were removed from the
product (see app/services/simulator.py). `competitions.simulator_enabled`
(the admin master switch) is UNCHANGED and stays — the simulator is
still admin-gated per competition, just no longer per-user trivia/cap
gated on top of that.

- `users.simulator_unlocked`
- `users.simulator_runs_used`
- `users.simulator_runs_reset_at`
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "cf1e325b1eac"
down_revision: Union[str, None] = "70ed5bcce983"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "simulator_runs_reset_at")
    op.drop_column("users", "simulator_runs_used")
    op.drop_column("users", "simulator_unlocked")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "simulator_unlocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "simulator_runs_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "simulator_runs_reset_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
