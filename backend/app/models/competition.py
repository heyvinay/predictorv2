"""Competition model for tournament configuration."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now
from app.models.entry import PaymentMode

if TYPE_CHECKING:
    from app.models.entry import PredictionEntry
    from app.models.fixture import Fixture
    from app.models.user import User


class Competition(SQLModel, table=True):
    """Competition instance (e.g., World Cup 2026)."""

    __tablename__ = "competitions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    entry_fee: Decimal = Field(default=Decimal("0.00"), max_digits=10, decimal_places=2)

    # Phase 1 Deadlines (Group Stage)
    phase1_deadline: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    # Phase 2 Control
    is_phase2_active: bool = Field(default=False)
    phase2_activated_at: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))
    phase2_bracket_deadline: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))
    phase2_deadline: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    # Post-deadline release control (v2.166.0): after the deadline the
    # V4 pages (dashboard / results / leaderboard) stay behind their
    # pre-tournament stubs until an admin flips this from /admin
    # ("Go live") — backend clean-up happens in that window. Admins
    # always see the V4 pages regardless.
    post_deadline_live: bool = Field(default=False)

    # Group Stage Winner release switch (v2.181.0): flipped by admin at
    # 7pm Malta on Sunday 28 June 2026 (or whenever the group stage
    # winner is to be revealed). Controls visibility of:
    #   - GroupStageWinnerCard on the dashboard
    #   - GROUP_STAGE_FINAL broadcast email content payload
    # Mirrors the post_deadline_live pattern — admin-only toggle from
    # /admin, defaults FALSE so the card stays hidden until release.
    group_stage_winner_released: bool = Field(default=False)

    # Knockout scoring gate (v2.181.1): admin-controlled switch that
    # gates ALL advancement-point payouts (group_advance / group_position
    # / round_of_32 / ... / winner) computed by
    # services.scoring.calculate_advancement_points. Match-points
    # (group-stage fixtures only) are NOT affected. Defaults FALSE so
    # the engine holds back knockout payouts until the admin verifies
    # the group-stage standings and bracket seeding, then flips this
    # from /admin. Distinct from group_stage_winner_released so an
    # admin can announce the champion without committing the engine.
    knockout_scoring_enabled: bool = Field(default=False)

    # Announcement hero visibility (v2.191.0): admin-controlled toggle that
    # hides the dashboard AnnouncementHero entirely — even the fallback
    # welcome card — when set to False. Defaults True so the hero shows on
    # all existing competitions without a migration data patch.
    announcement_hero_enabled: bool = Field(default=True)

    # What-if bracket simulator master switch: admin-controlled gate on
    # top of the per-user trivia unlock + daily cap. Defaults FALSE so the
    # simulator stays off until an admin opts a competition in from
    # /admin. Admins always retain full simulator access regardless of
    # this flag (see services.simulator.get_status/record_run) — usage is
    # still counted + audited, just uncapped.
    simulator_enabled: bool = Field(default=False)

    # Configuration reference
    config_file: str | None = None

    # External API identifier (e.g. Football-Data competition code "WC")
    external_id: str | None = Field(default=None, index=True)

    is_active: bool = Field(default=True)

    # Entry settings — admin-configurable per competition. YAML config only
    # provides bootstrap defaults; the effective values live on this row.
    max_entries_per_user: int = Field(default=5)
    auto_create_first_entry: bool = Field(default=True)
    allow_duplicate_from_existing: bool = Field(default=True)
    allow_user_rename: bool = Field(default=True)
    allow_user_withdrawal: bool = Field(default=True)
    require_ready_before_submit: bool = Field(default=True)
    payment_mode: PaymentMode = Field(default=PaymentMode.PER_ENTRY)
    block_unpaid_entry_submission: bool = Field(default=False)
    show_entry_reference_publicly: bool = Field(default=False)
    phase_scoped_status_enabled: bool = Field(default=False)
    bonus_questions_required_for_ready: bool = Field(default=False)

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    users: list["User"] = Relationship(back_populates="competition")
    fixtures: list["Fixture"] = Relationship(back_populates="competition")
    entries: list["PredictionEntry"] = Relationship(back_populates="competition")
