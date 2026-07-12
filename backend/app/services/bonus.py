"""Bonus-question service.

Loads question definitions from `config/worldcup2026.yml`, scores user
predictions against the admin-entered correct answers, and exposes
helpers for the API layer.

Question definitions live in the YAML, not the DB. The DB only holds
per-user picks (BonusPrediction) and per-competition correct answers
(BonusAnswer). Adding/removing a question is a config change, not a
migration.
"""

from __future__ import annotations

import unicodedata
import uuid
from dataclasses import dataclass
from typing import Iterable, Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.config import get_tournament_config
from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.fixture import Fixture, MatchStatus


BonusCategory = Literal["group_stage", "top_flop", "awards"]
# Note: `top_flop` stays the internal literal; only display strings change to
# "Knockout Stage — Top / Flop". Filtered input_types added 2026-06-01 to
# drive the dark_horse / flop dropdowns off `fifa_top_teams`.
BonusInputType = Literal[
    "team",
    "player",
    "team_outside_top_n",
    "team_in_top_n",
]


@dataclass
class BonusQuestion:
    """One question as rendered for the wizard / admin UI."""

    id: str
    category: BonusCategory
    label: str  # already has {top_n} substituted
    input_type: BonusInputType
    points: int


@dataclass
class BonusMeta:
    """FIFA top_n cutoff and the team list it expands to.

    Ships to the wizard so the dark_horse / flop dropdowns can be filtered
    without duplicating the team list on the frontend. The list is whatever
    the YAML's `bonus.fifa_top_teams` holds, in YAML order.
    """

    top_n: int
    fifa_top_teams: list[str]


@dataclass
class BonusHitRate:
    """Pool-wide correctness of ONE resolved bonus question: how many
    eligible entries picked (any of) the correct answer(s), out of the
    eligible pool. Powers the "% who got it right" stat on the Insights
    "Bonus Points" card. Only produced for questions that have a recorded
    answer — an unresolved question has no hit rate yet."""

    question_id: str
    correct_answers: list[str]
    hit_count: int
    eligible_count: int
    hit_rate: float  # hit_count / eligible_count, 0.0 when eligible_count == 0


# ---- Config loading ---------------------------------------------------------


def _get_bonus_config() -> dict:
    """Return the `bonus:` section of the tournament config, or empty dict."""
    try:
        config = get_tournament_config()
    except FileNotFoundError:
        return {}
    return config.get("bonus", {}) or {}


def _category_points(bonus_cfg: dict, category: BonusCategory) -> int:
    """Look up the configured point value for a category, defaulting to 0."""
    return int(bonus_cfg.get("points", {}).get(category, 0))


def get_meta() -> BonusMeta:
    """Load the FIFA top_n cutoff and team list from YAML.

    Used by the wizard's dark_horse / flop dropdowns to filter the 48-team
    pool by FIFA rank without duplicating the list on the frontend. Order
    preserved from YAML (which is in FIFA-rank order).
    """
    cfg = _get_bonus_config()
    return BonusMeta(
        top_n=int(cfg.get("top_n", 10)),
        fifa_top_teams=list(cfg.get("fifa_top_teams", []) or []),
    )


def get_questions() -> list[BonusQuestion]:
    """Load the list of bonus questions from YAML, with `{top_n}` substituted
    into labels so the API ships a fully-rendered string to the frontend."""
    cfg = _get_bonus_config()
    top_n = int(cfg.get("top_n", 10))
    raw_qs = cfg.get("questions", []) or []
    questions: list[BonusQuestion] = []
    for raw in raw_qs:
        category: BonusCategory = raw.get("category", "group_stage")
        label = (raw.get("label") or "").replace("{top_n}", str(top_n))
        questions.append(
            BonusQuestion(
                id=raw["id"],
                category=category,
                label=label,
                input_type=raw.get("input_type", "team"),
                points=_category_points(cfg, category),
            )
        )
    return questions


def get_top_n() -> int:
    """Return the configured FIFA top-N cutoff for dark-horse / flop questions."""
    return int(_get_bonus_config().get("top_n", 10))


