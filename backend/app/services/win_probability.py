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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import utc_now

log = logging.getLogger(__name__)

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
from app.services.r32_resolver import build_r32_resolver, resolve_r32_pair
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
    # team -> exact highest stage reached -> accumulated weight. Converted
    # to cumulative "reached at least" odds once the loop finishes.
    exact_stage_weight: dict[str, dict[str, float]] = {}

    for winners, weight in enumerate_scenarios(matches, known_winners, unresolved):
        advancement = build_advancement(matches, winners)
        scenario_count += 1

        for team, stage in advancement.items():
            team_weights = exact_stage_weight.setdefault(team, {})
            team_weights[stage] = team_weights.get(stage, 0.0) + weight

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

    team_stage_odds = {
        team: _cumulative_from_exact(exact) for team, exact in exact_stage_weight.items()
    }

    return PoolSimulationResult(
        entries=accum, scenario_count=scenario_count, team_stage_odds=team_stage_odds
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


async def compute_win_probability(session: AsyncSession) -> PoolSimulationResult:
    """Top-level entry point: load the live bracket + pool, enumerate every
    remaining-match completion under the 50/50 model, and return each
    entry's P(win) / P(top-3) / expected rank.

    Exact enumeration only for now — at the current tournament stage
    m is well inside the 2**m budget this needs (m only shrinks as
    matches finish). A Monte Carlo fallback for large m is deferred; see
    the plan doc for the threshold this will need once implemented.
    """
    matches, known_winners, unresolved = await load_bracket_state(session)
    actual_advancement = await get_actual_advancement(session)
    entries, base_points = await load_pool_predictions(session, actual_advancement)
    points_by_stage = get_scoring_config().get("advancement", {})

    return simulate_pool(matches, known_winners, unresolved, entries, points_by_stage, base_points)


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
    result: PoolSimulationResult
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
) -> PoolSimulationResult:
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
) -> PoolSimulationResult:
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
