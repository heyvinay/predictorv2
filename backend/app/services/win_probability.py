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

import asyncio
import itertools
import logging
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import utc_now

log = logging.getLogger(__name__)

from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction, normalize_stage
from app.models.score import Score
from app.services.bracket_seeding import (
    EXT_ID_TO_MATCH_NUMBER,
    FINAL_SOURCES,
    QUARTER_FINAL_SOURCES,
    ROUND_OF_16_SOURCES,
    SEMI_FINAL_SOURCES,
)
from app.services.bonus import (
    answer_in,
    compute_bottlers,
    compute_dark_horse,
    get_meta,
    get_questions,
)
from app.services.locking import get_active_competition
from app.services.odds_cache import get_or_refresh_odds
from app.services.polymarket import get_stage_reach_probabilities
from app.services.r32_resolver import build_r32_resolver, resolve_r32_pair
from app.services.team_match import canonicalize, derive_advance_probability, extract_h2h_odds, find_odds_for_fixture
from app.services.scoring import (
    calculate_entry_points,
    eligible_entry_ids_select,
    get_actual_advancement,
    get_scoring_config,
)

# Merged match_number -> (home_source, away_source) for every R16+ match —
# same aggregation ko_lineup_resolver.py performs, duplicated here rather
# than imported since it's a module-private (`_ALL_KO_SOURCES`) there.
_ALL_KO_SOURCES: dict[int, tuple[dict, dict]] = {
    **ROUND_OF_16_SOURCES,
    **QUARTER_FINAL_SOURCES,
    **SEMI_FINAL_SOURCES,
    **FINAL_SOURCES,
}

_SCORED_KO_STAGES = (
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
)

# TeamPrediction stages this simulator resimulates. 'group' is excluded
# deliberately — group-stage advancement is already fully determined once
# groups are complete, so it belongs in each entry's banked base, not in
# the per-scenario KO delta.
KO_PREDICTION_STAGES = frozenset(
    {"round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner"}
)

# The only two bonus questions whose correct answer is a function of
# knockout bracket progress (services.bonus.compute_dark_horse /
# compute_bottlers) — the group-stage questions are settled facts once
# the group stage ends and never need re-simulation.
BONUS_BRACKET_QUESTIONS = frozenset({"dark_horse", "flop"})

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
    match_probabilities: dict[int, float] | None = None,
) -> Iterator[tuple[dict[int, str], float]]:
    """Yield (winners, weight) for every completion of the bracket.

    `match_probabilities` maps match_number -> P(home side advances); a
    match absent from it (or the whole arg omitted) defaults to a flat
    50/50 split — this is the ONLY thing that changes behavior, so
    omitting the arg entirely reproduces the original uniform model
    exactly (each of the 2**len(unresolved) combinations at 1/2**n).

    `unresolved` must be in topological order — ascending match_number is
    always valid, since FIFA match numbers only ever reference strictly
    earlier matches (verified against bracket_seeding.py's source maps).
    """
    match_probabilities = match_probabilities or {}
    n = len(unresolved)

    for bits in itertools.product((0, 1), repeat=n):
        winners = dict(known_winners)
        weight = 1.0
        for match_number, bit in zip(unresolved, bits):
            spec = matches[match_number]
            home = resolve_ref(spec.home_ref, winners)
            away = resolve_ref(spec.away_ref, winners)
            p_home = match_probabilities.get(match_number, 0.5)
            winners[match_number] = home if bit == 0 else away
            weight *= p_home if bit == 0 else (1.0 - p_home)
        yield winners, weight


# Above this many unresolved matches, 2**m scenarios stops being cheap to
# enumerate exhaustively — benchmarked at ~9s for m=14 against a 68-entry
# pool (2**14 = 16,384 scenarios), so m=15 (32,768) is still comfortably
# affordable but roughly doubles that; each further step doubles it again.
# This tournament's m only ever shrinks (every finished KO match removes
# one unresolved match), so exact enumeration covers it end to end — this
# constant exists to future-proof a differently-shaped tournament (more
# knockout rounds simultaneously unresolved) rather than for this one.
# Exposed as a `simulate_pool`/`compute_win_probability` parameter, not
# just a hardcoded constant, so it can be tuned per deployment without a
# code change if a pool's entry count changes the affordable ceiling.
EXACT_ENUMERATION_MAX_M = 15
MONTE_CARLO_SAMPLES = 20_000


