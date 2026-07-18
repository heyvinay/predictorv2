"""Final podium + Trionda side prize (Plan A)."""

from dataclasses import dataclass

import pytest

from app.services.group_stage_winner import group_stage_total
from app.services.tournament_champion import pick_trionda_recipient


class _Phase1:
    match_outcome_points = 100
    exact_score_points = 40
    hybrid_bonus_points = 7


class _Breakdown:
    phase1 = _Phase1()


class _Entry:
    breakdown = _Breakdown()
    bonus_group_points = 10


def test_group_stage_total_is_shared_and_stable():
    assert group_stage_total(_Entry()) == 157


@dataclass
class _Row:
    entry_id: str
    user_name: str
    position: int
    total_points: int
    gs_total: int


def _rows(*specs):
    # specs: (entry_id, position, total, gs_total)
    return [
        _Row(entry_id=e, user_name=e.upper(), position=p, total_points=t, gs_total=g)
        for (e, p, t, g) in specs
    ]


def test_trionda_direct_runner_up_eligible():
    rows = _rows(("champ", 1, 612, 348), ("kevin", 2, 598, 340), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "kevin"
    assert out.requires_draw is False
    assert out.reason == "runner-up on total points"


def test_trionda_skips_group_stage_cash_winner():
    # kevin at #2 also holds the max group-stage total → ineligible, ball walks to #3
    rows = _rows(("champ", 1, 612, 348), ("kevin", 2, 598, 356), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "john"
    assert "not eligible" in out.reason


def test_trionda_shared_gs_cash_both_skipped():
    # champ and kevin SHARE max gs_total (tie) → both ineligible; champ is champion anyway
    rows = _rows(("champ", 1, 612, 356), ("kevin", 2, 598, 356), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "john"


def test_trionda_rank_tie_breaks_on_group_stage_points():
    rows = _rows(
        ("champ", 1, 612, 356),
        ("a", 2, 598, 330),
        ("b", 2, 598, 345),  # same rank, more gs points → b gets the ball
    )
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "b"
    assert out.requires_draw is False


def test_trionda_persisting_tie_requires_draw():
    rows = _rows(
        ("champ", 1, 612, 356),
        ("a", 2, 598, 330),
        ("b", 2, 598, 330),
    )
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.requires_draw is True
    assert {c.entry_id for c in out.draw_candidates} == {"a", "b"}
    assert out.recipient is None


def test_trionda_shared_champions_shift_runner_up_rank():
    # two joint champions at position 1 → runner-up rank is position 2
    rows = _rows(("c1", 1, 612, 356), ("c2", 1, 612, 340), ("a", 2, 598, 330))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "a"
