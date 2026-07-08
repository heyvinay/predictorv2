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
# Gating (v2.194.x) — one-time trivia unlock, daily run cap, admin master
# switch. See app/services/simulator.py for the enforcement logic.
# ---------------------------------------------------------------------------


class SimulatorStatus(BaseModel):
    """Current gating state for the requesting user.

    `runs_remaining` is `None` for admins (unlimited — the cap doesn't
    apply to them) and `max(0, cap - runs_used)` for everyone else.
    """

    feature_enabled: bool
    unlocked: bool
    is_admin: bool
    runs_used: int
    runs_remaining: int | None
    cap: int
    reset_at: datetime | None


class ChallengeQuestion(BaseModel):
    """One trivia question, answer key withheld.

    ★ Never add `correct_index` (or any other answer-bearing field) to
    this schema — it is the response body for `GET /simulator/challenge`
    and must never leak the answer to the client.
    """

    question_id: str
    question: str
    options: list[str]


class ChallengeAttempt(BaseModel):
    """A user's answer to a trivia challenge."""

    question_id: str
    answer_index: int
    elapsed_ms: int


class UnlockResult(BaseModel):
    """Outcome of a trivia attempt + the resulting gating status."""

    unlocked: bool
    status: SimulatorStatus


class FiftyFiftyRequest(BaseModel):
    """Client claims the 50:50 lifeline for a specific challenge question."""

    question_id: str


class FiftyFiftyResponse(BaseModel):
    """Two option indexes that are NOT the correct answer.

    Classic 50:50 mechanic — the client eliminates these two so the
    remaining pair still includes the correct answer. Returning up to two
    wrong indexes never leaks `correct_index` directly (there are always
    three wrong options, so revealing two still leaves genuine ambiguity
    if the user hasn't used the lifeline).
    """

    wrong_indexes: list[int]
