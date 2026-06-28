"""Add standings_drift_events table (v2.182.0).

Revision ID: 1b2c3d4e5f6a
Revises: 0a1b2c3d4e5f
Create Date: 2026-06-28 02:00:00.000000

Detect-only drift verifier: each row captures a single moment where
our computed group standings disagreed with a trusted external source
(Football-Data primary, ESPN secondary, Wikipedia tertiary fallback).
Admins resolve via /admin — no automatic rewrite of /standings.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "1b2c3d4e5f6a"
down_revision: Union[str, None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enums first — autogenerate skips dependent ENUM creates.
    trusted_source = postgresql.ENUM(
        "FOOTBALL_DATA", "ESPN", "WIKIPEDIA",
        name="trustedsource",
        create_type=False,
    )
    drift_status = postgresql.ENUM(
        "OPEN",
        "DISMISSED_OURS_CORRECT",
        "DISMISSED_TRANSIENT",
        "RESOLVED_VIA_SCORE_EDIT",
        name="drifteventstatus",
        create_type=False,
    )
    op.execute(
        "CREATE TYPE trustedsource AS ENUM "
        "('FOOTBALL_DATA','ESPN','WIKIPEDIA')"
    )
    op.execute(
        "CREATE TYPE drifteventstatus AS ENUM "
        "('OPEN','DISMISSED_OURS_CORRECT','DISMISSED_TRANSIENT','RESOLVED_VIA_SCORE_EDIT')"
    )

    op.create_table(
        "standings_drift_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "competition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("competitions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("trusted_source", trusted_source, nullable=False),
        sa.Column(
            "groups_disagreeing",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            drift_status,
            nullable=False,
            server_default="OPEN",
            index=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("standings_drift_events")
    op.execute("DROP TYPE IF EXISTS drifteventstatus")
    op.execute("DROP TYPE IF EXISTS trustedsource")
