"""Group Stage Winner data — single payload for both the dashboard card
and the GROUP_STAGE_FINAL broadcast email.

Computes the winner from `calculate_leaderboard` (phase_1 filter) and
folds in the four-part points breakdown that the card displays:

  1. Points from Correct Match Outcomes → phase1.match_outcome_points
  2. Extra Points from Exact Score      → phase1.exact_score_points
  3. Extra Points from Rarity           → phase1.hybrid_bonus_points
  4. Points from Bonus Questions        → breakdown.bonus_question_points

The four bullets sum to total_points (phase2 is dormant per CLAUDE.md
single-phase invariant, so phase1.total + bonus_question_points = total).

Story-line composition (v2.181.0) ALSO runs server-side so card and email
render the same prose. The narrative picks one of five templates keyed
on *lead pattern* (wire-to-wire / dominant / steady / late surge /
sneaked in), plus a margin beat (gap vs runner-up) and a bracket beat
(champion pick + finalists alive). Edits to the wording live here only;
both surfaces re-render on next request.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import utc_now
from app.services.leaderboard import calculate_leaderboard


@dataclass(frozen=True)
class GroupStageWinner:
    """Winner payload — flat, JSON-serialisable, mirrors the
    `GroupStageWinnerResponse` Pydantic schema field-for-field.
    """

    entry_id: str
    user_name: str
    entry_name: str
    total_points: int
    final_rank: int

    # 4-part breakdown (sums to total_points)
    outcome_points: int
    exact_score_extra: int
    rarity_extra: int
    bonus_question_points: int

    # Story stats
    correct_outcomes: int
    exact_scores: int
    days_at_top: int
    champion_pick: str | None
    champion_alive: bool
    finalist_picks: list[str]
    finalists_alive: int

    # Context facts that power the narrative (v2.181.0)
    runner_up_name: str | None
    runner_up_gap: int | None
    total_days: int

    # Pre-composed narrative — card and email both render this string
    # verbatim. Edit `_compose_story_line` below to change wording.
    story_line: str

    generated_at: datetime


# ---------------------------------------------------------------------------
# Narrative helpers — pure functions, easy to tweak in isolation
# ---------------------------------------------------------------------------
def _oxford_join(items: list[str]) -> str:
    """Comma-and joiner. Handles 0/1/2/3+ items naturally."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _lead_beat(days_at_top: int, total_days: int, name: str) -> str:
    """Opening sentence — picks template by lead pattern.

    days_at_top is COUNT(DISTINCT captured_date WHERE position=1) for
    this winner. total_days is COUNT(DISTINCT captured_date) for the
    whole snapshot table — the tournament's lived duration.
    """
    if total_days <= 0:
        return f"{name} took the group stage"
    if days_at_top >= total_days:
        return (
            f"{name} led this group stage from start to finish — "
            f"#1 every single day across the {total_days}-day window"
        )
    if days_at_top == 1:
        return (
            f"A patient climb that paid off — {name} reached #1 only "
            "on the final day of the group stage"
        )
    ratio = days_at_top / total_days
    if ratio >= 0.6:
        return (
            f"{name} dominated the group stage — holding #1 on "
            f"{days_at_top} of the {total_days} tournament days"
        )
    if ratio >= 0.25:
        return (
            f"{name} took the group stage on a steady run — leading the "
            f"pool on {days_at_top} of the {total_days} tournament days"
        )
    return (
        f"{name} sealed the group stage on a late charge — leading "
        f"the pool on only {days_at_top} of the {total_days} days but "
        "timing the climb to perfection"
    )


