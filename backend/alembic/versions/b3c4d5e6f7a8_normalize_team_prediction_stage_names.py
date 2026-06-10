"""Normalize TeamPrediction.stage values to singular spellings.

Revision ID: b3c4d5e6f7a8
Revises: 9a1b2c3d4e5f
Create Date: 2026-06-10 12:00:00.000000

The frontend historically wrote `quarter_finals` / `semi_finals` (plural)
into team_predictions.stage, while the scoring engine, Fixture.stage,
config/worldcup2026.yml advancement keys, and the email recap all use
singular (`quarter_final` / `semi_final`). The mismatch made QF/SF bracket
picks silently score 0 points. v2.161.0 makes singular canonical
everywhere (frontend writes singular; backend normalizes defensively via
models.prediction.normalize_stage); this migration converts the existing
production rows.

For each (plural → singular) pair:
  1. Guard DELETE: remove plural rows that would collide with an existing
     singular row for the same (entry_id, phase, team) — protects the
     uq_team_pred_entry_phase_team_stage unique constraint, which spans
     (entry_id, phase, team, stage). A collision means the entry already
     holds the same pick under both spellings; the plural copy is a
     redundant duplicate.
  2. UPDATE the remaining plural rows to the singular spelling.

Notes:
- `stage` is a plain VARCHAR column — no enum type swap needed.
- Audit-event metadata (prediction.bracket_replaced picks_summary) is
  intentionally NOT rewritten — it is a historical record of what the
  client sent at the time.
- Downgrade is asymmetric: it reverses the UPDATEs but cannot restore
  guard-DELETEd duplicate rows (they were redundant duplicates of picks
  that still exist under the singular spelling).
- The pytest suite uses SQLModel create_all, not Alembic — this migration
  must be verified manually: upgrade, probe
  `SELECT stage, COUNT(*) FROM team_predictions GROUP BY stage` (expect
  no plurals), downgrade, re-upgrade. Backend startup auto-runs
  `alembic upgrade head` (app.database.init_db), so prod picks this up
  on deploy.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "9a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STAGE_RENAMES: list[tuple[str, str]] = [
    ("quarter_finals", "quarter_final"),
    ("semi_finals", "semi_final"),
]


def upgrade() -> None:
    for plural, singular in _STAGE_RENAMES:
        # 1. Guard: drop plural rows whose singular twin already exists for
        #    the same (entry_id, phase, team) — renaming them would violate
        #    uq_team_pred_entry_phase_team_stage.
        op.execute(
            f"""
            DELETE FROM team_predictions tp
            WHERE tp.stage = '{plural}'
              AND EXISTS (
                  SELECT 1 FROM team_predictions dup
                  WHERE dup.entry_id = tp.entry_id
                    AND dup.phase = tp.phase
                    AND dup.team = tp.team
                    AND dup.stage = '{singular}'
              )
            """
        )
        # 2. Rename the remainder.
        op.execute(
            f"""
            UPDATE team_predictions
            SET stage = '{singular}', updated_at = NOW()
            WHERE stage = '{plural}'
            """
        )


def downgrade() -> None:
    """Reverse the renames. Guard-DELETEd duplicate rows are NOT restored
    (they duplicated picks that survive under the other spelling)."""
    for plural, singular in _STAGE_RENAMES:
        op.execute(
            f"""
            UPDATE team_predictions
            SET stage = '{plural}', updated_at = NOW()
            WHERE stage = '{singular}'
            """
        )
