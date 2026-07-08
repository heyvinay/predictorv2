"""What-if bracket simulator service.

Bulk-loads every eligible entry's full knockout picks + frozen group
points + current standing in a handful of queries, so the frontend can
re-rank the field client-side as the user hypothetically resolves
remaining knockout fixtures — no per-tweak round trip.

Also owns the GATING layer: an admin-controlled master switch per
competition (`Competition.simulator_enabled`). Admins always have full
access regardless of the switch. There is no per-user unlock or daily
run cap — those were removed; usage is still counted + audited via
`record_run`, just never capped.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.entry import ActorRole
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.user import User
from app.schemas.simulator import (
    SimulatorBracketPicks,
    SimulatorEntryPicks,
    SimulatorPicksResponse,
    SimulatorStatus,
)
from app.services.audit import record_audit_event
from app.services.leaderboard import _list_eligible_entries, calculate_leaderboard

# DB TeamPrediction.stage values are SINGULAR; the response's bracket-picks
# field names are PLURAL for QF/SF (frontend BracketPrediction convention —
# see entry_predictions.py:_organize_bracket). "winner" has no plural form
# since it's a single pick, not a list field.
_KO_STAGES = (
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
    "winner",
)

_STAGE_TO_FIELD = {
    "round_of_32": "round_of_32",
    "round_of_16": "round_of_16",
    "quarter_final": "quarter_finals",
    "semi_final": "semi_finals",
    "final": "final",
}


async def _load_ko_picks(
    session: AsyncSession, entry_ids: list[uuid.UUID]
) -> dict[uuid.UUID, SimulatorBracketPicks]:
    """All knockout-stage TeamPrediction rows for `entry_ids`, in one query.

    PHASE_1 ONLY — every entry carries a dormant phase_2 row set; joining
    without the phase filter double-counts (★ CLAUDE.md invariant).
    """
    if not entry_ids:
        return {}
    result = await session.execute(
        select(TeamPrediction.entry_id, TeamPrediction.stage, TeamPrediction.team)
        .where(TeamPrediction.entry_id.in_(entry_ids))
        .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
        .where(TeamPrediction.stage.in_(_KO_STAGES))
    )

    picks_by_entry: dict[uuid.UUID, SimulatorBracketPicks] = {
        entry_id: SimulatorBracketPicks() for entry_id in entry_ids
    }
    for entry_id, stage, team in result.all():
        bucket = picks_by_entry.setdefault(entry_id, SimulatorBracketPicks())
        if stage == "winner":
            bucket.winner = team
            continue
        field = _STAGE_TO_FIELD.get(stage)
        if field is None:
            continue
        getattr(bucket, field).append(team)

    return picks_by_entry


async def get_bracket_picks(session: AsyncSession) -> SimulatorPicksResponse:
    """Every eligible entry's knockout picks + frozen group points +
    frozen knockout-bonus points + current total/position, in ~3-4
    queries total:

    1. Eligible-entries lookup (shared predicate with the leaderboard).
    2. One bulk KO-stage TeamPrediction query for all entries.
    3. `calculate_leaderboard` (itself cached — usually a cache hit, not a
       fresh query round trip).
    """
    eligible = await _list_eligible_entries(session, phase="phase_1")
    entry_ids = [e.id for e in eligible]

    ko_picks = await _load_ko_picks(session, entry_ids)

    board = await calculate_leaderboard(session, phase=None)
    board_by_entry = {row.entry_id: row for row in board.entries}

    entries: list[SimulatorEntryPicks] = []
    for entry in eligible:
        row = board_by_entry.get(entry.id)
        if row is None:
            # Entry is eligible for phase_1 but didn't clear the overall
            # (cross-phase) leaderboard predicate — shouldn't happen given
            # the shared eligibility rule, but skip defensively rather than
            # crash the bulk endpoint over one row.
            continue

        phase1 = row.breakdown.phase1
        group_points = (
            phase1.match_total
            + phase1.group_advance_points
            + phase1.group_position_points
            + row.bonus_group_points
        )

        picks = ko_picks.get(entry.id, SimulatorBracketPicks())

        entries.append(
            SimulatorEntryPicks(
                entry_id=str(entry.id),
                entry_name=entry.display_name,
                user_id=str(entry.user_id),
                user_name=(
                    (entry.user.name or entry.user.email.split("@")[0])
                    if entry.user
                    else "Unknown"
                ),
                position=row.position,
                total_points=row.total_points,
                group_points=group_points,
                bonus_knockout_points=row.bonus_knockout_points,
                picks=picks,
            )
        )

    return SimulatorPicksResponse(
        entries=entries,
        last_calculated=aware_utc(board.last_calculated) or utc_now(),
    )


# ===========================================================================
# Gating — admin master switch only. Enforcement
# (`_require_simulator_access`) lives in app/api/simulator.py; this module
# just reports status and records usage for auditing.
# ===========================================================================


def get_status(user: User, competition: Competition | None) -> SimulatorStatus:
    """Current gating state for `user`: the active competition's master
    switch, plus whether `user` is an admin (who always has full access
    regardless of the switch)."""
    feature_enabled = bool(competition.simulator_enabled) if competition else False
    return SimulatorStatus(feature_enabled=feature_enabled, is_admin=user.is_admin)


async def record_run(session: AsyncSession, user: User) -> SimulatorStatus:
    """Record one committed simulator run against `user`, for auditing.

    No unlock or daily-cap check — the master switch
    (`_require_simulator_access`) is the only gate, and it's enforced by
    the caller before this runs. Fires a `feature.simulator_run` audit
    event and commits.
    """
    record_audit_event(
        session,
        event_type="feature.simulator_run",
        actor_user_id=user.id,
        actor_role=ActorRole.ADMIN if user.is_admin else ActorRole.USER,
        subject_type="user",
        subject_id=user.id,
        metadata={"is_admin": user.is_admin},
    )
    await session.commit()
    return SimulatorStatus(feature_enabled=True, is_admin=user.is_admin)
