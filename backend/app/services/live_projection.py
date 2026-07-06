"""Live projected-leaderboard overlay (v2.198.0).

Read-time overlay layering a PROVISIONAL knockout-advancement projection
onto the banked leaderboard. Never mutates the banked board (the single
source of truth that daily snapshots + the Race chart consume) — it
copies rows, sets projected_* fields, and re-sorts a fresh list.

Key invariants (see docs/superpowers/plans/2026-07-06-live-projected-leaderboard.md):
- Knockout advancement ONLY (R32+). Rarity-free, so no denominator churn.
- Provisional winner = ET-inclusive, PENALTY-BLIND scoreline
  (Score.final_home_score/away). Level match → no winner. A live shootout
  is invisible until FINISHED.
- Overlay projects LIVE matches only; the seamless handoff at FINISHED is
  guaranteed by score_sync hard-invalidating the cache on a KO finish
  (see score_sync.sync_scores_once's points_relevant_ko branch).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse
from app.services.scoring import get_actual_advancement, get_scoring_config

# Stage -> the stage its winner reaches. Mirrors the advancement_map in
# scoring.get_actual_advancement. 'third_place' and 'group' are absent by
# design (third_place is unscored; group has no live projection).
_ADVANCEMENT_MAP = {
    "round_of_32": "round_of_16",
    "round_of_16": "quarter_final",
    "quarter_final": "semi_final",
    "semi_final": "final",
    "final": "winner",
}
_LIVE_STATUSES = (MatchStatus.LIVE, MatchStatus.HALFTIME)
_KO_STAGES = list(_ADVANCEMENT_MAP.keys())

# Full stage progression (mirrors scoring.get_actual_advancement's internal
# stage_ranking) — used to detect a team already banked at `next_stage` or
# beyond via the real (non-live) advancement path.
_STAGE_ORDER = ["round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner"]


def _already_banked(actual_advancement: dict[str, str], team: str, stage: str) -> bool:
    """True if `team` is already credited (via the REAL banked path) with
    reaching `stage` or beyond.

    Guards against a real race: scoring.get_actual_advancement() credits a
    team's advancement the instant a DOWNSTREAM fixture's real team name is
    seeded — with no requirement that the feeding (upstream) match be
    FINISHED. score_sync writes a fixture's real team names independent of
    any other fixture's status. So a team can already be banked at `stage`
    while the match that decided it is still LIVE in our DB. Without this
    check, a live delta here would double-count on top of the banked total
    that already includes the same credit — then silently vanish the moment
    the feeding match's status catches up, looking exactly like the
    visible-dip bug this feature exists to prevent.
    """
    current = actual_advancement.get(team)
    if not current or current not in _STAGE_ORDER or stage not in _STAGE_ORDER:
        return False
    return _STAGE_ORDER.index(current) >= _STAGE_ORDER.index(stage)


@dataclass
class LiveAdvance:
    """A provisional next-stage advance implied by a live KO match."""

    team: str
    next_stage: str
    points: int


def project_rows(
    entries: list[LeaderboardEntry], deltas: dict[uuid.UUID, int]
) -> list[LeaderboardEntry]:
    """Pure: return a NEW list of row COPIES with projected_* set and
    re-ranked by projected_total (exact_scores tiebreak, matching the
    banked sort). Banked position/total_points on each copy are left
    untouched. NEVER mutates the input list or its rows — the caller
    passes cache-owned objects."""
    projected: list[LeaderboardEntry] = []
    for e in entries:
        delta = deltas.get(e.entry_id, 0)
        copy = e.model_copy()
        copy.live_delta = delta
        copy.projected_total = e.total_points + delta
        projected.append(copy)

    projected.sort(key=lambda r: (r.projected_total, r.exact_scores), reverse=True)

    pos = 1
    for i, r in enumerate(projected):
        if i > 0 and (
            r.projected_total < projected[i - 1].projected_total
            or (
                r.projected_total == projected[i - 1].projected_total
                and r.exact_scores < projected[i - 1].exact_scores
            )
        ):
            pos = i + 1
        r.projected_position = pos
    return projected


async def _has_live_ko(session: AsyncSession) -> bool:
    q = await session.execute(
        select(Fixture.id)
        .where(Fixture.status.in_(_LIVE_STATUSES))
        .where(Fixture.stage.in_(_KO_STAGES))
        .limit(1)
    )
    return q.scalar_one_or_none() is not None


async def _live_ko_advances(session: AsyncSession) -> list[LiveAdvance]:
    """Provisional next-stage advances from currently-live KO matches.

    Winner is decided on the ET-inclusive, PENALTY-BLIND scoreline
    (final_home_score/away). A level match yields nothing (goes to
    ET/pens). Unresolved slot placeholders never produce an advance.
    """
    adv_config = get_scoring_config().get("advancement", {})
    result = await session.execute(
        select(Fixture, Score)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(Fixture.status.in_(_LIVE_STATUSES))
        .where(Fixture.stage.in_(_KO_STAGES))
    )
    advances: list[LiveAdvance] = []
    for fixture, score in result.all():
        home, away = score.final_home_score, score.final_away_score
        if home == away:
            continue  # level → no provisional winner
        winner = fixture.home_team if home > away else fixture.away_team
        if not winner or winner.startswith("slot:"):
            continue
        next_stage = _ADVANCEMENT_MAP[fixture.stage]
        advances.append(
            LiveAdvance(
                team=winner,
                next_stage=next_stage,
                points=int(adv_config.get(next_stage, 0)),
            )
        )
    return advances


async def _deltas_by_entry(
    session: AsyncSession, advances: list[LiveAdvance]
) -> dict[uuid.UUID, int]:
    """Provisional point gain per entry from the given live advances.

    An entry gains adv_config[next_stage] for each live advance whose
    (team, next_stage) matches one of its bracket picks — UNLESS that
    (team, next_stage) credit is already reflected in the banked
    get_actual_advancement() result, in which case it's skipped (see
    _already_banked's docstring for why this gap-check is required).
    PHASE_1 only (dormant phase_2 rows exist)."""
    if not advances:
        return {}

    actual_advancement = await get_actual_advancement(session)
    live_advances = [
        a for a in advances if not _already_banked(actual_advancement, a.team, a.next_stage)
    ]
    if not live_advances:
        return {}

    points_for = {(a.team, a.next_stage): a.points for a in live_advances}
    teams = [a.team for a in live_advances]
    stages = [a.next_stage for a in live_advances]
    rows = await session.execute(
        select(
            TeamPrediction.entry_id,
            TeamPrediction.team,
            TeamPrediction.stage,
        )
        .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
        .where(TeamPrediction.team.in_(teams))
        .where(TeamPrediction.stage.in_(stages))
    )
    deltas: dict[uuid.UUID, int] = {}
    for entry_id, team, stage in rows.all():
        pts = points_for.get((team, stage))
        if pts:
            deltas[entry_id] = deltas.get(entry_id, 0) + pts
    return deltas


async def _gates_open(session: AsyncSession) -> bool:
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    comp = result.scalar_one_or_none()
    return bool(comp and comp.knockout_scoring_enabled and comp.live_projection_enabled)


async def apply_live_projection(
    session: AsyncSession, response: LeaderboardResponse
) -> LeaderboardResponse:
    """Layer the live KO projection onto a banked LeaderboardResponse.

    Returns the response unchanged (live_projection_active stays False)
    when the gates are closed or no KO match is live. Otherwise returns a
    NEW response whose entries are re-ranked COPIES carrying projected_*.
    """
    if not await _gates_open(session):
        return response
    if not await _has_live_ko(session):
        return response
    advances = await _live_ko_advances(session)
    deltas = await _deltas_by_entry(session, advances)
    projected_entries = project_rows(response.entries, deltas)
    return response.model_copy(
        update={"entries": projected_entries, "live_projection_active": True}
    )
