"""Add audit_events table for system-wide audit logging.

Revision ID: 6a7b8c9d0e33
Revises: 5f6a9b0c1d22
Create Date: 2026-05-16 19:30:00.000000

Adds the `audit_events` table. This is the unified, append-only audit log
for all user-attributable actions (login, register, entry mutations,
admin settings changes, etc.). Required for the prize-money integrity
guarantee: every state change must be reconstructable from the log.

The existing `predictionphase` enum is referenced via PgEnum with
create_type=False (the standard pattern in this codebase — sa.Enum
silently drops `create_type` for postgres-specific kwargs).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "6a7b8c9d0e33"
down_revision: Union[str, None] = "5f6a9b0c1d22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "actor_role",
            PgEnum("USER", "ADMIN", "SYSTEM", name="actorrole", create_type=False),
            nullable=False,
        ),
        sa.Column("subject_type", sa.String(length=32), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("event_metadata", JSONB(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_audit_event_actor"
        ),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index(
        "ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"]
    )
    op.create_index("ix_audit_events_subject_type", "audit_events", ["subject_type"])
    op.create_index("ix_audit_events_subject_id", "audit_events", ["subject_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_subject_id", table_name="audit_events")
    op.drop_index("ix_audit_events_subject_type", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_table("audit_events")
