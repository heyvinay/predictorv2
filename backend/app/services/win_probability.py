"""Knockout win-probability simulation engine (pure core).

Simulates every remaining knockout match to build an empirical probability
distribution over which prediction entry wins the pool, with team
trophy-odds as a byproduct. See
docs/superpowers/specs/... (design doc pending) for the full plan.

This module's pure core deliberately knows nothing about the DB, the
scoring service, or caching — it operates on a bracket described by
`MatchSpec` and a set of already-known winners. Callers (the DB-integrated
layer, added separately) are responsible for translating the live bracket
state (via `ko_lineup_resolver` / `bracket_seeding`) into this shape.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterator

# Mirrors scoring.py's stage progression (get_actual_advancement /
# calculate_advancement_points) — kept in lockstep deliberately rather than
# imported, since this module has no async DB dependency and stage names
# are a stable, singular-only contract across the codebase.
STAGE_ORDER = [
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
    "winner",
]

ADVANCEMENT_MAP = {
    "round_of_32": "round_of_16",
    "round_of_16": "quarter_final",
    "quarter_final": "semi_final",
    "semi_final": "final",
    "final": "winner",
}


@dataclass(frozen=True)
class MatchSpec:
    """One knockout fixture in the simulated bracket.

    `home_ref` / `away_ref` are either a literal team name (str) or the
    match_number (int) of the upstream match whose winner feeds this side —
    the same shape as bracket_seeding.py's source maps, minus the
    {"type": "winner", ...} wrapper (type is always "winner" for KO
    matches; there is nothing else to simulate).
    """

    stage: str
    home_ref: str | int
    away_ref: str | int


def resolve_ref(ref: str | int, winners: dict[int, str]) -> str:
    """A literal team name resolves to itself; a match_number resolves to
    that match's winner. `winners` must already contain every match_number
    referenced — callers are responsible for supplying refs in topological
    (ascending match_number) order, which FIFA's numbering guarantees."""
    return ref if isinstance(ref, str) else winners[ref]


def build_advancement(
    matches: dict[int, MatchSpec], winners: dict[int, str]
) -> dict[str, str]:
    """Collapse a fully-resolved bracket (every match has a winner) into a
    team -> highest_stage_reached dict, matching the shape and semantics of
    scoring.get_actual_advancement(): every team seeded into a match is
    credited with reaching that match's stage, and each match's winner is
    additionally credited with reaching the next stage.
    """
    advancement: dict[str, str] = {}

    def credit(team: str | None, stage: str) -> None:
        if team is None:
            return
        current = advancement.get(team)
        if current is None or STAGE_ORDER.index(stage) > STAGE_ORDER.index(current):
            advancement[team] = stage

    for match_number, spec in matches.items():
        home = resolve_ref(spec.home_ref, winners)
        away = resolve_ref(spec.away_ref, winners)
        credit(home, spec.stage)
        credit(away, spec.stage)

        winner = winners.get(match_number)
        next_stage = ADVANCEMENT_MAP.get(spec.stage)
        if winner and next_stage:
            credit(winner, next_stage)

    return advancement


def enumerate_scenarios(
    matches: dict[int, MatchSpec],
    known_winners: dict[int, str],
    unresolved: list[int],
) -> Iterator[tuple[dict[int, str], float]]:
    """Yield (winners, weight) for every completion of the bracket under a
    uniform 50/50 per-match model.

    `unresolved` must be in topological order — ascending match_number is
    always valid, since FIFA match numbers only ever reference strictly
    earlier matches (verified against bracket_seeding.py's source maps).
    Each of the 2**len(unresolved) combinations carries equal weight.
    """
    n = len(unresolved)
    weight = 1.0 / (2**n) if n else 1.0

    for bits in itertools.product((0, 1), repeat=n):
        winners = dict(known_winners)
        for match_number, bit in zip(unresolved, bits):
            spec = matches[match_number]
            home = resolve_ref(spec.home_ref, winners)
            away = resolve_ref(spec.away_ref, winners)
            winners[match_number] = home if bit == 0 else away
        yield winners, weight


def entry_ko_points(
    predictions: list[tuple[str, str]],
    advancement: dict[str, str],
    points_by_stage: dict[str, int],
) -> int:
    """Sum of advancement points a single entry earns under one scenario's
    advancement dict. Mirrors scoring.calculate_advancement_points exactly
    (verified by test_entry_ko_points_matches_real_calculate_advancement_points)
    but operates on plain (team, stage) tuples instead of a TeamPrediction
    row, and takes the stage->points map directly instead of reading
    get_scoring_config() — callers own translating real TeamPrediction rows
    and the live scoring config into this shape.
    """
    total = 0
    for team, stage in predictions:
        actual_stage = advancement.get(team)
        if actual_stage is not None and STAGE_ORDER.index(actual_stage) >= STAGE_ORDER.index(
            stage
        ):
            total += points_by_stage.get(stage, 0)
    return total


@dataclass
class EntryProbability:
    """One entry's outcome distribution across every simulated scenario."""

    p_win: float = 0.0
    p_top3: float = 0.0
    expected_rank: float = 0.0


@dataclass
class PoolSimulationResult:
    entries: dict[str, EntryProbability]
    scenario_count: int


def simulate_pool(
    matches: dict[int, MatchSpec],
    known_winners: dict[int, str],
    unresolved: list[int],
    entries: dict[str, list[tuple[str, str]]],
    points_by_stage: dict[str, int],
    base_points: dict[str, int],
) -> PoolSimulationResult:
    """Enumerate every bracket completion and, for each, rank the pool by
    base_points[entry] + entry_ko_points(...) to accumulate P(win),
    P(top-3), and expected final rank per entry.

    Ranking uses standard competition ranking (ties share the lower rank
    number, e.g. 1-1-3). Win credit for a scenario is split evenly among
    every entry tied for the top score, so `sum(p_win for all entries)`
    always equals 1.0 — the invariant the plan's response schema depends
    on to render odds that don't silently over- or under-count.
    """
    entry_ids = list(entries)
    accum = {eid: EntryProbability() for eid in entry_ids}
    scenario_count = 0

    for winners, weight in enumerate_scenarios(matches, known_winners, unresolved):
        advancement = build_advancement(matches, winners)
        scenario_count += 1

        scores = {
            eid: base_points.get(eid, 0)
            + entry_ko_points(entries[eid], advancement, points_by_stage)
            for eid in entry_ids
        }

        ranked_scores = sorted(set(scores.values()), reverse=True)
        rank_by_score = {score: i + 1 for i, score in enumerate(ranked_scores)}

        top_score = ranked_scores[0]
        top_entries = [eid for eid, score in scores.items() if score == top_score]
        win_share = weight / len(top_entries)

        for eid in entry_ids:
            rank = rank_by_score[scores[eid]]
            accum[eid].expected_rank += rank * weight
            if rank <= 3:
                accum[eid].p_top3 += weight

        for eid in top_entries:
            accum[eid].p_win += win_share

    return PoolSimulationResult(entries=accum, scenario_count=scenario_count)
