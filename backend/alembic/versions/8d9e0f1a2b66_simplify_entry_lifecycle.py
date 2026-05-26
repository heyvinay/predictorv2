"""Simplify entry lifecycle — collapse status enum to 3 values.

Revision ID: 8d9e0f1a2b66
Revises: 7c8d9e0f1a55
Create Date: 2026-05-21 12:00:00.000000

Reduces `entrystatus` enum from 6 → 3 values:

    OLD: draft, ready, submitted, locked, withdrawn, disabled
    NEW: draft, submitted, withdrawn

Data migration (PredictionEntryPhase.status):
- ready    → submitted   (user had committed to readiness)
- locked   → submitted   (deadline-passed is just non-editable submission now)
- disabled → draft       (this value was unused; real disable is the
                          orthogonal `is_disabled` boolean on PredictionEntry)
- draft / submitted / withdrawn → unchanged

For every row whose status changes, write a PredictionEntryEvent row with
actor_role=SYSTEM, reason='lifecycle_simplification', so the audit trail
explains the change.

PostgreSQL doesn't support `ALTER TYPE ... DROP VALUE`, so the enum
swap uses the standard 4-step pattern:
  1. CREATE a new enum type with only the 3 values (entrystatus_new).
  2. ALTER each column that uses entrystatus to use entrystatus_new
     with a USING clause that maps old → new.
  3. DROP the old enum type.
  4. RENAME the new type to `entrystatus`.

Columns using `entrystatus`:
- prediction_entry_phases.status (the only one)
- prediction_entry_events.from_status and .to_status are TEXT (per the
  model — `from_status = String`, not the enum), so they don't need
  altering. They keep historical values like 'ready' / 'locked' as text.

Phase 2 schema (phase2_deadline, is_phase2_active, phase2_activated_at,
PHASE_2 in predictionphase enum, /admin/competition/phase2/open) is
NOT touched. It stays dormant for a possible future revival.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8d9e0f1a2b66"
down_revision: Union[str, None] = "7c8d9e0f1a55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ---- 1. Data migration: map status values + write audit events. ----
    # Audit row template; we look up entry.user_id to use as actor_user_id
    # (since the change is system-initiated and entry owner is the natural
    # subject for who's affected).
    # READY → SUBMITTED.
    op.execute(
        """
        INSERT INTO prediction_entry_events
            (id, entry_id, phase, from_status, to_status,
             actor_user_id, actor_role, reason, created_at)
        SELECT
            gen_random_uuid(), pep.entry_id, pep.phase, 'ready', 'submitted',
            pe.user_id, 'SYSTEM', 'lifecycle_simplification', NOW()
        FROM prediction_entry_phases pep
        JOIN prediction_entries pe ON pe.id = pep.entry_id
        WHERE pep.status::text = 'READY'
        """
    )
    op.execute(
        """
        UPDATE prediction_entry_phases
        SET status = 'SUBMITTED', updated_at = NOW()
        WHERE status::text = 'READY'
        """
    )

    # LOCKED → SUBMITTED.
    op.execute(
        """
        INSERT INTO prediction_entry_events
            (id, entry_id, phase, from_status, to_status,
             actor_user_id, actor_role, reason, created_at)
        SELECT
            gen_random_uuid(), pep.entry_id, pep.phase, 'locked', 'submitted',
            pe.user_id, 'SYSTEM', 'lifecycle_simplification', NOW()
        FROM prediction_entry_phases pep
        JOIN prediction_entries pe ON pe.id = pep.entry_id
        WHERE pep.status::text = 'LOCKED'
        """
    )
    op.execute(
        """
        UPDATE prediction_entry_phases
        SET status = 'SUBMITTED', updated_at = NOW()
        WHERE status::text = 'LOCKED'
        """
    )

    # DISABLED → DRAFT. (Enum value was unused; the real disable mechanism
    # is the orthogonal `is_disabled` boolean on prediction_entries, which
    # we don't touch.)
    op.execute(
        """
        INSERT INTO prediction_entry_events
            (id, entry_id, phase, from_status, to_status,
             actor_user_id, actor_role, reason, created_at)
        SELECT
            gen_random_uuid(), pep.entry_id, pep.phase, 'disabled', 'draft',
            pe.user_id, 'SYSTEM', 'lifecycle_simplification', NOW()
        FROM prediction_entry_phases pep
        JOIN prediction_entries pe ON pe.id = pep.entry_id
        WHERE pep.status::text = 'DISABLED'
        """
    )
    op.execute(
        """
        UPDATE prediction_entry_phases
        SET status = 'DRAFT', updated_at = NOW()
        WHERE status::text = 'DISABLED'
        """
    )

    # ---- 2. Swap the enum type. ----
    # PostgreSQL doesn't support ALTER TYPE DROP VALUE, so we:
    #   (a) create entrystatus_new with the 3 values;
    #   (b) alter the column to use the new type (data is already in the
    #       reduced set, so the USING clause is a straight cast);
    #   (c) drop the old type;
    #   (d) rename the new type to `entrystatus`.
    op.execute("CREATE TYPE entrystatus_new AS ENUM ('DRAFT', 'SUBMITTED', 'WITHDRAWN')")
    op.execute(
        """
        ALTER TABLE prediction_entry_phases
        ALTER COLUMN status TYPE entrystatus_new
        USING status::text::entrystatus_new
        """
    )
    op.execute("DROP TYPE entrystatus")
    op.execute("ALTER TYPE entrystatus_new RENAME TO entrystatus")


def downgrade() -> None:
    """Restore the 6-value enum. Cannot recover discarded transitions —
    rows that were `ready` / `locked` / `disabled` stay in their new
    statuses (submitted / submitted / draft). The audit events from the
    upgrade are kept for traceability.
    """
    bind = op.get_bind()

    op.execute(
        """
        CREATE TYPE entrystatus_old AS ENUM (
            'draft', 'ready', 'submitted', 'locked', 'withdrawn', 'disabled'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE prediction_entry_phases
        ALTER COLUMN status TYPE entrystatus_old
        USING status::text::entrystatus_old
        """
    )
    op.execute("DROP TYPE entrystatus")
    op.execute("ALTER TYPE entrystatus_old RENAME TO entrystatus")