def sample_scenarios(
    matches: dict[int, MatchSpec],
    known_winners: dict[int, str],
    unresolved: list[int],
    num_samples: int = MONTE_CARLO_SAMPLES,
    *,
    rng: random.Random | None = None,
    match_probabilities: dict[int, float] | None = None,
) -> Iterator[tuple[dict[int, str], float]]:
    """Monte Carlo fallback for when 2**len(unresolved) is too large to
    enumerate exhaustively: `num_samples` random draws, each carrying
    equal weight 1/num_samples. Downstream aggregation (simulate_pool)
    only ever consumes (winners, weight) pairs, so it needs no changes to
    consume sampled scenarios instead of enumerated ones — this is a
    statistical ESTIMATE of the same quantity enumerate_scenarios
    computes exactly, convergent as num_samples grows but never exact for
    finite samples.

    `match_probabilities` (match_number -> P(home advances), default 0.5
    when absent) skews the per-match coin flip — unlike the exact path,
    the probability is baked into the DRAW frequency here rather than
    the yielded weight, since that's what "random sampling" means; the
    weight stays uniform either way.

    Same topological-order requirement as enumerate_scenarios: ascending
    match_number in `unresolved` is always valid.
    """
    rng = rng if rng is not None else random.Random()
    match_probabilities = match_probabilities or {}
    weight = 1.0 / num_samples

    for _ in range(num_samples):
        winners = dict(known_winners)
        for match_number in unresolved:
            spec = matches[match_number]
            home = resolve_ref(spec.home_ref, winners)
            away = resolve_ref(spec.away_ref, winners)
            p_home = match_probabilities.get(match_number, 0.5)
            winners[match_number] = home if rng.random() < p_home else away
        yield winners, weight


def resolve_known_state(
    matches: dict[int, MatchSpec], raw_outcomes: dict[int, str]
) -> tuple[dict[int, str], list[int]]:
    """Split a bracket into its known-decided winners and its still-open
    (unresolved) matches, given each match's raw '1'/'2' outcome where
    available (absent/None means not yet played).

    Processes matches in ascending match_number order — the topological
    order FIFA's numbering guarantees (a match's home_ref/away_ref only
    ever point to strictly earlier match numbers). A match is only
    counted as decided if BOTH its own outcome is known AND its feeder
    matches (if any) already resolved — a fixture reported FINISHED
    while its feeders are still open (a transient data-lag edge case) is
    conservatively deferred to `unresolved` rather than guessed at.
    """
    winners: dict[int, str] = {}
    unresolved: list[int] = []

    for match_number in sorted(matches):
        spec = matches[match_number]
        try:
            home = resolve_ref(spec.home_ref, winners)
            away = resolve_ref(spec.away_ref, winners)
        except KeyError:
            unresolved.append(match_number)
            continue

        outcome = raw_outcomes.get(match_number)
        if outcome in ("1", "2"):
            winners[match_number] = home if outcome == "1" else away
        else:
            unresolved.append(match_number)

    return winners, unresolved


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


@dataclass(frozen=True)
class BonusSimulationConfig:
    """What the per-scenario bonus re-simulation needs to know.

    Only the KO-bracket-dependent bonus questions (dark_horse, flop) are
    ever candidates for simulation — the group-stage questions are
    settled facts once the group stage ends and always live in
    base_points, never here. `unresolved_questions` is the ONLY switch
    that matters for correctness: a question already answered by an
    admin (a BonusAnswer row exists) must never be re-simulated, since
    its real fixed points are already baked into base_points. Passing
    an already-resolved question here would double-count it.
    """

    fifa_top_teams: frozenset[str]
    unresolved_questions: frozenset[str]
    points_by_question: dict[str, int]


