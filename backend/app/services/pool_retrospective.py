"""Pool-vs-tournament retrospective — ONE aggregate pass (Plan A §8).

Everything the wrap-up page's collective cards need, plus per-member
superlatives, computed together so the page never does 104 per-fixture
fetches. third_place is excluded everywhere (unscored-stage invariant).

Heavily reuses canonical helpers rather than re-deriving facts that
already have a single source of truth elsewhere:
- `eligible_entry_ids_select()` / `get_all_outcome_counts()` /
  `get_actual_advancement()` from `app.services.scoring` — the same
  denominators and advancement map the live leaderboard scores against.
- `calculate_leaderboard()` from `app.services.leaderboard` — per-entry
  totals, champion pick, exact/correct counts. Already cached (30s TTL),
  so calling it here doesn't add a fresh cold-rebuild cost.
- `_group_points` / `_knockout_points` from `app.services.tournament_champion`
  — the same group/knockout point split the final-podium card uses.
- `get_questions()` / `compute_bonus_hit_rates()` from `app.services.bonus`.
"""

import logging
from collections import Counter, defaultdict

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score

logger = logging.getLogger(__name__)


def outcome_of(home: int, away: int) -> str:
    if home > away:
        return "1"
    if home < away:
        return "2"
    return "X"


def rank_misses_and_bankers(stats, top_n: int = 3):
    """stats: iterable of (label, correct_pct, exact_count) for FINISHED
    group matches. Returns (misses, bankers): lowest-pct and highest-pct
    top_n, each ordered most-extreme-first."""
    ordered = sorted(stats, key=lambda s: s[1])
    misses = ordered[:top_n]
    bankers = list(reversed(ordered[-top_n:]))
    return misses, bankers


def _pick_superlatives(personal_stats: dict) -> list[dict]:
    """personal_stats: {exact_hits: [(fixture_label, co_predictors, pts)],
    exact_count, exact_percentile, champion_pick, champion_hit,
    champion_furthest_stage_label, low_consensus_points, ko_hit_pct,
    ko_hit_percentile}. Returns exactly 3 {emoji,title,body} dicts,
    strongest first. Fallback order guarantees 3 for every entry."""
    out = []
    hits = sorted(personal_stats.get("exact_hits", []), key=lambda h: h[1])
    if hits and hits[0][1] <= 3:
        label, co, pts = hits[0]
        who = "Only you called it" if co == 1 else f"One of {co} who called it"
        out.append({
            "emoji": "🎯", "title": who,
            "body": f"{label} exact — {co} of the pool. Your rarest correct pick (+{pts}).",
        })
    if personal_stats.get("exact_percentile", 100) <= 25:
        out.append({
            "emoji": "📈", "title": "Sharp shooter",
            "body": f"{personal_stats['exact_count']} exact scores — top {personal_stats['exact_percentile']}% of the pool.",
        })
    if personal_stats.get("champion_hit"):
        out.append({
            "emoji": "🛡️", "title": "Faithful to the end",
            "body": f"Your champion pick {personal_stats['champion_pick']} went all the way.",
        })
    # NOTE (deviation from the plan's literal draft): the plan gated this
    # block on `low_consensus_points > 0`, but that leaves only 2 truly
    # unconditional fallback blocks (Bracket architect / Ever-present)
    # below it — insufficient to "guarantee 3" (docstring promise, and
    # pinned by test_superlatives_always_three_with_fallbacks's "weak"
    # case, which has exact_percentile=80, champion_hit=False, and
    # low_consensus_points=0 and still expects len == 3). Dropping the
    # `> 0` gate makes this block unconditional like the two after it,
    # matching the sibling blocks' shape and the documented guarantee.
    if len(out) < 3:
        out.append({
            "emoji": "⚔️", "title": "Giant killer",
            "body": f"{personal_stats.get('low_consensus_points', 0)} points from picks fewer than 15% of the pool made.",
        })
    if len(out) < 3:
        out.append({
            "emoji": "🧭", "title": "Bracket architect",
            "body": f"Your knockout calls landed in the top {personal_stats.get('ko_hit_percentile', 50)}% of the pool.",
        })
    if len(out) < 3:
        out.append({
            "emoji": "⚽", "title": "Ever-present",
            "body": "All 104 matches predicted — a full five-week campaign.",
        })
    return out[:3]


