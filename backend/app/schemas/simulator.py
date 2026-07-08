"""What-if bracket simulator schemas.

Powers a client-side leaderboard re-rank: the frontend takes every
eligible entry's frozen group points + full knockout picks, lets the
user hypothetically resolve remaining knockout fixtures, and recomputes
standings without another round trip per what-if tweak.
"""

from datetime import datetime

from pydantic import BaseModel


class SimulatorBracketPicks(BaseModel):
    """One entry's knockout picks, keyed by stage.

    Field names are PLURAL (`quarter_finals`, `semi_finals`) to match the
    `BracketPrediction` API shape the frontend already knows how to read
    (see `app.schemas.predictions.BracketPrediction` /
    `entry_predictions.py:_organize_bracket`). The underlying
    `TeamPrediction.stage` column values are SINGULAR
    (`quarter_final`, `semi_final`) — mapped at the service layer.
    """

    round_of_32: list[str] = []
    round_of_16: list[str] = []
    quarter_finals: list[str] = []
    semi_finals: list[str] = []
    final: list[str] = []
    winner: str | None = None


class SimulatorEntryPicks(BaseModel):
    """One eligible entry's picks + frozen group points + current standing."""

    entry_id: str
    entry_name: str
    user_id: str
    user_name: str
    position: int
    total_points: int
    # Group-stage points only (match outcomes/exact scores + group
    # advancement/position bonuses + group-stage bonus questions) — frozen
    # inputs the simulator layers hypothetical knockout results on top of.
    group_points: int
    # Knockout-stage bonus-question points (e.g. Top/Flop) — also frozen.
    # No bonus question is resolved by who wins a bracket match, so this
    # rides through unchanged in every what-if scenario, same as
    # `group_points`. Without it, `newTotal` on the frontend silently
    # dropped this component even in a "nothing hypothetical changed"
    # scenario, understating any entry with banked knockout-bonus points.
    bonus_knockout_points: int
    picks: SimulatorBracketPicks


class SimulatorPicksResponse(BaseModel):
    """Every eligible entry's bracket picks in one response."""

    entries: list[SimulatorEntryPicks]
    last_calculated: datetime


# ---------------------------------------------------------------------------
# Gating — admin master switch only. The one-time trivia unlock and daily
# run cap were removed; see app/services/simulator.py.
# ---------------------------------------------------------------------------


class SimulatorStatus(BaseModel):
    """Current gating state for the requesting user.

    `feature_enabled` reflects the active competition's admin-controlled
    master switch. Admins always get full access regardless of its value.
    """

    feature_enabled: bool
    is_admin: bool
