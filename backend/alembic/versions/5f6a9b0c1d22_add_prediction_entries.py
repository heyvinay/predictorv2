"""Add prediction entries, phases, events; rewire prediction tables to entries.

Revision ID: 5f6a9b0c1d22
Revises: 4e5f7a2b8c11
Create Date: 2026-05-16 13:30:00.000000

This is a greenfield, destructive migration. No backfill is performed —
existing prediction rows would be orphaned. The expectation is that this
runs against a database with no production data.

Adds:
- 3 new enum types (entrystatus, actorrole, paymentmode)
- 3 new tables (prediction_entries, prediction_entry_phases,
  prediction_entry_events)
- 11 entry-settings columns on `competitions`

Rewires:
- match_predictions, team_predictions, bonus_predictions:
  drops user_id → adds entry_id (FK to prediction_entries)
- leaderboard_snapshots: adds entry_id (nullable); replaces unique
  constraint from (user_id, captured_date) to (entry_id, captured_date)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


# revision identifiers, used by Alembic.
revision: str = "5f6a9b0c1d22"
down_revision: Union[str, None] = "4e5f7a2b8c11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# DB-level enum value sets. UPPERCASE to match the existing convention
# (matchstatus, predictionphase, authprovider, scoresource all use
# uppercase enum names — Python `str, Enum` classes have lowercase
# `.value` strings but SQLAlchemy stores the `.name` for enum types
# created from a Python Enum subclass).
ENTRY_STATUS_VALUES = ("DRAFT", "READY", "SUBMITTED", "LOCKED", "WITHDRAWN", "DISABLED")
ACTOR_ROLE_VALUES = ("USER", "ADMIN", "SYSTEM")
PAYMENT_MODE_VALUES = ("PER_ENTRY", "PER_USER")

# We use sqlalchemy.dialects.postgresql.ENUM (not sa.Enum) for all column
# references to existing or new enum types. sa.Enum is the generic SQL
# type and silently drops the postgres-specific `create_type` kwarg, which
# causes "type already exists" errors when reusing an enum that was created
# in a previous migration (predictionphase) or earlier in this migration
# (entrystatus, actorrole, paymentmode). The PG-dialect ENUM honors it.


def upgrade() -> None:
    # -------------------------------------------------------------------
    # Step 1 — Create new Postgres enum types
    # -------------------------------------------------------------------
    op.execute(
        "CREATE TYPE entrystatus AS ENUM "
        "('DRAFT', 'READY', 'SUBMITTED', 'LOCKED', 'WITHDRAWN', 'DISABLED')"
    )
    op.execute("CREATE TYPE actorrole AS ENUM ('USER', 'ADMIN', 'SYSTEM')")
    op.execute("CREATE TYPE paymentmode AS ENUM ('PER_ENTRY', 'PER_USER')")

    # -------------------------------------------------------------------
    # Step 2 — Add entry-settings columns to `competitions`
    # All with server_default so the existing competition row backfills.
    # -------------------------------------------------------------------
    op.add_column(
        "competitions",
        sa.Column("max_entries_per_user", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "auto_create_first_entry",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "allow_duplicate_from_existing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "allow_user_rename", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "allow_user_withdrawal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "require_ready_before_submit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "payment_mode",
            PgEnum(*PAYMENT_MODE_VALUES, name="paymentmode", create_type=False),
            nullable=False,
            server_default="PER_ENTRY",
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "block_unpaid_entry_submission",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "show_entry_reference_publicly",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "phase_scoped_status_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column(
            "bonus_questions_required_for_ready",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # -------------------------------------------------------------------
    # Step 3 — Create `prediction_entries`
    # -------------------------------------------------------------------
    op.create_table(
        "prediction_entries",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("entry_number", sa.Integer(), nullable=False),
        sa.Column("paid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "prize_eligible", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("is_disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("disabled_reason", sa.String(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["competition_id"], ["competitions.id"], name="fk_entry_competition"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_entry_user"),
        sa.ForeignKeyConstraint(
            ["disabled_by_user_id"], ["users.id"], name="fk_entry_disabled_by"
        ),
        sa.UniqueConstraint(
            "competition_id", "reference", name="uq_entry_competition_reference"
        ),
        sa.UniqueConstraint(
            "competition_id",
            "user_id",
            "entry_number",
            name="uq_entry_competition_user_number",
        ),
    )
    op.create_index(
        "ix_entry_competition_user",
        "prediction_entries",
        ["competition_id", "user_id"],
    )
    op.create_index(
        "ix_entry_competition_disabled",
        "prediction_entries",
        ["competition_id", "is_disabled"],
    )

    # -------------------------------------------------------------------
    # Step 4 — Create `prediction_entry_phases`
    # -------------------------------------------------------------------
    op.create_table(
        "prediction_entry_phases",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column(
            "phase",
            PgEnum("PHASE_1", "PHASE_2", name="predictionphase", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            PgEnum(*ENTRY_STATUS_VALUES, name="entrystatus", create_type=False),
            nullable=False,
        ),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["prediction_entries.id"], name="fk_entry_phase_entry"
        ),
        sa.UniqueConstraint("entry_id", "phase", name="uq_entry_phase"),
    )
    op.create_index(
        "ix_prediction_entry_phases_entry_id",
        "prediction_entry_phases",
        ["entry_id"],
    )
    op.create_index(
        "ix_entry_phase_status", "prediction_entry_phases", ["phase", "status"]
    )

    # -------------------------------------------------------------------
    # Step 5 — Create `prediction_entry_events`
    # -------------------------------------------------------------------
    op.create_table(
        "prediction_entry_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column(
            "phase",
            PgEnum("PHASE_1", "PHASE_2", name="predictionphase", create_type=False),
            nullable=True,
        ),
        sa.Column("from_status", sa.String(), nullable=False),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "actor_role",
            PgEnum(*ACTOR_ROLE_VALUES, name="actorrole", create_type=False),
            nullable=False,
        ),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["prediction_entries.id"], name="fk_entry_event_entry"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_entry_event_actor"
        ),
    )
    op.create_index(
        "ix_prediction_entry_events_entry_id",
        "prediction_entry_events",
        ["entry_id"],
    )
    op.create_index(
        "ix_prediction_entry_events_actor_user_id",
        "prediction_entry_events",
        ["actor_user_id"],
    )

    # -------------------------------------------------------------------
    # Greenfield clear — destructive by design. The brief states no
    # backfill is required because there is no production data. The
    # `entry_id` columns being added next are NOT NULL, so any pre-
    # existing rows would fail the constraint. We clear them here.
    # -------------------------------------------------------------------
    op.execute("TRUNCATE TABLE match_predictions CASCADE")
    op.execute("TRUNCATE TABLE team_predictions CASCADE")
    op.execute("TRUNCATE TABLE bonus_predictions CASCADE")
    op.execute("TRUNCATE TABLE leaderboard_snapshots CASCADE")

    # -------------------------------------------------------------------
    # Step 6 — Alter `match_predictions`: user_id → entry_id
    # No existing DB-level unique constraint to drop (the old
    # Config.unique_together was Pydantic-only).
    # -------------------------------------------------------------------
    op.drop_index("ix_match_predictions_user_id", table_name="match_predictions")
    op.drop_constraint(
        "match_predictions_user_id_fkey", "match_predictions", type_="foreignkey"
    )
    op.drop_column("match_predictions", "user_id")
    op.add_column(
        "match_predictions", sa.Column("entry_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "fk_match_pred_entry",
        "match_predictions",
        "prediction_entries",
        ["entry_id"],
        ["id"],
    )
    op.create_index(
        "ix_match_predictions_entry_id", "match_predictions", ["entry_id"]
    )
    op.create_unique_constraint(
        "uq_match_pred_entry_fixture",
        "match_predictions",
        ["entry_id", "fixture_id"],
    )

    # -------------------------------------------------------------------
    # Step 7 — Alter `team_predictions`: user_id → entry_id
    # New unique includes `phase` so the same team/stage can appear in
    # both phase_1 and phase_2 for the same entry.
    # -------------------------------------------------------------------
    op.drop_index("ix_team_predictions_user_id", table_name="team_predictions")
    op.drop_constraint(
        "team_predictions_user_id_fkey", "team_predictions", type_="foreignkey"
    )
    op.drop_column("team_predictions", "user_id")
    op.add_column(
        "team_predictions", sa.Column("entry_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "fk_team_pred_entry",
        "team_predictions",
        "prediction_entries",
        ["entry_id"],
        ["id"],
    )
    op.create_index(
        "ix_team_predictions_entry_id", "team_predictions", ["entry_id"]
    )
    op.create_unique_constraint(
        "uq_team_pred_entry_phase_team_stage",
        "team_predictions",
        ["entry_id", "phase", "team", "stage"],
    )

    # -------------------------------------------------------------------
    # Step 8 — Alter `bonus_predictions`: user_id → entry_id
    # This table DOES have an existing DB-level unique constraint.
    # -------------------------------------------------------------------
    op.drop_constraint("uq_bonus_pred_user_q", "bonus_predictions", type_="unique")
    op.drop_index("ix_bonus_predictions_user_id", table_name="bonus_predictions")
    op.drop_constraint(
        "bonus_predictions_user_id_fkey", "bonus_predictions", type_="foreignkey"
    )
    op.drop_column("bonus_predictions", "user_id")
    op.add_column(
        "bonus_predictions", sa.Column("entry_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "fk_bonus_pred_entry",
        "bonus_predictions",
        "prediction_entries",
        ["entry_id"],
        ["id"],
    )
    op.create_index(
        "ix_bonus_predictions_entry_id", "bonus_predictions", ["entry_id"]
    )
    op.create_unique_constraint(
        "uq_bonus_pred_entry_q",
        "bonus_predictions",
        ["entry_id", "question_id"],
    )

    # -------------------------------------------------------------------
    # Step 9 — Alter `leaderboard_snapshots`: add entry_id, swap unique key
    # entry_id stays nullable for now — Task D will migrate the snapshot
    # service and then make it NOT NULL.
    # -------------------------------------------------------------------
    op.drop_constraint(
        "uq_snapshot_user_date", "leaderboard_snapshots", type_="unique"
    )
    op.add_column(
        "leaderboard_snapshots", sa.Column("entry_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_snapshot_entry",
        "leaderboard_snapshots",
        "prediction_entries",
        ["entry_id"],
        ["id"],
    )
    op.create_index(
        "ix_leaderboard_snapshots_entry_id",
        "leaderboard_snapshots",
        ["entry_id"],
    )
    op.create_unique_constraint(
        "uq_snapshot_entry_date",
        "leaderboard_snapshots",
        ["entry_id", "captured_date"],
    )


def downgrade() -> None:
    # Reverse order, exactly.

    # 9 reverse
    op.drop_constraint(
        "uq_snapshot_entry_date", "leaderboard_snapshots", type_="unique"
    )
    op.drop_index(
        "ix_leaderboard_snapshots_entry_id", table_name="leaderboard_snapshots"
    )
    op.drop_constraint(
        "fk_snapshot_entry", "leaderboard_snapshots", type_="foreignkey"
    )
    op.drop_column("leaderboard_snapshots", "entry_id")
    op.create_unique_constraint(
        "uq_snapshot_user_date",
        "leaderboard_snapshots",
        ["user_id", "captured_date"],
    )

    # 8 reverse — bonus_predictions
    op.drop_constraint("uq_bonus_pred_entry_q", "bonus_predictions", type_="unique")
    op.drop_index("ix_bonus_predictions_entry_id", table_name="bonus_predictions")
    op.drop_constraint("fk_bonus_pred_entry", "bonus_predictions", type_="foreignkey")
    op.drop_column("bonus_predictions", "entry_id")
    op.add_column(
        "bonus_predictions", sa.Column("user_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "bonus_predictions_user_id_fkey",
        "bonus_predictions",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index(
        "ix_bonus_predictions_user_id", "bonus_predictions", ["user_id"]
    )
    op.create_unique_constraint(
        "uq_bonus_pred_user_q", "bonus_predictions", ["user_id", "question_id"]
    )

    # 7 reverse — team_predictions
    op.drop_constraint(
        "uq_team_pred_entry_phase_team_stage", "team_predictions", type_="unique"
    )
    op.drop_index("ix_team_predictions_entry_id", table_name="team_predictions")
    op.drop_constraint("fk_team_pred_entry", "team_predictions", type_="foreignkey")
    op.drop_column("team_predictions", "entry_id")
    op.add_column(
        "team_predictions", sa.Column("user_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "team_predictions_user_id_fkey",
        "team_predictions",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index(
        "ix_team_predictions_user_id", "team_predictions", ["user_id"]
    )

    # 6 reverse — match_predictions
    op.drop_constraint(
        "uq_match_pred_entry_fixture", "match_predictions", type_="unique"
    )
    op.drop_index("ix_match_predictions_entry_id", table_name="match_predictions")
    op.drop_constraint(
        "fk_match_pred_entry", "match_predictions", type_="foreignkey"
    )
    op.drop_column("match_predictions", "entry_id")
    op.add_column(
        "match_predictions", sa.Column("user_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "match_predictions_user_id_fkey",
        "match_predictions",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index(
        "ix_match_predictions_user_id", "match_predictions", ["user_id"]
    )

    # 5 reverse
    op.drop_index(
        "ix_prediction_entry_events_actor_user_id",
        table_name="prediction_entry_events",
    )
    op.drop_index(
        "ix_prediction_entry_events_entry_id", table_name="prediction_entry_events"
    )
    op.drop_table("prediction_entry_events")

    # 4 reverse
    op.drop_index("ix_entry_phase_status", table_name="prediction_entry_phases")
    op.drop_index(
        "ix_prediction_entry_phases_entry_id", table_name="prediction_entry_phases"
    )
    op.drop_table("prediction_entry_phases")

    # 3 reverse
    op.drop_index("ix_entry_competition_disabled", table_name="prediction_entries")
    op.drop_index("ix_entry_competition_user", table_name="prediction_entries")
    op.drop_table("prediction_entries")

    # 2 reverse — drop competition columns
    op.drop_column("competitions", "bonus_questions_required_for_ready")
    op.drop_column("competitions", "phase_scoped_status_enabled")
    op.drop_column("competitions", "show_entry_reference_publicly")
    op.drop_column("competitions", "block_unpaid_entry_submission")
    op.drop_column("competitions", "payment_mode")
    op.drop_column("competitions", "require_ready_before_submit")
    op.drop_column("competitions", "allow_user_withdrawal")
    op.drop_column("competitions", "allow_user_rename")
    op.drop_column("competitions", "allow_duplicate_from_existing")
    op.drop_column("competitions", "auto_create_first_entry")
    op.drop_column("competitions", "max_entries_per_user")

    # 1 reverse — drop enum types AFTER all consuming columns are dropped
    op.execute("DROP TYPE paymentmode")
    op.execute("DROP TYPE actorrole")
    op.execute("DROP TYPE entrystatus")