# ---------------------------------------------------------------------------
# Real aggregate — read-only, single pass over the DB per call.
# ---------------------------------------------------------------------------

# KO ladder stage order (matches get_actual_advancement's vocabulary, plus
# "winner"). Capacity = number of teams that occupy that stage's fixtures.
_KO_STAGES = ["round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner"]
_KO_CAPACITY = {
    "round_of_32": 32,
    "round_of_16": 16,
    "quarter_final": 8,
    "semi_final": 4,
    "final": 2,
    "winner": 1,
}
_KO_STAGE_RANK = {s: i for i, s in enumerate(_KO_STAGES)}

# Low-consensus threshold for the "giant killer" superlative — a correct
# outcome pick fewer than 15% of the pool also made.
_LOW_CONSENSUS_THRESHOLD = 0.15


def _fixture_label(fixture: Fixture, score: Score) -> str:
    """'M23 · Morocco 2–0 Belgium'-style label. Group fixtures have
    match_number = NULL in prod (per CLAUDE.md) — fall back to no prefix
    rather than rendering 'MNone'."""
    prefix = f"M{fixture.match_number} · " if fixture.match_number else ""
    return f"{prefix}{fixture.home_team} {score.final_home_score}–{score.final_away_score} {fixture.away_team}"


def _percentile_rank(value: float, all_values: list[float]) -> int:
    """'Top X%' framing: the % of the pool whose value is >= this one.
    Rank 1 of many entries lands near 1%; the whole pool lands at 100%.
    Defensive against an empty pool (returns 100)."""
    if not all_values:
        return 100
    n = len(all_values)
    at_or_above = sum(1 for v in all_values if v >= value)
    return max(1, round(100 * at_or_above / n))


def _reached(team: str, stage: str, advancement: dict[str, str]) -> bool:
    reached_stage = advancement.get(team)
    if reached_stage not in _KO_STAGE_RANK:
        return False
    return _KO_STAGE_RANK[reached_stage] >= _KO_STAGE_RANK[stage]


def _empty_retrospective() -> dict:
    """Fail-open payload — degrade to an empty-but-valid shape rather than
    ever 500ing the wrap-up page."""
    return {
        "group_called_right": 0,
        "group_total": 0,
        "final_called_right_pct": 0.0,
        "final_winner_team": None,
        "exact_total": 0,
        "exact_avg_per_entry": 0.0,
        "misses": [],
        "bankers": [],
        "ko_ladder": [],
        "bonus": [],
        "champion_distribution": [],
        "personal": None,
    }