# ---- Player-name normalization ---------------------------------------------


def _normalize(s: str) -> str:
    """Case-fold + strip accents so 'Mbappé' matches 'mbappe'. Used for both
    team and player answer comparison; team names usually exact-match anyway,
    but this is forgiving."""
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold().strip()


def answers_match(user_answer: str, correct_answer: str) -> bool:
    """Compare two free-text answers leniently (case- and accent-insensitive)."""
    return _normalize(user_answer) == _normalize(correct_answer)


def answer_in(user_answer: str, correct_answers: list[str]) -> bool:
    """True if `user_answer` matches any one of `correct_answers`. Used
    for bonus questions where multiple teams may tie on the criterion
    (e.g. two teams scoring the same number of goals in the group stage)
    — picking any of the tied teams should award full points."""
    if not user_answer:
        return False
    n = _normalize(user_answer)
    return any(_normalize(c) == n for c in correct_answers)


# ---- Scoring ----------------------------------------------------------------


async def calculate_bonus_points(
    session: AsyncSession,
    entry_id: uuid.UUID,
    competition_id: uuid.UUID | None = None,
) -> int:
    """Total bonus points earned by a single prediction entry.

    For each question with a recorded correct answer (in `bonus_answers`),
    check whether the entry's prediction matches via answers_match() and
    award the question's category points if so. Returns the sum.
    """
    # Load all bonus answers (optionally filtered by competition). Each
    # question may have several rows now — one per tied correct answer.
    ans_q = select(BonusAnswer)
    if competition_id is not None:
        ans_q = ans_q.where(BonusAnswer.competition_id == competition_id)
    ans_rows = (await session.execute(ans_q)).scalars().all()
    if not ans_rows:
        return 0

    correct_by_qid: dict[str, list[str]] = {}
    for a in ans_rows:
        correct_by_qid.setdefault(a.question_id, []).append(a.correct_answer)

    # Entry's predictions for those questions.
    pred_rows = (
        await session.execute(
            select(BonusPrediction)
            .where(BonusPrediction.entry_id == entry_id)
            .where(BonusPrediction.question_id.in_(list(correct_by_qid.keys())))
        )
    ).scalars().all()

    # Map question ID → category points.
    questions_by_id: dict[str, BonusQuestion] = {q.id: q for q in get_questions()}

    total = 0
    for pred in pred_rows:
        corrects = correct_by_qid.get(pred.question_id)
        question = questions_by_id.get(pred.question_id)
        if not corrects or question is None:
            continue
        # Full points if the user picked any of the tied correct answers.
        if answer_in(pred.answer, corrects):
            total += question.points
    return total


async def compute_bonus_hit_rates(
    session: AsyncSession,
    competition_id: uuid.UUID | None = None,
) -> list[BonusHitRate]:
    """Pool-wide hit rate for every RESOLVED bonus question.

    For each question that has a recorded answer, counts how many eligible
    entries picked (any of) the correct answer(s), over the eligible-entry
    denominator (SUBMITTED, not disabled, not withdrawn — the same
    `eligible_entry_ids_select()` predicate rarity and the leaderboard use,
    so the count is consistent with every other pool stat). Matching goes
    through `answer_in()` — case/accent-insensitive, identical semantics to
    the per-entry scorer `calculate_bonus_points`, so the aggregate can
    never disagree with an individual's own hit/miss. Unresolved questions
    are omitted entirely (no answer to score against yet)."""
    from sqlalchemy import func

    from app.services.scoring import eligible_entry_ids_select

    ans_q = select(BonusAnswer)
    if competition_id is not None:
        ans_q = ans_q.where(BonusAnswer.competition_id == competition_id)
    ans_rows = (await session.execute(ans_q)).scalars().all()
    if not ans_rows:
        return []

    correct_by_qid: dict[str, list[str]] = {}
    for a in ans_rows:
        correct_by_qid.setdefault(a.question_id, []).append(a.correct_answer)

    eligible_select = eligible_entry_ids_select()
    eligible_count = (
        await session.execute(
            select(func.count()).select_from(eligible_select.subquery())
        )
    ).scalar_one()

    # Distinct eligible entries whose pick for each question matches. Loaded
    # once and matched in Python via answer_in (SQL `IN` would miss
    # case/accent variants the real scorer counts).
    hit_entries_by_qid: dict[str, set] = {qid: set() for qid in correct_by_qid}
    if eligible_count:
        pred_rows = (
            await session.execute(
                select(BonusPrediction)
                .where(BonusPrediction.question_id.in_(list(correct_by_qid.keys())))
                .where(BonusPrediction.entry_id.in_(eligible_entry_ids_select()))
            )
        ).scalars().all()
        for pred in pred_rows:
            corrects = correct_by_qid.get(pred.question_id)
            if corrects and answer_in(pred.answer, corrects):
                hit_entries_by_qid[pred.question_id].add(pred.entry_id)

    return [
        BonusHitRate(
            question_id=qid,
            correct_answers=sorted(corrects),
            hit_count=len(hit_entries_by_qid[qid]),
            eligible_count=eligible_count,
            hit_rate=(len(hit_entries_by_qid[qid]) / eligible_count) if eligible_count else 0.0,
        )
        for qid, corrects in correct_by_qid.items()
    ]