def simulate_bonus_points(
    picks: dict[str, str],
    advancement: dict[str, str],
    config: BonusSimulationConfig,
) -> int:
    """One entry's bonus points for ONE scenario's advancement dict.

    Reuses the real scoring functions (services.bonus.compute_dark_horse /
    compute_bottlers) directly against the simulated advancement — the
    same team->highest_stage shape build_advancement() already produces
    for KO scoring — so there is no separate reimplementation to drift
    out of sync with the actual bonus-settlement logic.

    compute_bottlers's `competition_teams` param is passed as
    `fifa_top_teams` itself rather than the full ~48-team roster: every
    fifa_top team is guaranteed to be a real competition entrant (the
    YAML's own invariant — see config/worldcup2026.yml's fifa_top_teams
    comment), so `[t for t in fifa_top if t in competition_teams]`
    reduces to `fifa_top` either way. A team absent from `advancement`
    (eliminated in the group stage, never seeded into a KO match) falls
    back to progress.get(t, "group") inside compute_bottlers/
    compute_dark_horse — identical to how the real DB-backed progress
    dict would represent that team, so restricting to KO-stage teams
    only never changes the answer.
    """
    total = 0
    if "dark_horse" in config.unresolved_questions:
        correct = compute_dark_horse(advancement, config.fifa_top_teams)
        if answer_in(picks.get("dark_horse", ""), correct):
            total += config.points_by_question.get("dark_horse", 0)
    if "flop" in config.unresolved_questions:
        correct = compute_bottlers(advancement, config.fifa_top_teams, config.fifa_top_teams)
        if answer_in(picks.get("flop", ""), correct):
            total += config.points_by_question.get("flop", 0)
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
    # team -> stage -> P(team reaches AT LEAST that stage), cumulative —
    # e.g. team_stage_odds["Brazil"]["final"] includes every scenario
    # where Brazil went on to win it all, not just the ones where the
    # final was its exact ceiling. Trophy odds are team_stage_odds[t]["winner"].
    team_stage_odds: dict[str, dict[str, float]] = field(default_factory=dict)
    # Stamped at construction — reflects when the simulation actually ran,
    # not when a cached result happens to be served to a given request.
    computed_at: datetime = field(default_factory=utc_now)
    # "exact" (2**m enumeration) or "monte_carlo" (sampled) — whichever
    # simulate_pool actually used, driven by len(unresolved) vs max_exact_m.
    mode: str = "exact"
    # m = len(unresolved), recorded directly rather than derived from
    # scenario_count — under "exact" mode scenario_count == 2**m so a
    # log2 reversal works, but under "monte_carlo" scenario_count is
    # just num_samples (e.g. 20,000) and log2(20000) is not m at all.
    unresolved_matches: int = 0