def _margin_clause(gap: int | None, runner_up_name: str | None) -> str | None:
    """Comma-joinable margin phrase, lowercase to attach onto the lead.

    Returns None if we don't have runner-up data (single-entry pool, or
    the snapshot/leaderboard query missed it).
    """
    if runner_up_name is None or gap is None:
        return None
    if gap == 0:
        return (
            f"tied with {runner_up_name} on points but took the spot on "
            "the tiebreaker"
        )
    if gap >= 15:
        return f"finishing {gap} points clear of {runner_up_name}"
    if gap >= 5:
        return f"edging {runner_up_name} by {gap} points"
    if gap == 1:
        return f"just 1 point clear of {runner_up_name}"
    return f"just {gap} points clear of {runner_up_name}"


def _bracket_sentence(
    champion_pick: str | None,
    champion_alive: bool,
    finalist_picks: list[str],
    finalists_alive: int,
) -> str | None:
    """Standalone sentence about the winner's bracket picks heading
    into the knockouts. Returns None if we have no bracket data.

    Avoids defeated framings where possible — celebrates what's still
    in play, only mentions eliminations when relevant context.
    """
    n_finalists = len(finalist_picks)

    # No data at all
    if not champion_pick and n_finalists == 0:
        return None

    # Only finalist data, no champion
    if not champion_pick:
        if finalists_alive == 0:
            return "Their finalists are already out of the bracket — the knockout run will need late drama."
        if finalists_alive == n_finalists:
            joined = _oxford_join(finalist_picks)
            label = "Both finalists" if n_finalists == 2 else f"All {n_finalists} of their finalists"
            return f"{label} ({joined}) are still alive in the knockouts."
        return (
            f"{finalists_alive} of their {n_finalists} finalist picks remain "
            "alive heading into the knockouts."
        )

    # Champion + (maybe) finalists
    champ_in_finalists = champion_pick in finalist_picks
    other_finalists = [t for t in finalist_picks if t != champion_pick]

    if n_finalists == 0:
        # Champion only
        if champion_alive:
            return (
                f"Their champion pick {champion_pick} carries the bracket "
                "bid into the knockouts."
            )
        return (
            f"Their champion pick {champion_pick} has already exited the "
            "bracket — the knockout run will need late drama."
        )

    # Both champion + finalists. If champion is also a finalist, mention
    # the other finalists separately to avoid double-counting Spain
    # twice in one sentence.
    if champion_alive and finalists_alive == n_finalists:
        # Everything alive
        if champ_in_finalists and other_finalists:
            other_phrase = _oxford_join(other_finalists)
            count_word = "the other finalist" if len(other_finalists) == 1 else "the other finalists"
            return (
                f"Their champion pick {champion_pick} is alive and so is "
                f"{count_word} they backed ({other_phrase}) — the full "
                "bracket bid carries forward."
            )
        joined = _oxford_join(finalist_picks)
        label = "Both finalists" if n_finalists == 2 else f"All {n_finalists} finalists"
        return (
            f"{label} ({joined}) are still alive, and their champion pick "
            f"{champion_pick} carries the run into the knockouts."
        )

    if champion_alive and finalists_alive > 0:
        return (
            f"{finalists_alive} of their {n_finalists} finalist picks remain "
            f"alive, with champion pick {champion_pick} carrying the "
            "bracket bid forward."
        )

    if champion_alive and finalists_alive == 0:
        return (
            f"Their other finalist picks are already out, but champion "
            f"pick {champion_pick} keeps the knockout hopes alive."
        )

    if not champion_alive and finalists_alive > 0:
        return (
            f"{finalists_alive} of {n_finalists} finalists are still alive, "
            f"though their champion pick {champion_pick} has already exited."
        )

    # Everything eliminated
    return (
        f"Their bracket picks have taken early hits — champion pick "
        f"{champion_pick} and every finalist are already out of the "
        "knockouts."
    )


