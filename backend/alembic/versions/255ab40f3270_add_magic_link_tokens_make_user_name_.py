"""add magic link tokens make user name nullable

Revision ID: 255ab40f3270
Revises: 5a8c1e2f3b09
Create Date: 2026-05-24 22:38:29.482938

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


# revision identifiers, used by Alembic.
# Re-chained from the original `5a8c1e2f3b09` (main head when this
# migration was authored) to `8d9e0f1a2b66` (the feat/sheets-overview
# chain head) at cherry-pick time, so the alembic graph stays linear
# on this branch.
revision: str = "255ab40f3270"
down_revision: Union[str, None] = "8d9e0f1a2b66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add magic_link_tokens table and make users.name nullable."""
    op.create_table(
        "magic_link_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_magic_link_tokens_token_hash",
        "magic_link_tokens",
        ["token_hash"],
        unique=False,
    )
    op.create_index(
        "ix_magic_link_tokens_user_id",
        "magic_link_tokens",
        ["user_id"],
        unique=False,
    )
    op.alter_column(
        "users",
        "name",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )


def downgrade() -> None:
    """Revert magic_link_tokens + users.name nullable change."""
    op.alter_column(
        "users",
        "name",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.drop_index("ix_magic_link_tokens_user_id", table_name="magic_link_tokens")
    op.drop_index("ix_magic_link_tokens_token_hash", table_name="magic_link_tokens")
    op.drop_table("magic_link_tokens")
