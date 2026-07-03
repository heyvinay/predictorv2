"""What-if bracket simulator service.

Bulk-loads every eligible entry's full knockout picks + frozen group
points + current standing in a handful of queries, so the frontend can
re-rank the field client-side as the user hypothetically resolves
remaining knockout fixtures — no per-tweak round trip.

Also owns the GATING layer (v2.194.x): a one-time game-show trivia
unlock (permanent per user), a daily cap of committed runs, and an
admin master switch. Admins bypass the unlock + cap entirely and
retain full access even when the master switch is off; admin usage is
still counted + audited, just uncapped.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import aware_utc, utc_now
from app.models.competition import Competition
from app.models.entry import ActorRole
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.user import User
from app.schemas.simulator import (
    ChallengeQuestion,
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
    """Every eligible entry's knockout picks + frozen group points + current
    total/position, in ~3-4 queries total:

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
                picks=picks,
            )
        )

    return SimulatorPicksResponse(
        entries=entries,
        last_calculated=aware_utc(board.last_calculated) or utc_now(),
    )


# ===========================================================================
# Gating (v2.194.x) — trivia unlock + daily cap + admin master switch.
# ===========================================================================

# Committed simulator runs a non-admin user may record per UTC day. Admins
# are exempt from this cap entirely (see record_run).
SIMULATOR_DAILY_CAP = 3

# Trivia bank for the one-time unlock challenge. `correct_index` never
# leaves the server — ChallengeQuestion (the API response shape) omits it
# entirely by construction.
_TRIVIA_QUESTIONS: list[dict] = [
    {
        "id": "wc-1930-winner",
        "question": "Which country won the first-ever FIFA World Cup in 1930?",
        "options": ["Brazil", "Argentina", "Uruguay", "Italy"],
        "correct_index": 2,
    },
    {
        "id": "wc-most-titles",
        "question": "Which country has won the most FIFA World Cup titles?",
        "options": ["Germany", "Brazil", "Italy", "Argentina"],
        "correct_index": 1,
    },
    {
        "id": "wc-2022-host",
        "question": "Which country hosted the 2022 FIFA World Cup?",
        "options": ["United Arab Emirates", "Qatar", "Saudi Arabia", "Kuwait"],
        "correct_index": 1,
    },
    {
        "id": "wc-players-per-side",
        "question": "How many players (including the goalkeeper) does each "
        "team have on the pitch at kickoff?",
        "options": ["9", "10", "11", "12"],
        "correct_index": 2,
    },
    {
        "id": "wc-2026-hosts",
        "question": "The 2026 FIFA World Cup is being co-hosted by the USA, "
        "Mexico, and which other country?",
        "options": ["Canada", "Costa Rica", "Panama", "Jamaica"],
        "correct_index": 0,
    },
]

# Max time allowed to answer the challenge, in milliseconds. Deliberately
# generous for a 4-option multiple-choice question while still ruling out
# "left the tab open and came back an hour later."
CHALLENGE_TIME_LIMIT_MS = 15_000


def get_challenge_question(user: User) -> ChallengeQuestion:
    """Pick a trivia question deterministically for `user`.

    Deterministic within a given `simulator_runs_used` count so repeated
    `GET /simulator/challenge` calls before an answer is submitted return
    the same question (no reshuffling mid-attempt), while different users
    — and the same user across days as their run count changes — see
    variety. Uses the user id together with the run counter rather than
    `random` so behaviour is reproducible in tests.
    """
    seed = user.id.int + user.simulator_runs_used
    q = _TRIVIA_QUESTIONS[seed % len(_TRIVIA_QUESTIONS)]
    return ChallengeQuestion(
        question_id=q["id"],
        question=q["question"],
        options=list(q["options"]),
    )


def _find_question(question_id: str) -> dict | None:
    for q in _TRIVIA_QUESTIONS:
        if q["id"] == question_id:
            return q
    return None


def verify_challenge(question_id: str, answer_index: int, elapsed_ms: int) -> bool:
    """True iff `answer_index` is correct for `question_id` AND the
    attempt was submitted within `CHALLENGE_TIME_LIMIT_MS`."""
    if elapsed_ms is None or elapsed_ms > CHALLENGE_TIME_LIMIT_MS or elapsed_ms < 0:
        return False
    question = _find_question(question_id)
    if question is None:
        return False
    return answer_index == question["correct_index"]