# ---- Auto-computed answers --------------------------------------------------
#
# The four group-stage questions (Goal Machine, Toothless Attack, The Sieve,
# The Fortress) and the two top/flop questions (Dark Horse, Bottlers) can be
# derived directly from fixtures + scores. The Awards section cannot — those
# come from the FIFA awards ceremony and must be entered manually.
#
# The compute functions below are pure (operate on plain data, no DB I/O)
# so they're trivially unit-testable. `compute_bonus_answers_for_competition`
# is the thin async orchestrator that loads from the DB and calls them.


# Stage rank for "how far did this team progress". Group stage = 0, winner
# = 6. Used by the dark-horse and bottlers calculators.
_STAGE_ORDER = ["group", "round_of_32", "round_of_16", "quarter_final", "semi_final", "final"]
_STAGE_RANK = {s: i for i, s in enumerate(_STAGE_ORDER)}
# Winner is one step above "final" — represents winning the final (not just
# reaching it). Used in dark-horse comparisons so a winning underdog out-
# ranks a finalist who lost the final.
_WINNER_RANK = len(_STAGE_ORDER)


def compute_group_stats(fixtures_with_scores: Iterable[Fixture]) -> dict[str, dict[str, int]]:
    """Aggregate {team: {gf, ga}} from finished group-stage fixtures only.

    Pure function — pass it any iterable of Fixture objects with their
    .score relationship preloaded. Fixtures without a final score, with
    placeholder team names ("TBD"), or in non-group stages are skipped.
    """
    stats: dict[str, dict[str, int]] = {}
    for f in fixtures_with_scores:
        if f.stage != "group":
            continue
        if f.status != MatchStatus.FINISHED:
            continue
        score = getattr(f, "score", None)
        if score is None:
            continue
        if not f.home_team or f.home_team == "TBD":
            continue
        if not f.away_team or f.away_team == "TBD":
            continue
        h = stats.setdefault(f.home_team, {"gf": 0, "ga": 0})
        a = stats.setdefault(f.away_team, {"gf": 0, "ga": 0})
        h["gf"] += score.home_score
        h["ga"] += score.away_score
        a["gf"] += score.away_score
        a["ga"] += score.home_score
    return stats


def compute_team_progress(fixtures_with_scores: Iterable[Fixture]) -> dict[str, str]:
    """For each team, the furthest stage they have *definitively* reached
    according to completed fixtures. A team that only appears in group
    fixtures (no knockout appearance yet) ends up at "group". The winner
    of a finished final gets the special "winner" stage."""
    progress: dict[str, str] = {}
    final_winner: str | None = None
    for f in fixtures_with_scores:
        if f.status != MatchStatus.FINISHED:
            continue
        if f.stage not in _STAGE_RANK:
            continue
        if not f.home_team or f.home_team == "TBD":
            continue
        if not f.away_team or f.away_team == "TBD":
            continue
        rank = _STAGE_RANK[f.stage]
        for team in (f.home_team, f.away_team):
            existing = _STAGE_RANK.get(progress.get(team, "group"), 0)
            if rank > existing or team not in progress:
                progress[team] = f.stage
        # Determine the final winner — used to bump them past plain "final".
        if f.stage == "final":
            score = getattr(f, "score", None)
            if score is not None:
                outcome = score.outcome
                if outcome == "1":
                    final_winner = f.home_team
                elif outcome == "2":
                    final_winner = f.away_team
    if final_winner:
        progress[final_winner] = "winner"
    return progress


