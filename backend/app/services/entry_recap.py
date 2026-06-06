"""Build a structured recap of an entry's predictions for email rendering.

The submission-confirmation email appends a monospace recap of what the
user predicted (group scores, knockout advancement, bonus answers).
This module gathers that data shape in one place; the email builder in
`app/services/email.py` consumes the dict and renders the HTML/text.

Failure mode: callers (the /entries/{id}/submit handler) treat the recap
as best-effort. If this function raises, the email is sent without the
recap section rather than failing the submission.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.models.bonus import BonusPrediction
from app.models.entry import PredictionEntry
from app.models.fixture import Fixture
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.services import bonus as bonus_service


# Display order for knockout rounds in the recap. Stage codes match the
# Fixture.stage / TeamPrediction.stage convention used across the codebase
# (see e.g. backend/app/services/scoring.py:342). "winner" is rendered
# separately as the CHAMPION section, not inside the round list.
_KNOCKOUT_ROUNDS: list[tuple[str, str]] = [
    ("round_of_32", "ROUND OF 32"),
    ("round_of_16", "ROUND OF 16"),
    ("quarter_final", "QUARTER-FINALS"),
    ("semi_final", "SEMI-FINALS"),
    ("final", "FINAL"),
]


async def build_entry_recap(
    session: AsyncSession,
    *,
    entry_id: uuid.UUID,
) -> dict:
    """Build the recap data shape for an entry's submission email.

    Returns a dict with keys ``groups``, ``knockout``, ``champion``, ``bonus``.
    Phase 1 predictions only — Phase 2 is dormant per CLAUDE.md.
    """
    # Pull the entry with all three prediction relations eager-loaded so we
    # don't pay N+1 latency inside the rendering loops.
    entry_stmt = (
        select(PredictionEntry)
        .where(PredictionEntry.id == entry_id)
        .options(
            selectinload(PredictionEntry.match_predictions).selectinload(
                MatchPrediction.fixture
            ),
            selectinload(PredictionEntry.team_predictions),
            selectinload(PredictionEntry.bonus_predictions),
        )
    )
    result = await session.execute(entry_stmt)
    entry = result.scalar_one()

    groups = _build_groups(entry.match_predictions)
    knockout, champion = _build_knockout(entry.team_predictions)
    bonus = _build_bonus(entry.bonus_predictions)

    return {
        "groups": groups,
        "knockout": knockout,
        "champion": champion,
        "bonus": bonus,
    }


def _build_groups(match_predictions: list[MatchPrediction]) -> list[dict]:
    """Bucket group-stage fixtures by group letter, in alphabetical order."""
    by_group: dict[str, list[dict]] = {}
    for mp in match_predictions:
        if mp.phase != PredictionPhase.PHASE_1:
            continue
        fix = mp.fixture
        if fix is None or fix.stage != "group" or fix.group is None:
            continue
        by_group.setdefault(fix.group, []).append(
            {
                "home": fix.home_team,
                "away": fix.away_team,
                "home_score": mp.home_score,
                "away_score": mp.away_score,
                "match_number": fix.match_number or 0,
            }
        )
    # Sort fixtures within a group by match_number for deterministic ordering.
    for fixtures in by_group.values():
        fixtures.sort(key=lambda f: f["match_number"])
    return [
        {"letter": letter, "fixtures": by_group[letter]}
        for letter in sorted(by_group.keys())
    ]


def _build_knockout(
    team_predictions: list[TeamPrediction],
) -> tuple[list[dict], str | None]:
    """Bucket team predictions by knockout round.

    Returns (rounds, champion). Champion is the team predicted to win the
    tournament (stage == 'winner'); rounds excludes that entry so it can
    render as its own CHAMPION block.
    """
    by_stage: dict[str, list[str]] = {}
    champion: str | None = None
    for tp in team_predictions:
        if tp.phase != PredictionPhase.PHASE_1:
            continue
        if tp.stage == "winner":
            champion = tp.team
            continue
        by_stage.setdefault(tp.stage, []).append(tp.team)
    rounds: list[dict] = []
    for stage_code, label in _KNOCKOUT_ROUNDS:
        teams = by_stage.get(stage_code, [])
        if not teams:
            continue
        rounds.append({"stage": stage_code, "label": label, "teams": sorted(teams)})
    return rounds, champion


def _build_bonus(bonus_predictions: list[BonusPrediction]) -> list[dict]:
    """Pair each bonus prediction with its YAML question label."""
    label_by_id = {q.id: q.label for q in bonus_service.get_questions()}
    rendered: list[dict] = []
    # Render in YAML order so the email matches the wizard's question ordering.
    for q in bonus_service.get_questions():
        pred = next(
            (bp for bp in bonus_predictions if bp.question_id == q.id),
            None,
        )
        if pred is None:
            continue
        rendered.append({"question_label": label_by_id[q.id], "answer": pred.answer})
    return rendered