def simulate_pool(
    matches: dict[int, MatchSpec],
    known_winners: dict[int, str],
    unresolved: list[int],
    entries: dict[str, list[tuple[str, str]]],
    points_by_stage: dict[str, int],
    base_points: dict[str, int],
    entry_bonus_picks: dict[str, dict[str, str]] | None = None,
    bonus_config: BonusSimulationConfig | None = None,
    max_exact_m: int = EXACT_ENUMERATION_MAX_M,
    num_samples: int = MONTE_CARLO_SAMPLES,
    rng: random.Random | None = None,
    match_probabilities: dict[int, float] | None = None,
) -> PoolSimulationResult:
    """Enumerate every bracket completion and, for each, rank the pool by
    base_points[entry] + entry_ko_points(...) [+ simulate_bonus_points(...)
    if an unresolved bracket-dependent bonus question applies] to
    accumulate P(win), P(top-3), and expected final rank per entry.

    `entry_bonus_picks`/`bonus_config` are optional so callers with
    nothing unresolved (or that don't care about bonus questions at all)
    can omit them with zero behavior change — the bonus term is simply
    0 for every entry in every scenario.

    Aggregation auto-selects exact enumeration when
    len(unresolved) <= max_exact_m, else falls back to seeded Monte
    Carlo sampling (see sample_scenarios) — this tournament never
    crosses that threshold (m only shrinks), but a differently-shaped
    one might.

    Ranking uses standard competition ranking (ties share the lower rank
    number, e.g. 1-1-3). Win credit for a scenario is split evenly among
    every entry tied for the top score, so `sum(p_win for all entries)`
    always equals 1.0 under exact enumeration — the invariant the plan's
    response schema depends on to render odds that don't silently over-
    or under-count. Under Monte Carlo, this holds only approximately
    (sampling noise), same as every other per-entry statistic.
    """
    entry_ids = list(entries)
    accum = {eid: EntryProbability() for eid in entry_ids}
    scenario_count = 0
    # team -> exact highest stage reached -> accumulated weight. Converted
    # to cumulative "reached at least" odds once the loop finishes.
    exact_stage_weight: dict[str, dict[str, float]] = {}
    bonus_picks = entry_bonus_picks or {}

    if len(unresolved) <= max_exact_m:
        scenario_source = enumerate_scenarios(
            matches, known_winners, unresolved, match_probabilities
        )
        mode = "exact"
    else:
        scenario_source = sample_scenarios(
            matches,
            known_winners,
            unresolved,
            num_samples,
            rng=rng,
            match_probabilities=match_probabilities,
        )
        mode = "monte_carlo"

    for winners, weight in scenario_source:
        advancement = build_advancement(matches, winners)
        scenario_count += 1

        for team, stage in advancement.items():
            team_weights = exact_stage_weight.setdefault(team, {})
            team_weights[stage] = team_weights.get(stage, 0.0) + weight

        scores = {
            eid: base_points.get(eid, 0)
            + entry_ko_points(entries[eid], advancement, points_by_stage)
            + (
                simulate_bonus_points(bonus_picks.get(eid, {}), advancement, bonus_config)
                if bonus_config is not None
                else 0
            )
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

    team_stage_odds = {
        team: _cumulative_from_exact(exact) for team, exact in exact_stage_weight.items()
    }

    return PoolSimulationResult(
        entries=accum,
        scenario_count=scenario_count,
        team_stage_odds=team_stage_odds,
        mode=mode,
        unresolved_matches=len(unresolved),
    )


def _cumulative_from_exact(exact: dict[str, float]) -> dict[str, float]:
    """Convert P(highest stage reached == X) into P(reached AT LEAST X) —
    a reverse cumulative sum over STAGE_ORDER, since reaching a later
    stage implies having reached every earlier one."""
    cumulative: dict[str, float] = {}
    running = 0.0
    for stage in reversed(STAGE_ORDER):
        running += exact.get(stage, 0.0)
        cumulative[stage] = running
    return cumulative


def compute_match_win_probabilities(
    matches: dict[int, MatchSpec],
    known_winners: dict[int, str],
    unresolved: list[int],
    api_matches: list[dict],
    stage_reach_probabilities: dict[str, dict[str, float]] | None = None,
) -> tuple[dict[int, float], int]:
    """Pure core: derive P(home advances) for every unresolved match whose
    two teams are already real (i.e. resolvable from `known_winners`).

    Two sources, in priority order:

    1. Polymarket's "reach {next_stage}" markets (`stage_reach_probabilities`,
       keyed by target stage -> {canonicalized team: P(Yes)}). Being
       seeded into this match already means both teams reached the
       match's OWN stage as a certain fact, so each team's price for
       reaching the NEXT stage already IS its probability of winning
       this specific match — no further derivation needed. Preferred
       over h2h because it's available even when this exact fixture
       hasn't been added to a sportsbook's h2h grid yet, and because a
       compound market naturally accounts for asymmetric bracket paths
       that a single match's h2h line doesn't need to. Renormalized
       (home / (home + away)) the same way h2h odds are devigged, to
       absorb the residual bid-ask spread between the two sides' prices.
    2. The Odds API's per-fixture h2h odds (team_match.py), when
       Polymarket doesn't have a usable price for BOTH sides.

    A match further out in the bracket — still waiting on another
    unresolved match to decide one of its teams — has no real matchup to
    price under EITHER source yet (there's no market for "TBD vs TBD");
    it's silently absent from the returned dict rather than guessed at,
    matching this module's existing gap-over-guess convention (see
    load_bracket_state's docstring). Callers default an absent
    match_number to 0.5.

    Returns (probabilities, priceable_count) — priceable_count is every
    unresolved match with two real teams, regardless of whether either
    source actually priced it, so callers can surface a coverage badge
    ("priced 2 of 2") distinct from "these matches aren't priceable yet".
    """
    probabilities: dict[int, float] = {}
    priceable_count = 0
    stage_reach_probabilities = stage_reach_probabilities or {}

    for match_number in unresolved:
        spec = matches[match_number]
        try:
            home = resolve_ref(spec.home_ref, known_winners)
            away = resolve_ref(spec.away_ref, known_winners)
        except KeyError:
            continue  # still slot-dependent — no real matchup to price yet

        priceable_count += 1

        target_stage = ADVANCEMENT_MAP.get(spec.stage)
        poly = stage_reach_probabilities.get(target_stage, {}) if target_stage else {}
        home_poly = poly.get(canonicalize(home))
        away_poly = poly.get(canonicalize(away))
        if home_poly is not None and away_poly is not None and (home_poly + away_poly) > 0:
            probabilities[match_number] = home_poly / (home_poly + away_poly)
            continue

        found = find_odds_for_fixture(home, away, api_matches)
        if found is None:
            continue
        odds = extract_h2h_odds(found)
        if odds is None:
            continue
        probabilities[match_number] = derive_advance_probability(odds)

    return probabilities, priceable_count


async def load_ko_match_win_probabilities(
    matches: dict[int, MatchSpec],
    known_winners: dict[int, str],
    unresolved: list[int],
) -> tuple[dict[int, float], int]:
    """DB/IO wrapper: read the shared odds cache + Polymarket's per-stage
    markets and delegate to the pure core. Never raises — both sources
    already have their own durability contracts (any upstream failure
    serves last-good cache, or empty on a cold cache), so an outage on
    either simply means fewer match_numbers get priced, and callers fall
    back to the uniform model for whatever's left unpriced.
    """
    cache = await get_or_refresh_odds()
    api_matches = cache.get("matches") or []

    target_stages = {
        ADVANCEMENT_MAP[matches[m].stage]
        for m in unresolved
        if matches[m].stage in ADVANCEMENT_MAP
    }
    stage_reach_probabilities = {
        stage: await get_stage_reach_probabilities(stage) for stage in target_stages
    }

    return compute_match_win_probabilities(
        matches, known_winners, unresolved, api_matches, stage_reach_probabilities
    )


@dataclass
class WinProbabilityComparison:
    """Both simulation views side by side: the existing uniform 50/50
    model, and an odds-weighted variant when The Odds API prices at least
    one of the next unresolved matches. `odds_weighted` is None (never a
    zeroed-out result) when nothing is priceable yet — the frontend's
    signal to hide the second column rather than render a misleading
    "identical to uniform" comparison.
    """

    uniform: PoolSimulationResult
    odds_weighted: PoolSimulationResult | None
    odds_matches_priced: int = 0
    odds_matches_priceable: int = 0


async def load_bracket_state(
    session: AsyncSession,
) -> tuple[dict[int, MatchSpec], dict[int, str], list[int]]:
    """Load the live knockout bracket into the pure engine's shape.

    R32 matches get literal (home, away) team names via r32_resolver (the
    same resolver get_actual_advancement uses to unmask 'slot:' placeholders
    from settled group standings). R16+ matches get MatchSpecs whose refs
    point at upstream match_numbers, taken straight from bracket_seeding's
    source maps. A fixture whose external_id isn't in
    EXT_ID_TO_MATCH_NUMBER is skipped — same defensive gap-over-guess
    behavior as ko_lineup_resolver.
    """
    r32_resolver = await build_r32_resolver(session)

    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(Fixture.stage.in_(_SCORED_KO_STAGES))
    )

    matches: dict[int, MatchSpec] = {}
    raw_outcomes: dict[int, str] = {}

    for fixture, score in result.all():
        match_number = EXT_ID_TO_MATCH_NUMBER.get(fixture.external_id or "")
        if match_number is None:
            continue

        if fixture.stage == "round_of_32":
            home, away = resolve_r32_pair(r32_resolver, fixture.home_team, fixture.away_team)
            if home is None or away is None:
                continue
            matches[match_number] = MatchSpec(stage=fixture.stage, home_ref=home, away_ref=away)
        else:
            source = _ALL_KO_SOURCES.get(match_number)
            if source is None:
                continue
            home_src, away_src = source
            matches[match_number] = MatchSpec(
                stage=fixture.stage,
                home_ref=home_src["match_number"],
                away_ref=away_src["match_number"],
            )

        if fixture.status == MatchStatus.FINISHED and score is not None:
            outcome = score.outcome
            if outcome in ("1", "2"):
                raw_outcomes[match_number] = outcome

    known_winners, unresolved = resolve_known_state(matches, raw_outcomes)
    return matches, known_winners, unresolved


