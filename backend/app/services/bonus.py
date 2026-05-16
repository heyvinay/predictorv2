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
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_tournament_config
from app.models.bonus import BonusAnswer, BonusPrediction


BonusCategory = Literal["group_stage", "top_flop", "awards"]
BonusInputType = Literal["team", "player"]


@dataclass
class BonusQuestion:
    """One question as rendered for the wizard / admin UI."""

    id: str
    category: BonusCategory
    label: str  # already has {top_n} substituted
    input_type: BonusInputType
    points: int


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
    """Compare two free-text answers leniently."""
    return _normalize(user_answer) == _normalize(correct_answer)


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
    # Load all bonus answers (optionally filtered by competition).
    ans_q = select(BonusAnswer)
    if competition_id is not None:
        ans_q = ans_q.where(BonusAnswer.competition_id == competition_id)
    ans_rows = (await session.execute(ans_q)).scalars().all()
    if not ans_rows:
        return 0

    correct_by_qid: dict[str, str] = {a.question_id: a.correct_answer for a in ans_rows}

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
        correct = correct_by_qid.get(pred.question_id)
        question = questions_by_id.get(pred.question_id)
        if correct is None or question is None:
            continue
        if answers_match(pred.answer, correct):
            total += question.points
    return total