def _teams_with_extremum(
    stats: dict[str, dict[str, int]], key: str, want_max: bool
) -> list[str]:
    """Return the team(s) whose stats[key] is the max (or min). Empty if
    no stats. Ties are returned in alphabetical order so the list is
    deterministic — admins reading the auto-suggestion see a stable set."""
    if not stats:
        return []
    values = [s[key] for s in stats.values()]
    target = max(values) if want_max else min(values)
    return sorted(t for t, s in stats.items() if s[key] == target)


def compute_dark_horse(progress: dict[str, str], fifa_top: set[str]) -> list[str]:
    """Team(s) NOT in `fifa_top` with the furthest progression. Empty if
    no non-top team has played any completed match yet."""
    if not progress:
        return []
    candidates: dict[str, int] = {}
    for team, stage in progress.items():
        if team in fifa_top:
            continue
        rank = _WINNER_RANK if stage == "winner" else _STAGE_RANK.get(stage, 0)
        candidates[team] = rank
    if not candidates:
        return []
    max_rank = max(candidates.values())
    return sorted(t for t, r in candidates.items() if r == max_rank)


def compute_bottlers(
    progress: dict[str, str], fifa_top: set[str], competition_teams: set[str]
) -> list[str]:
    """Top-N team(s) with the earliest exit (lowest stage rank). Only
    considers top-N teams that are actually in the competition. A top
    team with no finished fixtures yet is treated as still at "group"."""
    top_in_comp = [t for t in fifa_top if t in competition_teams]
    if not top_in_comp:
        return []
    ranks = {t: _STAGE_RANK.get(progress.get(t, "group"), 0) for t in top_in_comp}
    # Skip the winner — they didn't "bottle" anything.
    ranks = {t: r for t, r in ranks.items() if progress.get(t) != "winner"}
    if not ranks:
        return []
    min_rank = min(ranks.values())
    return sorted(t for t, r in ranks.items() if r == min_rank)


async def compute_bonus_answers_for_competition(
    session: AsyncSession,
    competition_id: uuid.UUID,
) -> dict[str, list[str]]:
    """Compute auto-derived correct answers for every question that
    *can* be auto-derived. Awards-category questions get an empty list
    (they're manual-only). The returned dict maps question_id → list of
    correct answers (multiple = a tie). Callers can decide whether to
    surface as a suggestion (current admin flow) or persist directly."""
    fx_rows = (
        await session.execute(
            select(Fixture)
            .where(Fixture.competition_id == competition_id)
            .options(selectinload(Fixture.score))
        )
    ).scalars().all()

    stats = compute_group_stats(fx_rows)
    progress = compute_team_progress(fx_rows)
    competition_teams: set[str] = set()
    for f in fx_rows:
        for t in (f.home_team, f.away_team):
            if t and t != "TBD":
                competition_teams.add(t)

    cfg = _get_bonus_config()
    fifa_top = set(cfg.get("fifa_top_teams", []) or [])

    return {
        "most_goals_scored_group": _teams_with_extremum(stats, "gf", True),
        "least_goals_scored_group": _teams_with_extremum(stats, "gf", False),
        "most_goals_conceded_group": _teams_with_extremum(stats, "ga", True),
        "least_goals_conceded_group": _teams_with_extremum(stats, "ga", False),
        "dark_horse": compute_dark_horse(progress, fifa_top),
        "flop": compute_bottlers(progress, fifa_top, competition_teams),
        # Awards questions intentionally omitted — manual only.
    }
