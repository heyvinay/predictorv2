"""Bracket-exposure computation.

Replaces the fixed `stubBracketExposure` on the frontend with a real
calculation of how many bracket points a user still has on the line.

Definition:
- "Points available" = sum of the scoring config's per-stage points for
  every knockout pick the user has locked in, assuming all picks are
  still alive. Multiplied by the phase multiplier.

  This is the *maximum* exposure — before any matches have been played,
  every pick is potentially still earning. As teams get eliminated this
  number should drop, but we don't have a "team eliminated" signal in
  the data yet, so for now we always report the maximum. (When live
  match results arrive — see the deferred Football-Data.org work — this
  service can subtract picks whose team was knocked out.)

- "Picks locked" / "picks total" — straightforward fraction of the
  bracket the user has filled in. Total is canonical to the FIFA 2026
  format (32 knockout picks across R32 → winner).

- "Final pick" — the (winner, opponent) pair extracted from the user's
  `winner` stage prediction and the other `final` stage prediction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.prediction import PredictionPhase, TeamPrediction
from app.services.scoring import get_scoring_config


# Map TeamPrediction.stage values → the scoring-config key for that stage.
# `group` is excluded — group-advance scoring is tracked differently and
# isn't part of "bracket exposure" in the dashboard's sense.
STAGE_POINT_KEY: dict[str, str] = {
    "round_of_32": "round_of_32",
    "round_of_16": "round_of_16",
    "quarter_final": "quarter_final",
    "semi_final": "semi_final",
    "final": "final",
    "winner": "winner",
}

# Canonical Phase 1 bracket pick counts for FIFA 2026 format:
#   16 R32 winners → 8 R16 winners → 4 QF → 2 SF → 1 final → 1 winner = 32 picks.
PICKS_PER_STAGE_PHASE_1: dict[str, int] = {
    "round_of_32": 16,
    "round_of_16": 8,
    "quarter_final": 4,
    "semi_final": 2,
    "final": 1,
    "winner": 1,
}
TOTAL_PHASE_1_BRACKET_PICKS = sum(PICKS_PER_STAGE_PHASE_1.values())


@dataclass
class BracketExposureResult:
    """Plain dataclass for the service result; API layer wraps in Pydantic."""

    points_available: int
    picks_locked: int
    picks_total: int
    final_winner: str | None
    final_opponent: str | None


async def compute_bracket_exposure(
    session: AsyncSession,
    entry_id: uuid.UUID,
    phase: PredictionPhase = PredictionPhase.PHASE_1,
) -> BracketExposureResult:
    """Compute the entry's bracket exposure for the given phase."""
    result = await session.execute(
        select(TeamPrediction)
        .where(TeamPrediction.entry_id == entry_id)
        .where(TeamPrediction.phase == phase)
    )
    preds = list(result.scalars().all())

    # Knockout-stage picks only — ignore 'group' stage predictions which
    # belong to group_advance scoring, not bracket exposure.
    ko_preds = [p for p in preds if p.stage in STAGE_POINT_KEY]

    config = get_scoring_config()
    adv = config.get("advancement", {})
    multiplier = config.get("phase_multipliers", {}).get(phase.value, 1.0)

    points_available = 0
    for p in ko_preds:
        key = STAGE_POINT_KEY[p.stage]
        points_available += adv.get(key, 0)
    points_available = int(round(points_available * multiplier))

    # Final pair: pull the user's winner pick and the other 'final' pick.
    winner_team = next((p.team for p in ko_preds if p.stage == "winner"), None)
    final_teams = [p.team for p in ko_preds if p.stage == "final"]
    final_opponent = None
    if winner_team:
        # The opponent is whichever finalist isn't the winner. If the user
        # only picked one finalist (the winner) we leave opponent as None.
        for t in final_teams:
            if t != winner_team:
                final_opponent = t
                break

    return BracketExposureResult(
        points_available=points_available,
        picks_locked=len(ko_preds),
        picks_total=TOTAL_PHASE_1_BRACKET_PICKS,
        final_winner=winner_team,
        final_opponent=final_opponent,
    )
