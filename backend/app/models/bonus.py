"""Bonus-question prediction + answer models.

Questions themselves live in `config/worldcup2026.yml` under the `bonus:`
key — they're tournament config, not data. These tables only hold:

- One row per (entry, question) for entry picks (`bonus_predictions`)
- One row per (competition, question) for the correct answer
  (`bonus_answers`), set by the admin when the answer is known.

`question_id` is the stable string key from the YAML (e.g. "dark_horse",
"top_scorer"). When the YAML changes question IDs, predictions for the
old ID become orphaned and the admin enters new correct answers.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.competition import Competition
    from app.models.entry import PredictionEntry


class BonusPrediction(SQLModel, table=True):
    """One entry's answer for one bonus question."""

    __tablename__ = "bonus_predictions"
    __table_args__ = (
        UniqueConstraint("entry_id", "question_id", name="uq_bonus_pred_entry_q"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entry_id: uuid.UUID = Field(foreign_key="prediction_entries.id", index=True)
    # YAML question ID, e.g. "most_goals_scored_group" or "top_scorer".
    question_id: str = Field(index=True, max_length=64)
    # Free-text answer. For team questions this is the full team name (matching
    # entries in the groups: section). For player questions it's whatever the
    # user typed — normalized at scoring time. Once the squads table ships,
    # player answers can be migrated to player_id references in-place.
    answer: str

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    entry: Optional["PredictionEntry"] = Relationship(back_populates="bonus_predictions")


class BonusAnswer(SQLModel, table=True):
    """The correct answer for a bonus question in a given competition.

    Set by an admin via /api/admin/bonus/answers when the question is
    resolved (group stage ending, tournament awards ceremony, etc.).
    Triggering a write here causes the leaderboard cache to invalidate so
    bonus points show up immediately.
    """

    __tablename__ = "bonus_answers"
    __table_args__ = (
        UniqueConstraint("competition_id", "question_id", name="uq_bonus_ans_comp_q"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    competition_id: uuid.UUID = Field(foreign_key="competitions.id", index=True)
    question_id: str = Field(index=True, max_length=64)
    # The canonical correct answer — same shape as predictions.answer.
    correct_answer: str
    resolved_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    competition: Optional["Competition"] = Relationship()
