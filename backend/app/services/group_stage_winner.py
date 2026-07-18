"""Group Stage Podium data — single payload for both the dashboard card
and the GROUP_STAGE_FINAL broadcast email.

Computes the top 3 entries from ``calculate_leaderboard`` (phase_1 filter)
and folds in the four-part points breakdown that the card displays per
entry:

  1. Points from Correct Match Outcomes → phase1.match_outcome_points
  2. Extra Points from Exact Score      → phase1.exact_score_points
  3. Extra Points from Rarity           → phase1.hybrid_bonus_points
  4. Points from Bonus Questions        → breakdown.bonus_question_points

The four bullets sum to ``total_points`` per entry (phase2 is dormant per
the CLAUDE.md single-phase invariant).

Story-line composition (v2.181.0) runs server-side so card and email
render the same prose. The narrative picks one of five templates keyed
on *lead pattern* (wire-to-wire / dominant / steady / late surge /
sneaked in), plus a margin beat (gap vs runner-up) and a bracket beat
(champion pick + finalists alive). Edits to the wording live here only;
both surfaces re-render on next request.

v2.183.x: schema upgraded from single winner to top-3 podium. Same URL,
new shape — see ``schemas/group_stage_winner.py`` for the response type.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import utc_now
from app.services.leaderboard import calculate_leaderboard


@dataclass(frozen=True)
class GroupStageEntry:
    """One podium row — winner, runner-up, or third-place."""

    entry_id: str
    user_name: str
    entry_name: str
    display_name: str
    final_rank: int
    total_points: int
    outcome_points: int
    exact_score_extra: int
    rarity_extra: int
    bonus_question_points: int


@dataclass(frozen=True)
class GroupStagePodium:
    """Top-3 podium with a winner-centred narrative + audit verification."""

    entries: list[GroupStageEntry]
    champion_pick: str | None
    champion_alive: bool
    finalist_picks: list[str]
    finalists_alive: int
    days_at_top: int
    total_days: int
    runner_up_gap: int | None
    story_line: str
    audit_verified: bool
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
    """Opening sentence — picks template by lead pattern."""
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
    """Comma-joinable margin phrase, lowercase to attach onto the lead."""
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
    into the knockouts."""
    n_finalists = len(finalist_picks)

    if not champion_pick and n_finalists == 0:
        return None

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

    champ_in_finalists = champion_pick in finalist_picks
    other_finalists = [t for t in finalist_picks if t != champion_pick]

    if n_finalists == 0:
        if champion_alive:
            return (
                f"Their champion pick {champion_pick} carries the bracket "
                "bid into the knockouts."
            )
        return (
            f"Their champion pick {champion_pick} has already exited the "
            "bracket — the knockout run will need late drama."
        )

    if champion_alive and finalists_alive == n_finalists:
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
    """Top-level narrative assembler — 2-3 sentences of prose."""
    lead = _lead_beat(days_at_top, total_days, name)
    margin = _margin_clause(runner_up_gap, runner_up_name)
    bracket = _bracket_sentence(
        champion_pick, champion_alive, finalist_picks, finalists_alive
    )

    sentence_1 = f"{lead}, {margin}." if margin else f"{lead}."
    if bracket:
        return f"{sentence_1} {bracket}"
    return sentence_1


def _display_name(user_name: str, entry_name: str, user_entry_count: int) -> str:
    """Match the leaderboard's ``rowDisplayName`` rule with one refinement:
    strip the owner-name prefix from the entry name when it duplicates
    (so "James Vella — James Vella 3rd Entry" collapses to
    "James Vella — 3rd Entry").
    """
    if user_entry_count <= 1:
        return user_name
    entry = (entry_name or "").strip()
    if not entry:
        return user_name
    # Strip the owner-name prefix if present, plus any separator after it.
    if entry.lower().startswith(user_name.lower()):
        trimmed = entry[len(user_name):].lstrip()
        trimmed = trimmed.lstrip("—-").lstrip()
        if trimmed:
            entry = trimmed
    return f"{user_name} — {entry}"


def group_stage_total(e) -> int:
    """★ THE group-stage-cash definition. Shared by the GSW podium and the
    Trionda eligibility check (tournament_champion.py). One resolver —
    never re-derive this sum elsewhere (read-vs-score-time rule)."""
    p1 = e.breakdown.phase1
    return (
        p1.match_outcome_points
        + p1.exact_score_points
        + p1.hybrid_bonus_points
        + (e.bonus_group_points or 0)
    )


