"""Add profile + payment fields to users

Adds the onboarding profile fields: employer (native enum), company_contact,
and paid_to. All nullable so existing rows (and Google sign-ups) back-fill
rather than break; mandatory-ness is enforced by the onboarding gate + API
validators, not DB constraints.

Revision ID: 9a1b2c3d4e5f
Revises: 8081fc184d75
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9a1b2c3d4e5f'
down_revision: Union[str, None] = '8081fc184d75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Native PG enum; member NAMES are the stored values (mirrors authprovider).
employer_enum = postgresql.ENUM('ATLAS', 'JMFA', 'NEITHER', name='employer')


def upgrade() -> None:
    """Create the employer enum type and add the three nullable columns."""
    employer_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('users', sa.Column('employer', employer_enum, nullable=True))
    op.add_column('users', sa.Column('company_contact', sa.String(), nullable=True))
    op.add_column('users', sa.Column('paid_to', sa.String(), nullable=True))


def downgrade() -> None:
    """Drop the columns then the enum type."""
    op.drop_column('users', 'paid_to')
    op.drop_column('users', 'company_contact')
    op.drop_column('users', 'employer')
    employer_enum.drop(op.get_bind(), checkfirst=True)