async def load_pool_predictions(
    session: AsyncSession, actual_advancement: dict[str, str]
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, int]]:
    """Load every eligible entry's KO-stage predictions plus its banked
    base score — every point EXCEPT the KO-advancement fields this
    simulator recomputes per scenario (match points, group_advance,
    group_position, and bonus_question_points all stay fixed).

    `actual_advancement` is the CURRENT get_actual_advancement() result,
    computed once by the caller and passed in — same batching rationale
    calculate_entry_points already documents for its own callers.
    """
    entry_ids_result = await session.execute(eligible_entry_ids_select())
    entry_ids = [row[0] for row in entry_ids_result.all()]

    entries: dict[str, list[tuple[str, str]]] = {}
    base_points: dict[str, int] = {}

    for entry_id in entry_ids:
        breakdown = await calculate_entry_points(
            session,
            entry_id,
            actual_advancement=actual_advancement,
            knockout_scoring_enabled=True,
        )
        banked_ko = (
            breakdown.phase1.round_of_32_points
            + breakdown.phase1.round_of_16_points
            + breakdown.phase1.quarter_final_points
            + breakdown.phase1.semi_final_points
            + breakdown.phase1.final_points
            + breakdown.phase1.winner_points
        )
        base_points[str(entry_id)] = breakdown.total - banked_ko

        preds_result = await session.execute(
            select(TeamPrediction.team, TeamPrediction.stage).where(
                TeamPrediction.entry_id == entry_id,
                TeamPrediction.phase == PredictionPhase.PHASE_1,
            )
        )
        entries[str(entry_id)] = [
            (team, normalize_stage(stage))
            for team, stage in preds_result.all()
            if normalize_stage(stage) in KO_PREDICTION_STAGES
        ]

    return entries, base_points


