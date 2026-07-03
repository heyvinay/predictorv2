"""What-if bracket simulator API routes.

Gating (v2.194.x): every route requires auth. The MASTER-SWITCH gate
(`competition.simulator_enabled`) applies to every INTERACTIVE route —
`/challenge` (GET + POST), `/run`, and `/bracket-picks`: a non-admin
caller is 403'd on all of them when the switch is off. Admins always
bypass the master switch (full access even when it's off). On top of
the master switch, `/run` and `/bracket-picks` additionally require the
non-admin caller to be unlocked (via the one-time trivia challenge),
and `/run` enforces the daily cap. `GET /status` is the ONE route that
stays reachable regardless of the switch — it's how the frontend learns
`feature_enabled` to decide whether to show the simulator at all.
"""

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.dependencies import CurrentUser, DbSession
from app.models.competition import Competition
from app.models.user import User
from app.schemas.simulator import (
    ChallengeAttempt,
    ChallengeQuestion,
    FiftyFiftyRequest,
    FiftyFiftyResponse,
    SimulatorPicksResponse,
    SimulatorStatus,
    UnlockResult,
)
from app.services.simulator import (
    get_bracket_picks,
    get_challenge_question,
    get_fifty_fifty,
    get_status,
    record_run,
    unlock,
)

router = APIRouter()


async def _get_active_competition(session: DbSession) -> Competition | None:
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    return result.scalar_one_or_none()


def _require_simulator_access(user: User, competition: Competition | None) -> None:
    """Master-switch gate shared by every INTERACTIVE simulator route.

    A non-admin caller may only interact with the simulator (challenge,
    run, bracket-picks) when the active competition's `simulator_enabled`
    is true. Admins always bypass — they retain full access even with the
    switch off. Raises 403 for a blocked non-admin; returns None otherwise.

    Deliberately NOT applied to `GET /status`: that endpoint must stay
    reachable so the frontend can read `feature_enabled` and decide
    whether to surface the simulator to the user at all.

    This is only the master-switch layer. The unlock + daily-cap checks
    live on top of it in `record_run` (for `/run`) and in the
    `simulator_unlocked` clause of `/bracket-picks`.
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
    """Current gating state for the caller: feature flag, unlock state,
    daily run usage/remaining, and next reset time.

    Always reachable — never master-switch-gated — so the frontend can
    read `feature_enabled` for a locked-out non-admin.
    """
    competition = await _get_active_competition(session)
    return await get_status(session, user, competition)


@router.get("/challenge", response_model=ChallengeQuestion)
async def simulator_challenge(
    session: DbSession,
    user: CurrentUser,
) -> ChallengeQuestion:
    """One trivia question for the unlock challenge. Never includes the
    answer key. Master-switch-gated for non-admins."""
    competition = await _get_active_competition(session)
    _require_simulator_access(user, competition)
    return get_challenge_question(user)


@router.post("/challenge", response_model=UnlockResult)
async def simulator_attempt_challenge(
    attempt: ChallengeAttempt,
    session: DbSession,
    user: CurrentUser,
) -> UnlockResult:
    """Submit an answer to the trivia challenge.

    Master-switch-gated for non-admins. Unlimited attempts, no lockout.
    On a correct + timely answer, `simulator_unlocked` flips permanently
    for this user.
    """
    competition = await _get_active_competition(session)
    _require_simulator_access(user, competition)

    unlocked = await unlock(
        session,
        user,
        question_id=attempt.question_id,
        answer_index=attempt.answer_index,
        elapsed_ms=attempt.elapsed_ms,
    )
    return UnlockResult(
        unlocked=unlocked,
        status=await get_status(session, user, competition),
    )


@router.post("/challenge/fifty-fifty", response_model=FiftyFiftyResponse)
async def simulator_fifty_fifty(
    body: FiftyFiftyRequest,
    session: DbSession,
    user: CurrentUser,
) -> FiftyFiftyResponse:
    """Spend the 50:50 lifeline on the current challenge question.

    Returns two option indexes that are NOT the correct answer, so the
    client can grey them out (and disable clicks) — the remaining pair
    still contains the correct answer, matching the classic game-show
    mechanic. `correct_index` never leaves the server; only wrong indexes
    do, so a two-index response still leaves a genuine two-way choice.

    Auth + master-switch gated like the other interactive routes; not
    rate-limited beyond the client's own once-per-attempt flag (calling
    it again returns the same deterministic pair — no leak surface).
    """
    competition = await _get_active_competition(session)
    _require_simulator_access(user, competition)
    wrong = get_fifty_fifty(body.question_id)
    if wrong is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown challenge question.",
        )
    return FiftyFiftyResponse(wrong_indexes=wrong)


@router.post("/run", response_model=SimulatorStatus)
async def simulator_run(
    session: DbSession,
    user: CurrentUser,
) -> SimulatorStatus:
    """Record one committed what-if simulator run against the caller's
    daily cap.

    Master-switch-gated for non-admins (403 when the switch is off).
    On top of that, raises 403 if a non-admin caller hasn't unlocked the
    simulator yet, or 429 (with a friendly `Retry-After` header) if
    they've hit `SIMULATOR_DAILY_CAP` for the day. Admins bypass all
    three checks but still have the run counted + audited.
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

    Access requires `user.is_admin OR (competition.simulator_enabled AND
    user.simulator_unlocked)` — admins always get through, even with the
    master switch off; everyone else needs both the feature flag on AND
    the one-time trivia unlock completed.
    """
    competition = await _get_active_competition(session)
    _require_simulator_access(user, competition)
    if not user.is_admin and not user.simulator_unlocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The bracket simulator isn't available to you yet.",
        )
    return await get_bracket_picks(session)
