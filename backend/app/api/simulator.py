"""What-if bracket simulator API routes.

Gating: every route requires auth. The MASTER-SWITCH gate
(`competition.simulator_enabled`) applies to every INTERACTIVE route —
`/run` and `/bracket-picks`: a non-admin caller is 403'd on both when the
switch is off. Admins always bypass the master switch (full access even
when it's off). `GET /status` is the ONE route that stays reachable
regardless of the switch — it's how the frontend learns `feature_enabled`
to decide whether to show the simulator at all.
"""

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.dependencies import CurrentUser, DbSession
from app.models.competition import Competition
from app.models.user import User
from app.schemas.simulator import SimulatorPicksResponse, SimulatorStatus
from app.services.simulator import get_bracket_picks, get_status, record_run

router = APIRouter()


async def _get_active_competition(session: DbSession) -> Competition | None:
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    return result.scalar_one_or_none()


def _require_simulator_access(user: User, competition: Competition | None) -> None:
    """Master-switch gate shared by every INTERACTIVE simulator route.

    A non-admin caller may only interact with the simulator (run,
    bracket-picks) when the active competition's `simulator_enabled` is
    true. Admins always bypass — they retain full access even with the
    switch off. Raises 403 for a blocked non-admin; returns None otherwise.

    Deliberately NOT applied to `GET /status`: that endpoint must stay
    reachable so the frontend can read `feature_enabled` and decide
    whether to surface the simulator to the user at all.
    """
    if user.is_admin:
        return
    feature_enabled = bool(competition.simulator_enabled) if competition else False
    if not feature_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The bracket simulator isn't available yet.",
        )


@router.get("/status", response_model=SimulatorStatus)
async def simulator_status(
    session: DbSession,
    user: CurrentUser,
) -> SimulatorStatus:
    """Current gating state for the caller: feature flag + admin status.

    Always reachable — never master-switch-gated — so the frontend can
    read `feature_enabled` for a locked-out non-admin.
    """
    competition = await _get_active_competition(session)
    return get_status(user, competition)


@router.post("/run", response_model=SimulatorStatus)
async def simulator_run(
    session: DbSession,
    user: CurrentUser,
) -> SimulatorStatus:
    """Record one committed what-if simulator run, for auditing.

    Master-switch-gated for non-admins (403 when the switch is off).
    No unlock or daily-cap check beyond that.
    """
    competition = await _get_active_competition(session)
    _require_simulator_access(user, competition)
    return await record_run(session, user)


@router.get("/bracket-picks", response_model=SimulatorPicksResponse)
async def bracket_picks(
    session: DbSession,
    user: CurrentUser,
) -> SimulatorPicksResponse:
    """Every eligible entry's full knockout picks + frozen group points +
    current total/position, in one bulk response.

    Powers a client-side leaderboard re-rank for the what-if bracket
    simulator: the frontend hypothetically resolves remaining knockout
    fixtures and recomputes standings locally instead of round-tripping
    per tweak.

    Access requires `user.is_admin OR competition.simulator_enabled` —
    admins always get through, even with the master switch off.
    """
    competition = await _get_active_competition(session)
    _require_simulator_access(user, competition)
    return await get_bracket_picks(session)