async def load_bonus_simulation_config(
    session: AsyncSession, competition_id: uuid.UUID
) -> BonusSimulationConfig:
    """Which bracket-dependent bonus questions (dark_horse, flop) still
    need per-scenario re-simulation, determined from the REAL resolution
    state — never assumed. A question drops out of unresolved_questions
    the moment ANY BonusAnswer row exists for it in this competition:
    from that point its real, fixed answer is already correctly baked
    into every entry's base_points (via calculate_entry_points's own
    bonus_question_points), and re-simulating it here would double-count
    it. This is also what makes the wiring future-proof — as the admin
    settles each question over the course of the tournament, this
    function's answer shifts on its own with no code change needed.
    """
    resolved_result = await session.execute(
        select(BonusAnswer.question_id).where(BonusAnswer.competition_id == competition_id)
    )
    resolved = {row[0] for row in resolved_result.all()}
    unresolved = BONUS_BRACKET_QUESTIONS - resolved

    meta = get_meta()
    questions_by_id = {q.id: q for q in get_questions()}
    points_by_question = {
        qid: questions_by_id[qid].points
        for qid in BONUS_BRACKET_QUESTIONS
        if qid in questions_by_id
    }

    return BonusSimulationConfig(
        fifa_top_teams=frozenset(meta.fifa_top_teams),
        unresolved_questions=frozenset(unresolved),
        points_by_question=points_by_question,
    )