def _compose_story_line(
    *,
    name: str,
    days_at_top: int,
    total_days: int,
    runner_up_name: str | None,
    runner_up_gap: int | None,
    champion_pick: str | None,
    champion_alive: bool,
    finalist_picks: list[str],
    finalists_alive: int,
) -> str:
    """Top-level narrative assembler — 2-3 sentences of prose.

    Lead + margin combine into one sentence with a comma; bracket gets
    its own sentence. Keep this function as the SOLE editor for wording
    changes — card, email, and tests all read the same string.
    """
    lead = _lead_beat(days_at_top, total_days, name)
    margin = _margin_clause(runner_up_gap, runner_up_name)
    bracket = _bracket_sentence(
        champion_pick, champion_alive, finalist_picks, finalists_alive
    )

    sentence_1 = f"{lead}, {margin}." if margin else f"{lead}."
    if bracket:
        return f"{sentence_1} {bracket}"
    return sentence_1


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
async def get_group_stage_winner(session: AsyncSession) -> GroupStageWinner | None:
    """Compute the Group Stage winner from the cached phase_1 leaderboard.

    Returns None only if the pool has zero eligible entries (defensive
    guard — shouldn't happen post-tournament). The release-flag gate
    lives at the API layer; the service itself is unconditional so
    test sends + admin previews can still inspect the payload.
    """
    lb = await calculate_leaderboard(session, phase="phase_1")
    if not lb.entries:
        return None
    winner = lb.entries[0]
    phase1 = winner.breakdown.phase1

    # Runner-up context — None if the pool has only one eligible entry.
    runner_up_name: str | None = None
    runner_up_gap: int | None = None
    if len(lb.entries) >= 2:
        runner_up = lb.entries[1]
        runner_up_name = runner_up.user_name
        runner_up_gap = winner.total_points - runner_up.total_points

    # Days-at-top: COUNT distinct snapshot dates where this entry was
    # at position 1. Captures dominance ("held #1 for N of M days")
    # vs squeaked-in-at-the-end ("hit #1 only on the final day").
    days_sql = text(
        """
        SELECT COUNT(DISTINCT captured_date) AS days
        FROM leaderboard_snapshots
        WHERE entry_id = :entry_id
          AND position = 1
        """
    )
    try:
        row = (await session.execute(days_sql, {"entry_id": winner.entry_id})).first()
        days_at_top = int(row.days or 0) if row else 0
    except Exception:  # noqa: BLE001 — story stat must not fail the payload
        days_at_top = 0

    # Total tournament days — COUNT distinct snapshot dates across the
    # whole table. Defines the denominator for the lead beat templates.
    total_days_sql = text(
        "SELECT COUNT(DISTINCT captured_date) AS days FROM leaderboard_snapshots"
    )
    try:
        row = (await session.execute(total_days_sql)).first()
        total_days = int(row.days or 0) if row else 0
    except Exception:  # noqa: BLE001
        total_days = 0

    finalist_picks_list = list(winner.finalist_picks or [])

    story_line = _compose_story_line(
        name=winner.user_name,
        days_at_top=days_at_top,
        total_days=total_days,
        runner_up_name=runner_up_name,
        runner_up_gap=runner_up_gap,
        champion_pick=winner.champion_pick,
        champion_alive=winner.champion_alive,
        finalist_picks=finalist_picks_list,
        finalists_alive=winner.finalists_alive,
    )

    return GroupStageWinner(
        entry_id=str(winner.entry_id),
        user_name=winner.user_name,
        entry_name=winner.entry_name,
        total_points=winner.total_points,
        final_rank=winner.position,
        outcome_points=phase1.match_outcome_points,
        exact_score_extra=phase1.exact_score_points,
        rarity_extra=phase1.hybrid_bonus_points,
        bonus_question_points=winner.breakdown.bonus_question_points,
        correct_outcomes=winner.correct_outcomes,
        exact_scores=winner.exact_scores,
        days_at_top=days_at_top,
        champion_pick=winner.champion_pick,
        champion_alive=winner.champion_alive,
        finalist_picks=finalist_picks_list,
        finalists_alive=winner.finalists_alive,
        runner_up_name=runner_up_name,
        runner_up_gap=runner_up_gap,
        total_days=total_days,
        story_line=story_line,
        generated_at=utc_now(),
    )
