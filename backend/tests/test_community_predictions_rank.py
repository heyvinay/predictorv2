"""Tests for CommunityPrediction.rank (B.3)."""

from app.schemas.prediction import CommunityPrediction


def test_community_prediction_rank_field_optional_and_defaults_none():
    """rank exists, is optional, defaults to None."""
    fields = CommunityPrediction.model_fields
    assert "rank" in fields
    assert fields["rank"].default is None


def test_community_prediction_accepts_integer_rank():
    cp = CommunityPrediction(
        user_name="Alice",
        entry_reference="REF1",
        entry_name="Alice's pick",
        home_score=2,
        away_score=1,
        rank=7,
    )
    assert cp.rank == 7


def test_community_prediction_accepts_null_rank():
    cp = CommunityPrediction(
        user_name="Bob",
        entry_reference="REF2",
        entry_name="Bob's pick",
        home_score=0,
        away_score=0,
    )
    assert cp.rank is None
