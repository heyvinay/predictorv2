"""Entry-scoped prediction-write service.

This module is the single source of truth for prediction writes. Every
mutation goes through `_validate_writeable(...)` which enforces:

- entry ownership (caller must be the entry's user — admins do not edit
  on behalf of users; admin overrides happen at the entry-lifecycle level)
- entry not withdrawn (`withdrawn_at is None`)
- entry not disabled (`is_disabled is False`)
- phase status is DRAFT for the relevant phase (READY/SUBMITTED/LOCKED
  all reject writes; the user must reopen to draft first)
- phase deadline not passed (when set on the competition)
- (per-fixture writes only) fixture not individually locked

The service writes audit rows in the same DB transaction as the data
mutation — see `services/audit.py`. This guarantees the audit log is
exactly as complete as the state itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import aware_utc, utc_now
from app.models.bonus import BonusPrediction
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry
from app.models.fixture import Fixture
from app.models.prediction import (
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
    normalize_stage,
)
from app.models.user import User
from app.services.audit import AuditContext, record_audit_event
from app.services.scoring import eligible_entry_ids_select
from app.services.locking import check_fixture_locked, get_current_phase
from app.models.entry import ActorRole


# ---------------------------------------------------------------------------
# Exceptions — typed so the API layer can map to HTTP codes
# ---------------------------------------------------------------------------
class PredictionError(Exception):
    """Base for prediction-service errors."""


class PredictionAccessDeniedError(PredictionError):
    """Caller doesn't own the entry (admins can't write either)."""


class PredictionLockedError(PredictionError):
    """Phase/fixture/deadline lock blocks the write."""


class PredictionValidationError(PredictionError):
    """Out-of-range score, missing field, withdrawn/disabled entry, etc."""


# Maximum goals per side. Matches the frontend cap so the UX clip
# matches the backend reject.
SCORE_MAX = 15


# ---------------------------------------------------------------------------
# Validation core — called by every write path
# ---------------------------------------------------------------------------
async def _validate_writeable(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    phase: PredictionPhase,
    competition: Competition,
) -> None:
    """Raise the appropriate typed exception unless the entry is in a
    state that accepts prediction writes for `phase`."""
    if entry.user_id != user.id:
        raise PredictionAccessDeniedError(
            f"User {user.id} cannot write to entry {entry.id}"
        )
    if entry.withdrawn_at is not None:
        raise PredictionValidationError("Entry is withdrawn")
    if entry.is_disabled:
        raise PredictionValidationError("Entry is disabled")

    phase_row = next((p for p in entry.phases if p.phase == phase), None)
    if phase_row is None:
        raise PredictionValidationError(
            f"Entry has no record for phase {phase.value}"
        )
    if phase_row.status != EntryStatus.DRAFT:
        raise PredictionLockedError(
            f"Phase {phase.value} is in status {phase_row.status.value}; "
            "predictions can only be edited in draft"
        )

    # Phase deadline gate — the wider lock that catches the whole phase
    # closing even before the user has explicitly submitted.
    deadline = (
        competition.phase1_deadline
        if phase == PredictionPhase.PHASE_1
        else competition.phase2_deadline
    )
    if deadline is not None and aware_utc(utc_now()) >= aware_utc(deadline):
        raise PredictionLockedError(
            f"Phase {phase.value} deadline has passed"
        )


def _validate_score(home: int, away: int) -> None:
    """Both scores must be 0..SCORE_MAX inclusive."""
    if not (0 <= home <= SCORE_MAX and 0 <= away <= SCORE_MAX):
        raise PredictionValidationError(
            f"Scores must be between 0 and {SCORE_MAX} inclusive"
        )


# ---------------------------------------------------------------------------
# Match predictions
# ---------------------------------------------------------------------------
async def get_match_predictions(
    session: AsyncSession, *, entry: PredictionEntry
) -> list[tuple[MatchPrediction, Fixture]]:
    """All match predictions for this entry, joined with their fixtures.

    Returns (prediction, fixture) tuples ordered by kickoff.
    """
    result = await session.execute(
        select(MatchPrediction, Fixture)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .where(MatchPrediction.entry_id == entry.id)
        .order_by(Fixture.kickoff)
    )
    return list(result.all())


async def upsert_match_prediction(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    fixture_id: uuid.UUID,
    home_score: int,
    away_score: int,
    ctx: AuditContext | None = None,
) -> MatchPrediction:
    """Insert-or-update one match prediction for `entry`.

    Enforces all lock rules. Writes a `prediction.match_upserted` audit
    row with old / new score values (or None for the old when this is
    a fresh insert).
    """
    _validate_score(home_score, away_score)

    # Load fixture so we can lock-check it before any state mutation.
    fixture = (
        await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    ).scalar_one_or_none()
    if fixture is None:
        raise PredictionValidationError(f"Fixture {fixture_id} not found")
    if check_fixture_locked(fixture):
        raise PredictionLockedError(
            f"Fixture {fixture_id} is locked (within 5 min of kickoff)"
        )

    current_phase = await get_current_phase(session)
    await _validate_writeable(
        session,
        entry=entry,
        user=user,
        phase=current_phase,
        competition=competition,
    )

    existing = (
        await session.execute(
            select(MatchPrediction).where(
                MatchPrediction.entry_id == entry.id,
                MatchPrediction.fixture_id == fixture_id,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        prediction = MatchPrediction(
            entry_id=entry.id,
            fixture_id=fixture_id,
            home_score=home_score,
            away_score=away_score,
            phase=current_phase,
        )
        session.add(prediction)
        old_home: int | None = None
        old_away: int | None = None
    else:
        old_home = existing.home_score
        old_away = existing.away_score
        existing.home_score = home_score
        existing.away_score = away_score
        existing.phase = current_phase
        existing.updated_at = utc_now()
        prediction = existing

    record_audit_event(
        session,
        event_type="prediction.match_upserted",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={
            "entry_reference": entry.reference,
            "fixture_id": str(fixture_id),
            "phase": current_phase.value,
            "old_home": old_home,
            "old_away": old_away,
            "new_home": home_score,
            "new_away": away_score,
        },
    )

    await session.flush()
    return prediction


async def batch_upsert_match_predictions(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    items: Iterable[tuple[uuid.UUID, int, int]],
    ctx: AuditContext | None = None,
) -> list[MatchPrediction]:
    """Upsert many match predictions. Skips fixtures that don't exist
    or are individually locked (preserving the legacy batch behaviour).

    Writes ONE `prediction.match_batch_upserted` event with all changes
    summarized, so a user saving 60 group-stage picks doesn't generate
    60 audit rows.
    """
    current_phase = await get_current_phase(session)
    await _validate_writeable(
        session,
        entry=entry,
        user=user,
        phase=current_phase,
        competition=competition,
    )

    results: list[MatchPrediction] = []
    changes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for fixture_id, home, away in items:
        # Range-check each item up front; one bad item fails the batch.
        _validate_score(home, away)

        fixture = (
            await session.execute(
                select(Fixture).where(Fixture.id == fixture_id)
            )
        ).scalar_one_or_none()
        if fixture is None:
            skipped.append(
                {"fixture_id": str(fixture_id), "reason": "fixture_not_found"}
            )
            continue
        if check_fixture_locked(fixture):
            skipped.append(
                {"fixture_id": str(fixture_id), "reason": "fixture_locked"}
            )
            continue

        existing = (
            await session.execute(
                select(MatchPrediction).where(
                    MatchPrediction.entry_id == entry.id,
                    MatchPrediction.fixture_id == fixture_id,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            pred = MatchPrediction(
                entry_id=entry.id,
                fixture_id=fixture_id,
                home_score=home,
                away_score=away,
                phase=current_phase,
            )
            session.add(pred)
            changes.append(
                {
                    "fixture_id": str(fixture_id),
                    "old_home": None,
                    "old_away": None,
                    "new_home": home,
                    "new_away": away,
                }
            )
            results.append(pred)
        else:
            if existing.home_score == home and existing.away_score == away:
                # No-op upsert — don't audit it.
                results.append(existing)
                continue
            changes.append(
                {
                    "fixture_id": str(fixture_id),
                    "old_home": existing.home_score,
                    "old_away": existing.away_score,
                    "new_home": home,
                    "new_away": away,
                }
            )
            existing.home_score = home
            existing.away_score = away
            existing.phase = current_phase
            existing.updated_at = utc_now()
            results.append(existing)

    record_audit_event(
        session,
        event_type="prediction.match_batch_upserted",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={
            "entry_reference": entry.reference,
            "phase": current_phase.value,
            "count_changed": len(changes),
            "count_skipped": len(skipped),
            "changes": changes,
            "skipped": skipped,
        },
    )

    await session.flush()
    return results


# ---------------------------------------------------------------------------
# Bracket / team predictions
# ---------------------------------------------------------------------------
async def get_bracket_predictions(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    phase: PredictionPhase,
) -> list[TeamPrediction]:
    """All bracket picks for this entry filtered by phase."""
    result = await session.execute(
        select(TeamPrediction)
        .where(TeamPrediction.entry_id == entry.id)
        .where(TeamPrediction.phase == phase)
    )
    return list(result.scalars().all())


async def replace_bracket_predictions(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    picks: list[dict[str, Any]],
    ctx: AuditContext | None = None,
) -> list[TeamPrediction]:
    """Replace this entry's bracket picks for the CURRENT phase.

    Picks for the OTHER phase are untouched — phase_1 and phase_2 bracket
    picks are independent (a user re-predicts after group stage).

    `picks` is a list of dicts with keys `team`, `stage`, `group_position`
    (the last optional).
    """
    current_phase = await get_current_phase(session)
    await _validate_writeable(
        session,
        entry=entry,
        user=user,
        phase=current_phase,
        competition=competition,
    )

    # Clear existing picks for this entry + phase only.
    await session.execute(
        delete(TeamPrediction)
        .where(TeamPrediction.entry_id == entry.id)
        .where(TeamPrediction.phase == current_phase)
    )

    new_rows: list[TeamPrediction] = []
    # De-dupe AFTER normalization: a stale cached frontend bundle may send
    # plural stage spellings ("quarter_finals") alongside the canonical
    # singular — both normalize to the same row and would violate the
    # uq_team_pred_entry_phase_team_stage unique constraint on insert.
    seen: set[tuple[str, str, int | None]] = set()
    for pick in picks:
        team = pick.get("team")
        stage = normalize_stage(pick.get("stage") or "")
        group_position = pick.get("group_position")
        if not team or not stage:
            # Skip ill-formed picks rather than fail the whole replace.
            continue
        key = (team, stage, group_position)
        if key in seen:
            continue
        seen.add(key)
        row = TeamPrediction(
            entry_id=entry.id,
            team=team,
            stage=stage,
            group_position=group_position,
            phase=current_phase,
        )
        session.add(row)
        new_rows.append(row)

    record_audit_event(
        session,
        event_type="prediction.bracket_replaced",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={
            "entry_reference": entry.reference,
            "phase": current_phase.value,
            "count": len(new_rows),
            # Summarized picks payload — full list, but compact.
            "picks_summary": [
                {
                    "team": r.team,
                    "stage": r.stage,
                    "group_position": r.group_position,
                }
                for r in new_rows
            ],
        },
    )

    await session.flush()
    return new_rows


# ---------------------------------------------------------------------------
# Bonus predictions
# ---------------------------------------------------------------------------
async def get_bonus_predictions(
    session: AsyncSession, *, entry: PredictionEntry
) -> list[BonusPrediction]:
    """All bonus picks for this entry."""
    result = await session.execute(
        select(BonusPrediction).where(BonusPrediction.entry_id == entry.id)
    )
    return list(result.scalars().all())


async def upsert_bonus_predictions(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    user: User,
    competition: Competition,
    picks: Iterable[tuple[str, str]],
    valid_question_ids: set[str],
    ctx: AuditContext | None = None,
) -> list[BonusPrediction]:
    """Upsert bonus picks for this entry.

    Bonus picks lock with phase_1 (per existing behaviour). Unknown
    question_ids are silently skipped (defends against YAML edits that
    rename questions). Empty answers DELETE the prediction so users
    can clear unwanted picks.

    `picks` is an iterable of (question_id, answer) tuples.
    """
    # Bonus is bound to phase_1 — same status gate.
    await _validate_writeable(
        session,
        entry=entry,
        user=user,
        phase=PredictionPhase.PHASE_1,
        competition=competition,
    )

    # Load existing rows in one query for upsert.
    existing_rows = (
        await session.execute(
            select(BonusPrediction).where(BonusPrediction.entry_id == entry.id)
        )
    ).scalars().all()
    by_qid: dict[str, BonusPrediction] = {p.question_id: p for p in existing_rows}

    changes: list[dict[str, Any]] = []
    for qid, raw_answer in picks:
        if qid not in valid_question_ids:
            continue
        existing = by_qid.get(qid)
        clean = (raw_answer or "").strip()
        if not clean:
            # Empty → delete the pick.
            if existing is not None:
                changes.append(
                    {"question_id": qid, "old": existing.answer, "new": None}
                )
                await session.delete(existing)
            continue
        if existing is not None:
            if existing.answer == clean:
                continue
            changes.append(
                {"question_id": qid, "old": existing.answer, "new": clean}
            )
            existing.answer = clean
            existing.updated_at = utc_now()
        else:
            changes.append({"question_id": qid, "old": None, "new": clean})
            session.add(
                BonusPrediction(
                    entry_id=entry.id, question_id=qid, answer=clean
                )
            )

    record_audit_event(
        session,
        event_type="prediction.bonus_upserted",
        actor_user_id=user.id,
        actor_role=ActorRole.USER,
        subject_type="entry",
        subject_id=entry.id,
        ctx=ctx,
        metadata={
            "entry_reference": entry.reference,
            "count_changed": len(changes),
            "changes": changes,
        },
    )

    await session.flush()
    refreshed = (
        await session.execute(
            select(BonusPrediction).where(BonusPrediction.entry_id == entry.id)
        )
    ).scalars().all()
    return list(refreshed)


# ---------------------------------------------------------------------------
# Per-entry agreements
# ---------------------------------------------------------------------------
async def compute_agreements(
    session: AsyncSession,
    *,
    entry: PredictionEntry,
    fixture_ids: list[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    """Per-fixture agreement counts vs THIS entry's picks.

    Privacy: only counts are returned, never individual picks. Counts are
    computed relative to the calling entry's own pick.

    Returns: list of dicts {fixture_id, agrees_exact, agrees_outcome, total}.
    """
    # Calling entry's picks for the requested fixtures.
    my_q = select(MatchPrediction).where(MatchPrediction.entry_id == entry.id)
    if fixture_ids:
        my_q = my_q.where(MatchPrediction.fixture_id.in_(fixture_ids))
    my_preds = {
        p.fixture_id: p
        for p in (await session.execute(my_q)).scalars().all()
    }
    if not my_preds:
        return []

    # Eligible entries only — keeps the Results-card rarity projection in
    # step with what scoring actually pays (same filter as
    # scoring.get_all_outcome_counts).
    relevant_ids = list(my_preds.keys())
    all_preds = (
        await session.execute(
            select(MatchPrediction).where(
                MatchPrediction.fixture_id.in_(relevant_ids),
                MatchPrediction.entry_id.in_(eligible_entry_ids_select()),
            )
        )
    ).scalars().all()

    by_fixture: dict[uuid.UUID, list[MatchPrediction]] = {}
    for p in all_preds:
        by_fixture.setdefault(p.fixture_id, []).append(p)

    def _sign(h: int, a: int) -> int:
        if h > a:
            return 1
        if h < a:
            return -1
        return 0

    out: list[dict[str, Any]] = []
    for fixture_id, my in my_preds.items():
        my_sign = _sign(my.home_score, my.away_score)
        preds = by_fixture.get(fixture_id, [])
        exact = sum(
            1
            for p in preds
            if p.home_score == my.home_score and p.away_score == my.away_score
        )
        outcome = sum(
            1 for p in preds if _sign(p.home_score, p.away_score) == my_sign
        )
        out.append(
            {
                "fixture_id": fixture_id,
                "agrees_exact": exact,
                "agrees_outcome": outcome,
                "total": len(preds),
            }
        )
    return out


def compute_points_for_finished_fixtures(
    pred_fixture_pairs,
    agreements_by_fixture: dict,
    scoring_config: dict,
):
    """Compute PickPointsOut for each (pred, fixture) where the fixture is
    FINISHED and has a score row. Returns a map from fixture_id → PickPointsOut.

    Caller is responsible for the bulk-agreement fetch — pass the already-
    computed map keyed by fixture_id. Per-fixture absence is treated as
    {agrees_exact: 0, agrees_outcome: 0, total: 0}.
    """
    from app.schemas.prediction import PickPointsOut
    from app.services.scoring import compute_match_points

    match_cfg = scoring_config.get("match", {})
    outcome_points = int(match_cfg.get("correct_outcome", 5))
    exact_points = int(match_cfg.get("exact_score", 10))
    rarity_cap = int(match_cfg.get("rarity_cap", match_cfg.get("hybrid_cap", 10)))
    mode = str(scoring_config.get("mode", "logarithmic"))

    out: dict = {}
    for pred, fixture in pred_fixture_pairs:
        # status may be a MatchStatus(str, Enum) or a plain string — unwrap
        # .value first: str(MatchStatus.FINISHED) is "MatchStatus.FINISHED"
        # on Python 3.11, which would silently skip every finished fixture.
        status_value = getattr(fixture.status, "value", fixture.status)
        if str(status_value).lower() != "finished":
            continue
        if fixture.score is None:
            continue
        agr = agreements_by_fixture.get(fixture.id, {})
        total_predictors = int(agr.get("total", 0))
        correct_predictors = int(agr.get("agrees_outcome", 0))

        total, correct_outcome, exact_score = compute_match_points(
            mode=mode,
            predicted_home=pred.home_score,
            predicted_away=pred.away_score,
            actual_home=fixture.score.home_score,
            actual_away=fixture.score.away_score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=outcome_points,
            exact_points=exact_points,
            cap=rarity_cap,
        )

        if exact_score:
            base_kind = "exact"
            base = outcome_points + exact_points
        elif correct_outcome:
            base_kind = "result"
            base = outcome_points
        else:
            base_kind = "miss"
            base = 0

        rarity = total - base
        out[fixture.id] = PickPointsOut(
            base=base, base_kind=base_kind, rarity=rarity, total=total
        )

    return out
