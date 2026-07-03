"""Add what-if bracket simulator gating columns.

Revision ID: 2d3e4f5a6b7c
Revises: 84f041293673
Create Date: 2026-07-03 00:00:00.000000

Gating layer for the what-if bracket simulator: a one-time game-show
trivia unlock (permanent per user), a daily cap of committed runs, and
an admin master switch. Admins bypass the unlock + cap entirely and
retain full access even when the master switch is off; admin usage is
still counted + audited, just uncapped (see app/services/simulator.py).

- `users.simulator_unlocked` — flips true forever once a user answers
  the trivia challenge correctly within the time limit. Defaults false
  so existing users start locked.
- `users.simulator_runs_used` — committed-run counter for the current
  UTC day. Defaults 0.
- `users.simulator_runs_reset_at` — UTC timestamp of the last daily
  reset; nullable (never reset yet). Compared against "today" in
  services.simulator._apply_daily_reset.
- `competitions.simulator_enabled` — admin master switch. Defaults
  false so the simulator stays off until an admin opts in.

server_default on every boolean/int column keeps existing rows valid
without a data migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2d3e4f5a6b7c"
down_revision: Union[str, None] = "84f041293673"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.add_column(
        "competitions",
        sa.Column(
            "simulator_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("competitions", "simulator_enabled")
    op.drop_column("users", "simulator_runs_reset_at")
    op.drop_column("users", "simulator_runs_used")
    op.drop_column("users", "simulator_unlocked")