async def load_bonus_picks(
    session: AsyncSession, question_ids: frozenset[str]
) -> dict[str, dict[str, str]]:
    """Each eligible entry's picks for the given bonus question ids.
    Callers pass only the currently-unresolved ids — there's no reason
    to load picks for a question that will never be re-simulated."""
    if not question_ids:
        return {}
    entry_ids_result = await session.execute(eligible_entry_ids_select())
    entry_ids = [row[0] for row in entry_ids_result.all()]
    if not entry_ids:
        return {}

    result = await session.execute(
        select(BonusPrediction.entry_id, BonusPrediction.question_id, BonusPrediction.answer)
        .where(BonusPrediction.entry_id.in_(entry_ids))
        .where(BonusPrediction.question_id.in_(list(question_ids)))
    )
    picks: dict[str, dict[str, str]] = {}
    for entry_id, question_id, answer in result.all():
        picks.setdefault(str(entry_id), {})[question_id] = answer
    return picks


async def compute_win_probability(session: AsyncSession) -> WinProbabilityComparison:
    """Top-level entry point: load the live bracket + pool and run the
    simulation twice — once under the uniform 50/50 model, once weighted
    by live betting odds for whichever unresolved matches are already
    real-vs-real and priced. The odds-weighted run is cheap to add: m is
    the same, so it's the same 2**m (or Monte Carlo) budget twice, not
    squared.
    """
    matches, known_winners, unresolved = await load_bracket_state(session)
    actual_advancement = await get_actual_advancement(session)
    entries, base_points = await load_pool_predictions(session, actual_advancement)
    points_by_stage = get_scoring_config().get("advancement", {})

    competition = await get_active_competition(session)
    bonus_config = None
    bonus_picks: dict[str, dict[str, str]] = {}
    if competition is not None:
        bonus_config = await load_bonus_simulation_config(session, competition.id)
        if bonus_config.unresolved_questions:
            bonus_picks = await load_bonus_picks(session, bonus_config.unresolved_questions)

    uniform = simulate_pool(
        matches,
        known_winners,
        unresolved,
        entries,
        points_by_stage,
        base_points,
        entry_bonus_picks=bonus_picks,
        bonus_config=bonus_config,
    )

    match_probabilities, priceable_count = await load_ko_match_win_probabilities(
        matches, known_winners, unresolved
    )
    odds_weighted = (
        simulate_pool(
            matches,
            known_winners,
            unresolved,
            entries,
            points_by_stage,
            base_points,
            entry_bonus_picks=bonus_picks,
            bonus_config=bonus_config,
            match_probabilities=match_probabilities,
        )
        if match_probabilities
        else None
    )

    return WinProbabilityComparison(
        uniform=uniform,
        odds_weighted=odds_weighted,
        odds_matches_priced=len(match_probabilities),
        odds_matches_priceable=priceable_count,
    )


# ─── Stale-while-revalidate cache ──────────────────────────────────────────
# Mirrors leaderboard.py's cache module exactly (CachedLeaderboard /
# _cache / _cache_ttl / _cache_locks / _refresh_tasks / _is_fresh /
# _schedule_background_refresh / invalidate_cache / expire_cache) — same
# NOTE on per-process-only caching applies here too. There's only one
# cache entry (no phase filter like the leaderboard), but the dict-keyed
# shape is kept for consistency and cheap future extension.

