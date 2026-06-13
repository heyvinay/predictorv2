"""Add users.last_seen_at + backfill from audit_events/created_at.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-06-13

v2.176.0 — engagement signal foundation. The `last_seen_at` column is
updated by `get_current_user` on each authenticated request (throttled
to once per 5 minutes per user) and feeds the broadcast Pool Ghost /
Lapsing cohorts plus future engagement surfaces.

Backfill strategy: for each existing user, set last_seen_at to the
greater of (MAX(audit_events.created_at) for events they actor on) and
their own `created_at`. This gives every user a defensible starting
value before the dependency starts writing.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable last_seen_at column and backfill."""
    op.add_column(
        "users",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Backfill: MAX(audit_events.created_at WHERE actor_user_id=u.id)
    # falling back to users.created_at when the user has no audit history.
    # COALESCE ensures every row gets a non-null seed value; the column
    # itself stays nullable so a future "never seen" user can still be
    # represented if we ever bulk-create accounts.
    op.execute(
        """
        UPDATE users u
        SET last_seen_at = GREATEST(
            COALESCE(
                (SELECT MAX(ae.created_at)
                   FROM audit_events ae
                  WHERE ae.actor_user_id = u.id),
                u.created_at
            ),
            u.created_at
        )
        """
    )


def downgrade() -> None:
    """Drop last_seen_at."""
    op.drop_column("users", "last_seen_at")
