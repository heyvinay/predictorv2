"""Match-impact service — which finished KO fixtures shuffled the leaderboard the most.

Used by the chart-annotation marker layer on the race tab. Group-stage
fixtures are excluded (KO-only rule); ``third_place`` is excluded
(unscored per CLAUDE.md invariant). Returns at most 3 markers, ordered
by impact score descending.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.models._datetime import aware_utc, utc_now


# Stage whitelist — KO only, no third_place (CLAUDE.md invariant)
SCORED_KO_STAGES = {
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
}

MARKER_CAP = 3


@dataclass
class MatchMarker:
    fixture_id: str
    kickoff: datetime
    home_team_code: str
    away_team_code: str
    home_score: int
    away_score: int
    is_upset: bool
    impact_score: float


@dataclass
class MatchMarkersResult:
    markers: list[MatchMarker]
    generated_at: datetime


async def compute_match_markers(
    session: AsyncSession, *, days: int = 14,
) -> MatchMarkersResult:
    """Returns at most 3 KO match markers from the last ``days`` days, ranked by impact.

    Only FINISHED fixtures in ``SCORED_KO_STAGES`` within the window are
    considered. ``third_place`` is explicitly excluded — the prediction game
    does not score that fixture (CLAUDE.md invariant).

    Each returned marker's ``kickoff`` is wrapped via ``aware_utc()`` to
    survive the aiosqlite tzinfo-strip on test runs.
    """
    earliest = utc_now() - timedelta(days=days)

    stmt = (
        select(Fixture, Score)
        .outerjoin(Score, Score.fixture_id == Fixture.id)
        .where(Fixture.status == MatchStatus.FINISHED)
        .where(Fixture.stage.in_(SCORED_KO_STAGES))
        .where(Fixture.kickoff >= earliest)
        .order_by(Fixture.kickoff.desc())
    )
    rows = (await session.execute(stmt)).all()

    markers: list[MatchMarker] = []
    for fixture, score in rows:
        markers.append(
            MatchMarker(
                fixture_id=str(fixture.id),
                kickoff=aware_utc(fixture.kickoff),
                home_team_code=fixture.home_team,
                away_team_code=fixture.away_team,
                home_score=score.home_score if score else 0,
                away_score=score.away_score if score else 0,
                # v1: always False — pool-consensus upset detection is a planned follow-up
                is_upset=False,
                impact_score=_impact_score(fixture),
            )
        )

    markers.sort(key=lambda m: m.impact_score, reverse=True)
    return MatchMarkersResult(
        markers=markers[:MARKER_CAP],
        generated_at=utc_now(),
    )


def _impact_score(f: Fixture) -> float:
    """Score a finished KO fixture by how rank-disruptive it likely is.

    v1: stage weight only. Later rounds eliminate more entries' live picks
    and therefore cause bigger rank shuffles.
    """
    weights: dict[str, float] = {
        "round_of_32": 1.0,
        "round_of_16": 1.5,
        "quarter_final": 2.5,
        "semi_final": 4.0,
        "final": 6.0,
    }
    return weights.get(f.stage, 1.0)
