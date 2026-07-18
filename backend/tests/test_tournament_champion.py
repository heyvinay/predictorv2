"""Final podium + Trionda side prize (Plan A)."""

import pytest

from app.services.group_stage_winner import group_stage_total


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