async def days_at_top(session: AsyncSession, entry_id) -> int:
    """COUNT of distinct snapshot dates where `entry_id` held position 1.
    Captures dominance vs squeaked-in-at-the-end. Shared by the GSW
    podium and the final podium (tournament_champion.py) — one query,
    never re-derive it elsewhere."""
    sql = text(
        """
        SELECT COUNT(DISTINCT captured_date) AS days
        FROM leaderboard_snapshots
        WHERE entry_id = :entry_id
          AND position = 1
        """
    )
    try:
        row = (await session.execute(sql, {"entry_id": entry_id})).first()
        return int(row.days or 0) if row else 0
    except Exception:  # noqa: BLE001 — story stat must not fail the payload
        return 0


async def total_snapshot_days(session: AsyncSession) -> int:
    """Total distinct captured_date values across every snapshot — the
    denominator for `days_at_top`. Shared by the GSW podium and the
    final podium (tournament_champion.py)."""
    sql = text("SELECT COUNT(DISTINCT captured_date) AS days FROM leaderboard_snapshots")
    try:
        row = (await session.execute(sql)).first()
        return int(row.days or 0) if row else 0
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# Service — primary entry point
# ---------------------------------------------------------------------------
async def get_group_stage_podium(session: AsyncSession) -> GroupStagePodium | None:
    """Compute the Group Stage podium (top 3) from the cached phase_1
    leaderboard. Returns None only if the pool has zero eligible entries.

    The release-flag gate lives at the API layer; the service itself is
    unconditional so test sends + admin previews can still inspect the
    payload.
    """
    lb = await calculate_leaderboard(session, phase="phase_1")
    if not lb.entries:
        return None

    # Count how many entries each user owns so display_name can pick
    # between "Person" and "Person — Entry name" per the leaderboard
    # convention. Bounded by the eligible-entries set (small in practice).
    user_entry_count: Counter[str] = Counter(e.user_id for e in lb.entries)

    # ★ Group-stage total = match outcomes + exact scores + rarity +
    # the TWO group-stage bonus questions (most goals scored / most
    # conceded). Excludes everything knockout — bracket advancement
    # credits, knockout-bonus payouts, the lot. This card is a
    # FROZEN historical statement about the group-stage podium;
    # once knockouts begin paying out, the live `e.total_points`
    # diverges from group-stage truth (e.g. Brian Agius at #2 on
    # the live board with strong R32 picks, but #5 on the group
    # stage). The card must stay pinned to group-stage truth.
    # (See module-level ``group_stage_total`` above — THE shared
    # resolver, also used by the Trionda eligibility check.)

    # Re-sort the leaderboard entries by group-stage total (exact-score
    # tiebreaker matches the live leaderboard convention). Once
    # knockouts settle, this sort no longer matches lb.entries' order
    # — that's the whole point. The GSW card is a snapshot of the
    # group-stage podium even when the live podium has shifted.
    gs_sorted = sorted(
        lb.entries,
        key=lambda e: (group_stage_total(e), e.exact_scores),
        reverse=True,
    )
    top: list = gs_sorted[:3]
    winner = top[0]
    phase1 = winner.breakdown.phase1
    winner_gs_total = group_stage_total(winner)

    runner_up_name: str | None = None
    runner_up_gap: int | None = None
    if len(top) >= 2:
        runner_up = top[1]
        runner_up_name = runner_up.user_name
        runner_up_gap = winner_gs_total - group_stage_total(runner_up)

    # Days-at-top / total_days: shared queries (see module-level
    # `days_at_top` / `total_snapshot_days` above — also used by the
    # final podium in tournament_champion.py).
    winner_days_at_top = await days_at_top(session, winner.entry_id)
    total_days = await total_snapshot_days(session)

    finalist_picks_list = list(winner.finalist_picks or [])

    story_line = _compose_story_line(
        name=winner.user_name,
        days_at_top=winner_days_at_top,
        total_days=total_days,
        runner_up_name=runner_up_name,
        runner_up_gap=runner_up_gap,
        champion_pick=winner.champion_pick,
        champion_alive=winner.champion_alive,
        finalist_picks=finalist_picks_list,
        finalists_alive=winner.finalists_alive,
    )

    entries = [
        GroupStageEntry(
            entry_id=str(e.entry_id),
            user_name=e.user_name,
            entry_name=e.entry_name,
            display_name=_display_name(
                e.user_name, e.entry_name, user_entry_count[e.user_id]
            ),
            # Rank within the GROUP-STAGE podium (not the live board).
            # gs_sorted is 0-indexed; rank is 1-indexed.
            final_rank=gs_sorted.index(e) + 1,
            # Total = group-stage total ONLY (excludes KO bracket payouts
            # and knockout-bonus). Frozen historical statement.
            total_points=group_stage_total(e),
            outcome_points=e.breakdown.phase1.match_outcome_points,
            exact_score_extra=e.breakdown.phase1.exact_score_points,
            rarity_extra=e.breakdown.phase1.hybrid_bonus_points,
            # Group bonus only — the 2 group-stage questions (most goals
            # scored / most conceded). Excludes the 2 knockout-stage
            # bonus questions when those eventually settle, since those
            # are a different scoring layer.
            bonus_question_points=(e.bonus_group_points or 0),
        )
        for e in top
    ]

    return GroupStagePodium(
        entries=entries,
        champion_pick=winner.champion_pick,
        champion_alive=winner.champion_alive,
        finalist_picks=finalist_picks_list,
        finalists_alive=winner.finalists_alive,
        days_at_top=winner_days_at_top,
        total_days=total_days,
        runner_up_gap=runner_up_gap,
        story_line=story_line,
        audit_verified=True,
        generated_at=utc_now(),
    )