async def _compute_pool_retrospective(session: AsyncSession, *, for_user_id=None) -> dict:
    from app.services.bonus import compute_bonus_hit_rates, get_questions
    from app.services.leaderboard import calculate_leaderboard
    from app.services.scoring import (
        eligible_entry_ids_select,
        get_actual_advancement,
        get_all_outcome_counts,
    )
    from app.services.tournament_champion import _group_points, _knockout_points

    eligible_select = eligible_entry_ids_select()
    eligible_count = (
        await session.execute(select(func.count()).select_from(eligible_select.subquery()))
    ).scalar_one()

    # ------------------------------------------------------------------
    # Group-stage match calls: outcome counts (canonical, shared with the
    # live scoring engine) + a small exact-count query scoped to group
    # fixtures.
    # ------------------------------------------------------------------
    outcome_counts_by_fixture = await get_all_outcome_counts(session)

    fixture_rows = (
        await session.execute(
            select(Fixture, Score)
            .outerjoin(Score, Fixture.id == Score.fixture_id)
            .where(Fixture.stage == "group")
            .where(Fixture.status == MatchStatus.FINISHED)
        )
    ).all()

    exact_count_rows = (
        await session.execute(
            select(MatchPrediction.fixture_id, func.count().label("cnt"))
            .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
            .join(Score, Fixture.id == Score.fixture_id)
            .where(Fixture.stage == "group")
            .where(Fixture.status == MatchStatus.FINISHED)
            .where(MatchPrediction.entry_id.in_(eligible_entry_ids_select()))
            .where(MatchPrediction.home_score == Score.home_score)
            .where(MatchPrediction.away_score == Score.away_score)
            .group_by(MatchPrediction.fixture_id)
        )
    ).all()
    exact_by_fixture: dict = {fid: cnt for fid, cnt in exact_count_rows}

    group_called_right = 0
    group_total = 0
    exact_total = 0
    stats: list[tuple[str, float, int]] = []

    for fixture, score in fixture_rows:
        if score is None:
            continue
        counts = outcome_counts_by_fixture.get(fixture.id, {"1": 0, "X": 0, "2": 0})
        total = sum(counts.values())
        if total == 0:
            continue

        group_total += 1
        actual_outcome = score.outcome
        correct = counts.get(actual_outcome, 0)
        exact = exact_by_fixture.get(fixture.id, 0)
        exact_total += exact

        majority_outcome = max(counts, key=counts.get)
        if majority_outcome == actual_outcome:
            group_called_right += 1

        label = _fixture_label(fixture, score)
        stats.append((label, correct / total, exact))

    misses_raw, bankers_raw = rank_misses_and_bankers(stats, top_n=3)
    misses = [{"label": lbl, "pct": pct, "exact_count": ex} for lbl, pct, ex in misses_raw]
    bankers = [{"label": lbl, "pct": pct, "exact_count": ex} for lbl, pct, ex in bankers_raw]

    exact_avg_per_entry = (exact_total / eligible_count) if eligible_count else 0.0

    # ------------------------------------------------------------------
    # Advancement + KO ladder — consensus lineup per stage (most-picked
    # teams among eligible entries) vs who actually got there.
    # ------------------------------------------------------------------
    advancement = await get_actual_advancement(session)  # team -> furthest stage
    final_winner_team = next(
        (team for team, stage in advancement.items() if stage == "winner"), None
    )

    ko_pick_rows = (
        await session.execute(
            select(TeamPrediction.team, TeamPrediction.stage, func.count().label("cnt"))
            .where(TeamPrediction.stage.in_(_KO_STAGES))
            .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
            .where(TeamPrediction.entry_id.in_(eligible_entry_ids_select()))
            .group_by(TeamPrediction.team, TeamPrediction.stage)
        )
    ).all()
    picks_by_stage: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for team, stage, cnt in ko_pick_rows:
        picks_by_stage[stage].append((team, cnt))

    champion_counts: Counter = Counter()
    for team, cnt in picks_by_stage.get("winner", []):
        champion_counts[team] += cnt

    final_called_right_pct = (
        (champion_counts.get(final_winner_team, 0) / eligible_count)
        if final_winner_team and eligible_count
        else 0.0
    )

    ko_ladder = []
    for stage in _KO_STAGES:
        capacity = _KO_CAPACITY[stage]
        ranked = sorted(picks_by_stage.get(stage, []), key=lambda tc: (-tc[1], tc[0]))
        consensus_list = [team for team, _cnt in ranked[:capacity]]
        consensus_had = sum(1 for team in consensus_list if _reached(team, stage, advancement))
        fallen_teams = [
            team for team in consensus_list if not _reached(team, stage, advancement)
        ][:10]
        ko_ladder.append({
            "stage": stage,
            "consensus_had": consensus_had,
            "of": len(consensus_list),
            "fallen_teams": fallen_teams,
        })

    champion_distribution = [
        {"team": team, "count": cnt, "is_actual": team == final_winner_team}
        for team, cnt in champion_counts.most_common(5)
    ]

    # ------------------------------------------------------------------
    # Bonus questions — resolved-only, via the shared hit-rate helper.
    # ------------------------------------------------------------------
    questions_by_id = {q.id: q for q in get_questions()}
    hit_rates = await compute_bonus_hit_rates(session)
    bonus = []
    for hr in hit_rates:
        question = questions_by_id.get(hr.question_id)
        if question is None:
            continue
        bonus.append({
            "question_id": hr.question_id,
            "label": question.label,
            "answer_label": ", ".join(hr.correct_answers),
            "hit_pct": hr.hit_rate,
        })

    # ------------------------------------------------------------------
    # Personal wrap — reuses the cached leaderboard for per-entry totals,
    # champion pick, and exact/correct counts. Only the fixture-level
    # exact-hit rarity and low-consensus points need a small dedicated
    # query against this user's own predictions.
    # ------------------------------------------------------------------
    personal = None
    if for_user_id is not None:
        lb = await calculate_leaderboard(session, phase="phase_1")
        lb_entries = lb.entries if lb else []
        mine = [e for e in lb_entries if e.user_id == for_user_id]

        if mine:
            all_exact_scores = [e.exact_scores for e in lb_entries]
            all_ko_points = [_knockout_points(e.breakdown.phase1) for e in lb_entries]
            total_entries = len(lb_entries)

            my_entry_ids = [e.entry_id for e in mine]
            personal_rows = (
                await session.execute(
                    select(MatchPrediction, Fixture, Score)
                    .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
                    .join(Score, Fixture.id == Score.fixture_id)
                    .where(Fixture.stage == "group")
                    .where(Fixture.status == MatchStatus.FINISHED)
                    .where(MatchPrediction.entry_id.in_(my_entry_ids))
                )
            ).all()

            from app.services.scoring import calculate_match_points

            per_entry_exact_hits: dict = defaultdict(list)
            per_entry_low_consensus: dict = defaultdict(int)
            for prediction, fixture, score in personal_rows:
                counts = outcome_counts_by_fixture.get(fixture.id, {"1": 0, "X": 0, "2": 0})
                total = sum(counts.values())
                correct_predictors = counts.get(score.outcome, 0)
                points, is_correct, is_exact = calculate_match_points(
                    prediction,
                    score,
                    total_predictors=total,
                    correct_predictors=correct_predictors,
                )
                if is_exact:
                    co = exact_by_fixture.get(fixture.id, 1)
                    label = _fixture_label(fixture, score)
                    per_entry_exact_hits[prediction.entry_id].append((label, co, points))
                if is_correct and total > 0 and (correct_predictors / total) < _LOW_CONSENSUS_THRESHOLD:
                    per_entry_low_consensus[prediction.entry_id] += points

            personal_list = []
            for e in mine:
                # Position-based percentile: what fraction of the pool
                # ranks at or below (numerically >=) this position.
                pct = max(1, round(100 * e.position / total_entries)) if total_entries else 100

                champion_hit = bool(final_winner_team) and e.champion_pick == final_winner_team
                ko_points = _knockout_points(e.breakdown.phase1)

                stats_dict = {
                    "exact_hits": per_entry_exact_hits.get(e.entry_id, []),
                    "exact_count": e.exact_scores,
                    "exact_percentile": _percentile_rank(e.exact_scores, all_exact_scores),
                    "champion_hit": champion_hit,
                    "champion_pick": e.champion_pick,
                    "low_consensus_points": per_entry_low_consensus.get(e.entry_id, 0),
                    "ko_hit_percentile": _percentile_rank(ko_points, all_ko_points),
                }
                superlatives = _pick_superlatives(stats_dict)

                personal_list.append({
                    "entry_id": str(e.entry_id),
                    "entry_name": e.entry_name,
                    "final_rank": e.position,
                    "total_points": e.total_points,
                    "group_points": _group_points(e.breakdown.phase1),
                    "knockout_points": ko_points,
                    "bonus_points": (e.bonus_group_points or 0) + (e.bonus_knockout_points or 0),
                    "percentile_label": f"top {pct}% of the pool",
                    "superlatives": superlatives,
                })
            personal = personal_list

    return {
        "group_called_right": group_called_right,
        "group_total": group_total,
        "final_called_right_pct": final_called_right_pct,
        "final_winner_team": final_winner_team,
        "exact_total": exact_total,
        "exact_avg_per_entry": exact_avg_per_entry,
        "misses": misses,
        "bankers": bankers,
        "ko_ladder": ko_ladder,
        "bonus": bonus,
        "champion_distribution": champion_distribution,
        "personal": personal,
    }


async def compute_pool_retrospective(session: AsyncSession, *, for_user_id=None) -> dict:
    """Pool-vs-tournament retrospective aggregate. Fail-open: any error in
    the real computation degrades to an empty-but-valid payload rather
    than 500ing the wrap-up page (same contract as live_projection.py)."""
    try:
        return await _compute_pool_retrospective(session, for_user_id=for_user_id)
    except Exception:  # noqa: BLE001 — fail-open boundary, see module docstring
        logger.exception("pool retrospective computation failed")
        return _empty_retrospective()
