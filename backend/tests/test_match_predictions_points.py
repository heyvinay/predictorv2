"""Tests for MatchPredictionRead.points (B.1)."""

import pytest

from app.schemas.prediction import MatchPredictionRead, PickPointsOut


def test_pick_points_out_has_expected_fields():
    """PickPointsOut carries base, base_kind, rarity, total."""
    pp = PickPointsOut(base=15, base_kind="exact", rarity=3, total=18)
    assert pp.base == 15
    assert pp.base_kind == "exact"
    assert pp.rarity == 3
    assert pp.total == 18


def test_pick_points_out_base_kind_constrained():
    """base_kind only accepts the three documented literals."""
    with pytest.raises(ValueError):
        PickPointsOut(base=0, base_kind="bogus", rarity=0, total=0)


def test_match_prediction_read_points_field_optional_and_defaults_none():
    """MatchPredictionRead.points exists, is optional, defaults to None."""
    fields = MatchPredictionRead.model_fields
    assert "points" in fields, "points field must exist on MatchPredictionRead"
    # Optional → default is None
    assert fields["points"].default is None
