"""Final podium + Trionda side prize (Plan A, 2026-07-18).

Ungated by design (GSW precedent): the release gate lives at the API
layer (`tournament_concluded OR is_admin`) so the admin can dress-
rehearse in production before flipping the flag.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.group_stage_winner import group_stage_total
from app.services.leaderboard import calculate_leaderboard

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TriondaResult:
    recipient: object | None  # a leaderboard row, or None when draw pending
    reason: str
    requires_draw: bool = False
    draw_candidates: list = field(default_factory=list)


def pick_trionda_recipient(rows, *, gs_total_of=group_stage_total) -> TriondaResult:
    """Rules-page algorithm, pure over leaderboard rows.

    The Trionda side prize goes to the highest-ranked entry that is NOT
    also the group-stage cash-prize winner (walking down the leaderboard
    one rank at a time, skipping ranks whose every occupant is
    ineligible). Ties within an eligible rank are broken by group-stage
    points; a persisting tie escalates to a manual draw.

    rows: leaderboard entries with .position, .total_points, .entry_id,
        already sorted so rows[0] is the champion (ties share position 1).
    gs_total_of: injectable for tests; production uses group_stage_total.
    """
    if len(rows) < 2:
        return TriondaResult(None, "not enough entries", requires_draw=False)

    max_gs = max(gs_total_of(r) for r in rows)
    ineligible = {r.entry_id for r in rows if gs_total_of(r) == max_gs}

    champion_rank = rows[0].position
    # Every distinct rank strictly below the (possibly shared) champion
    # rank, in ascending order — this is the walk-down sequence.
    ranks = sorted({r.position for r in rows if r.position > champion_rank})

    for rank in ranks:
        at_rank = [r for r in rows if r.position == rank]
        eligible = [r for r in at_rank if r.entry_id not in ineligible]
        if not eligible:
            continue  # whole rank is ineligible → walk down to the next one

        if len(eligible) == 1:
            reason = (
                "runner-up on total points"
                if rank == ranks[0]
                else f"moved down to #{rank} — group-stage champion not eligible"
            )
            return TriondaResult(eligible[0], reason)

        # Tie at this rank among eligible entries → group-stage points
        # break it (mirrors the leaderboard's own tiebreaker convention).
        best_gs = max(gs_total_of(r) for r in eligible)
        winners = [r for r in eligible if gs_total_of(r) == best_gs]
        if len(winners) == 1:
            return TriondaResult(
                winners[0], f"tied at #{rank} — took it on group-stage points"
            )
        return TriondaResult(
            None,
            f"tied at #{rank} — draw pending",
            requires_draw=True,
            draw_candidates=winners,
        )

    return TriondaResult(None, "no eligible entry", requires_draw=False)


def _knockout_points(p1) -> int:
    return (
        p1.round_of_32_points
        + p1.round_of_16_points
        + p1.quarter_final_points
        + p1.semi_final_points
        + p1.final_points
        + p1.winner_points
    )


def _group_points(p1) -> int:
    return (
        p1.match_outcome_points
        + p1.exact_score_points
        + p1.hybrid_bonus_points
        + p1.group_advance_points
        + p1.group_position_points
    )


async def _days_at_top(session: AsyncSession, entry_id) -> int:
    days_sql = text(
        """
        SELECT COUNT(DISTINCT captured_date) AS days
        FROM leaderboard_snapshots
        WHERE entry_id = :entry_id AND position = 1
        """
    )
    try:
        row = (await session.execute(days_sql, {"entry_id": entry_id})).first()
        return int(row.days) if row and row.days else 0
    except Exception:  # noqa: BLE001 — stats never break the payload
        return 0


def _compose_story_line(champion, runner_up, gap: int, days_at_top: int) -> str:
    beat = (
        f"led for {days_at_top} matchdays"
        if days_at_top >= 10
        else "timed the run to the final week"
    )
    return (
        f"{champion.user_name} takes the title by {gap} points — "
        f"{champion.exact_scores} exact scores and a bracket that held, "
        f"having {beat}. {runner_up.user_name} pushed it all the way."
    )


async def get_final_podium(session: AsyncSession):
    """Top-3 of the FINAL leaderboard + Trionda + story. Returns the
    service-level dict the API layer maps onto schemas (final_match and
    audit are attached at the API layer)."""
    lb = await calculate_leaderboard(session, phase="phase_1")
    if lb is None or not lb.entries:
        return None
    rows = lb.entries

    # NOTE: this is a deliberate fallback, not the real Final result.
    # Fetching the actual Final fixture's winner and overwriting
    # champion_hit for all three podium entries is A5's job (the API
    # layer) — this service intentionally stays DB-model-free beyond the
    # leaderboard/snapshot reads above.
    actual_champion_team = None
    top = rows[:3]
    champion = top[0]
    if champion.champion_pick and champion.champion_alive:
        actual_champion_team = champion.champion_pick

    trionda = pick_trionda_recipient(rows)

    entries = []
    for r in top:
        p1 = r.breakdown.phase1
        entries.append(
            {
                "entry_id": str(r.entry_id),
                "user_name": r.user_name,
                "entry_name": r.entry_name,
                "final_rank": r.position,
                "total_points": r.total_points,
                "group_points": _group_points(p1),
                "knockout_points": _knockout_points(p1),
                "bonus_points": (r.bonus_group_points or 0)
                + (r.bonus_knockout_points or 0),
                "exact_scores": r.exact_scores,
                "rarity_points": p1.hybrid_bonus_points,
                "days_at_top": await _days_at_top(session, r.entry_id),
                "champion_pick": r.champion_pick,
                "champion_hit": bool(
                    actual_champion_team
                    and r.champion_pick == actual_champion_team
                ),
                "is_champion": r.position == rows[0].position,
            }
        )

    total_days_sql = text(
        "SELECT COUNT(DISTINCT captured_date) AS days FROM leaderboard_snapshots"
    )
    try:
        row = (await session.execute(total_days_sql)).first()
        total_days = int(row.days) if row and row.days else 0
    except Exception:  # noqa: BLE001
        total_days = 0

    gap = top[0].total_points - top[1].total_points if len(top) > 1 else 0
    story = _compose_story_line(
        top[0], top[1] if len(top) > 1 else top[0], gap, entries[0]["days_at_top"]
    )

    return {
        "entries": entries,
        "trionda": trionda,
        "story_line": story,
        "total_days": total_days,
    }
