"""Pydantic schema for the Group Stage Winner endpoint.

Mirrors the service dataclass field-for-field. The endpoint serialises
the dataclass through this schema to enforce response shape + give the
OpenAPI surface for client-side codegen later.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GroupStageWinnerResponse(BaseModel):
    """Single winner record returned by GET /api/dashboard/group-stage-winner."""

    entry_id: str
    user_name: str
    entry_name: str
    total_points: int
    final_rank: int

    # 4-part breakdown — sums to total_points
    outcome_points: int
    exact_score_extra: int
    rarity_extra: int
    bonus_question_points: int

    # Story stats
    correct_outcomes: int
    exact_scores: int
    days_at_top: int
    champion_pick: str | None
    champion_alive: bool
    finalist_picks: list[str]
    finalists_alive: int

    # Context facts that power the narrative (v2.181.0)
    runner_up_name: str | None
    runner_up_gap: int | None
    total_days: int

    # Pre-composed narrative — render verbatim on card and in email.
    story_line: str

    generated_at: datetime