def _apply_daily_reset(user: User) -> None:
    """Reset the daily run counter if the last reset wasn't today (UTC).

    Does NOT commit — callers are expected to commit alongside whatever
    else they're doing in the same request (status read, run record, or
    unlock). `simulator_runs_reset_at` is tz-aware; `aware_utc()` guards
    against the aiosqlite tzinfo-strip-on-read gotcha in tests.
    """
    now = utc_now()
    last_reset = aware_utc(user.simulator_runs_reset_at)
    if last_reset is None or last_reset.date() < now.date():
        user.simulator_runs_used = 0
        user.simulator_runs_reset_at = now


def _runs_remaining(user: User) -> int | None:
    """`None` (unlimited) for admins, else the non-negative remainder."""
    if user.is_admin:
        return None
    return max(0, SIMULATOR_DAILY_CAP - user.simulator_runs_used)


async def get_status(
    session: AsyncSession, user: User, competition: Competition | None
) -> SimulatorStatus:
    """Current gating state for `user`, applying the daily reset first.

    Callers must commit the session afterwards if `user` was mutated by
    the reset (both HTTP handlers below do so via their own commit or by
    delegating to `record_run`/`unlock`, which always commit).
    """
    _apply_daily_reset(user)
    await session.commit()

    feature_enabled = bool(competition.simulator_enabled) if competition else False
    unlocked = True if user.is_admin else user.simulator_unlocked

    return SimulatorStatus(
        feature_enabled=feature_enabled,
        unlocked=unlocked,
        is_admin=user.is_admin,
        runs_used=user.simulator_runs_used,
        runs_remaining=_runs_remaining(user),
        cap=SIMULATOR_DAILY_CAP,
        reset_at=user.simulator_runs_reset_at,
    )


async def record_run(session: AsyncSession, user: User) -> SimulatorStatus:
    """Record one committed simulator run against `user`'s daily cap.

    Enforcement (admins bypass both checks — see module docstring):
    - non-admin must be unlocked (`simulator_unlocked=True`), else 403.
    - non-admin must be under `SIMULATOR_DAILY_CAP` for today, else 429.

    Every successful call increments `simulator_runs_used`, stamps
    `simulator_runs_reset_at`, records a `feature.simulator_run` audit
    event, and commits — including for admins, whose usage is still
    counted + audited even though it's never capped.
    """
    _apply_daily_reset(user)

    if not user.is_admin:
        if not user.simulator_unlocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Answer the trivia challenge to unlock the bracket simulator.",
            )
        if user.simulator_runs_used >= SIMULATOR_DAILY_CAP:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Daily simulator limit reached ({SIMULATOR_DAILY_CAP} runs). "
                    "Try again after midnight UTC."
                ),
                headers={"Retry-After": str(_seconds_until_utc_midnight())},
            )

    user.simulator_runs_used += 1
    user.simulator_runs_reset_at = utc_now()

    record_audit_event(
        session,
        event_type="feature.simulator_run",
        actor_user_id=user.id,
        actor_role=ActorRole.ADMIN if user.is_admin else ActorRole.USER,
        subject_type="user",
        subject_id=user.id,
        metadata={"runs_used": user.simulator_runs_used, "is_admin": user.is_admin},
    )
    await session.commit()

    return SimulatorStatus(
        feature_enabled=True,
        unlocked=True,
        is_admin=user.is_admin,
        runs_used=user.simulator_runs_used,
        runs_remaining=_runs_remaining(user),
        cap=SIMULATOR_DAILY_CAP,
        reset_at=user.simulator_runs_reset_at,
    )


def _seconds_until_utc_midnight() -> int:
    """Whole seconds remaining until the next UTC daily reset boundary."""
    now = utc_now()
    next_midnight = datetime.combine(
        now.date(), datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(days=1)
    return max(0, int((next_midnight - now).total_seconds()))


async def unlock(
    session: AsyncSession,
    user: User,
    *,
    question_id: str,
    answer_index: int,
    elapsed_ms: int,
) -> bool:
    """Attempt to permanently unlock the simulator for `user`.

    Unlimited attempts, no lockout — wrong or late answers just return
    False so the frontend can re-serve a (possibly new) challenge. On
    success, `simulator_unlocked` is set permanently and a
    `feature.simulator_unlocked` audit event is recorded. Always commits
    (both branches leave the session in a clean, persisted state).
    """
    correct = verify_challenge(question_id, answer_index, elapsed_ms)
    if correct:
        user.simulator_unlocked = True
        record_audit_event(
            session,
            event_type="feature.simulator_unlocked",
            actor_user_id=user.id,
            actor_role=ActorRole.ADMIN if user.is_admin else ActorRole.USER,
            subject_type="user",
            subject_id=user.id,
            metadata={"question_id": question_id, "elapsed_ms": elapsed_ms},
        )
    await session.commit()
    return correct