_CACHE_KEY = "default"


@dataclass
class CachedWinProbability:
    result: WinProbabilityComparison
    last_calculated: datetime
    # Marked by expire_win_probability_cache() — a stale result is still
    # servable via stale-while-revalidate, unlike a dropped one.
    stale: bool = False


_cache: dict[str, CachedWinProbability] = {}
_cache_ttl = timedelta(seconds=30)
_cache_locks: dict[str, asyncio.Lock] = {}
_refresh_tasks: dict[str, "asyncio.Task[None]"] = {}

# Overridable in tests (point at the test engine's factory); production
# lazily resolves the app's global async_session_maker.
_background_session_factory: Callable[[], AsyncSession] | None = None


def _make_background_session() -> AsyncSession:
    if _background_session_factory is not None:
        return _background_session_factory()
    from app.database import async_session_maker

    return async_session_maker()


def _lock_for(cache_key: str) -> asyncio.Lock:
    lock = _cache_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _cache_locks[cache_key] = lock
    return lock


def _is_fresh(cached: CachedWinProbability, now: datetime) -> bool:
    return not cached.stale and (now - cached.last_calculated) < _cache_ttl


async def _rebuild_win_probability(
    session: AsyncSession, cache_key: str, now: datetime
) -> WinProbabilityComparison:
    result = await compute_win_probability(session)
    _cache[cache_key] = CachedWinProbability(result=result, last_calculated=now)
    return result


def _schedule_background_refresh(cache_key: str) -> None:
    """Kick off (at most one) off-request rebuild for `cache_key`.

    Part of the stale-while-revalidate path: the caller has already been
    served the expired result, so the rebuild's seconds-long cost (the
    ~9s benchmark measured against the live pool) lands here instead of
    on a user request.
    """
    existing = _refresh_tasks.get(cache_key)
    if existing is not None and not existing.done():
        return

    async def _refresh() -> None:
        async with _lock_for(cache_key):
            now = utc_now()
            cached = _cache.get(cache_key)
            if cached is not None and _is_fresh(cached, now):
                return  # rebuilt by someone else while we waited
            async with _make_background_session() as session:
                await _rebuild_win_probability(session, cache_key, now)

    def _log_failure(task: "asyncio.Task[None]") -> None:
        if not task.cancelled() and task.exception() is not None:
            log.warning(
                "background win-probability refresh for %r failed: %s",
                cache_key,
                task.exception(),
            )

    task = asyncio.create_task(_refresh())
    task.add_done_callback(_log_failure)
    _refresh_tasks[cache_key] = task


async def get_win_probability(
    session: AsyncSession, force_refresh: bool = False
) -> WinProbabilityComparison:
    """Cached entry point: fast path on a fresh cache, stale-while-
    revalidate on an expired one, blocking rebuild on a cold cache or
    force_refresh — same three paths as leaderboard.calculate_leaderboard.
    """
    cache_key = _CACHE_KEY
    now = utc_now()

    if not force_refresh and cache_key in _cache:
        cached = _cache[cache_key]
        if _is_fresh(cached, now):
            return cached.result
        _schedule_background_refresh(cache_key)
        return cached.result

    async with _lock_for(cache_key):
        now = utc_now()
        if not force_refresh and cache_key in _cache:
            cached = _cache[cache_key]
            if _is_fresh(cached, now):
                return cached.result

        return await _rebuild_win_probability(session, cache_key, now)


def invalidate_win_probability_cache() -> None:
    """Drop the cache entirely. The next consumer BLOCKS on a full
    rebuild — read-your-write semantics. Used for the admin toggle path
    and the score-sync KO-finish hook (mirrors leaderboard's usage)."""
    global _cache
    _cache = {}


def expire_win_probability_cache() -> None:
    """Mark the cached result stale WITHOUT dropping it — consumers keep
    getting instant responses from the last-known result while the
    stale-while-revalidate path rebuilds in the background."""
    for cached in _cache.values():
        cached.stale = True