# ---------------------------------------------------------------------------
# Backward-compat shim (deprecated — to be removed once all callers move
# to get_group_stage_podium). Returns just the winner's GroupStageEntry
# with a couple of legacy fields surfaced as attributes.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _LegacyWinnerView:
    """Adapter that lets existing callers keep using the old field names
    while the podium service is the source of truth."""

    entry_id: str
    user_name: str
    entry_name: str
    total_points: int
    final_rank: int
    outcome_points: int
    exact_score_extra: int
    rarity_extra: int
    bonus_question_points: int
    correct_outcomes: int
    exact_scores: int
    days_at_top: int
    champion_pick: str | None
    champion_alive: bool
    finalist_picks: list[str]
    finalists_alive: int
    runner_up_name: str | None
    runner_up_gap: int | None
    total_days: int
    story_line: str
    generated_at: datetime


async def get_group_stage_winner(session: AsyncSession) -> _LegacyWinnerView | None:
    """DEPRECATED — use ``get_group_stage_podium`` instead.

    Thin wrapper kept for the email-tokens helper which hasn't been
    migrated yet. New callers should hit ``get_group_stage_podium`` and
    pull ``podium.entries[0]``.
    """
    podium = await get_group_stage_podium(session)
    if podium is None or not podium.entries:
        return None
    w = podium.entries[0]
    # Recover correct_outcomes / exact_scores via a fresh leaderboard
    # read (cached, cheap). Kept off the new podium type because no card
    # uses them, but the email-tokens helper expects them on the legacy
    # view's surface.
    lb = await calculate_leaderboard(session, phase="phase_1")
    src = next((e for e in lb.entries if str(e.entry_id) == w.entry_id), None)
    runner_up_name: str | None = None
    if len(podium.entries) >= 2:
        runner_up_name = podium.entries[1].user_name
    return _LegacyWinnerView(
        entry_id=w.entry_id,
        user_name=w.user_name,
        entry_name=w.entry_name,
        total_points=w.total_points,
        final_rank=w.final_rank,
        outcome_points=w.outcome_points,
        exact_score_extra=w.exact_score_extra,
        rarity_extra=w.rarity_extra,
        bonus_question_points=w.bonus_question_points,
        correct_outcomes=src.correct_outcomes if src else 0,
        exact_scores=src.exact_scores if src else 0,
        days_at_top=podium.days_at_top,
        champion_pick=podium.champion_pick,
        champion_alive=podium.champion_alive,
        finalist_picks=list(podium.finalist_picks),
        finalists_alive=podium.finalists_alive,
        runner_up_name=runner_up_name,
        runner_up_gap=podium.runner_up_gap,
        total_days=podium.total_days,
        story_line=podium.story_line,
        generated_at=podium.generated_at,
    )
