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


# ─── compute_points_for_finished_fixtures (pure helper) ─────────────────

from uuid import uuid4

from app.services.predictions import compute_points_for_finished_fixtures


def _fake_fixture(fixture_id, *, status, home_score=None, away_score=None):
    """Minimal duck-typed Fixture for the pure helper. The helper only
    reads `id`, `status`, and `score.{home_score,away_score}` — passing
    a SimpleNamespace avoids depending on the full SQLModel."""
    from types import SimpleNamespace

    score = (
        SimpleNamespace(home_score=home_score, away_score=away_score)
        if home_score is not None
        else None
    )
    return SimpleNamespace(id=fixture_id, status=status, score=score)


def _fake_pred(fixture_id, h, a):
    from types import SimpleNamespace
    return SimpleNamespace(fixture_id=fixture_id, home_score=h, away_score=a)


SCORING_CONFIG = {
    "mode": "logarithmic",
    "match": {"correct_outcome": 5, "exact_score": 10, "rarity_cap": 10},
}


def test_compute_points_exact_pick():
    """Exact pick on a finished fixture: base_kind='exact', base=15."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="finished", home_score=2, away_score=1)
    pred = _fake_pred(fid, 2, 1)
    agreements = {fid: {"agrees_exact": 1, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    assert fid in result
    out = result[fid]
    assert out.base_kind == "exact"
    assert out.base == 15
    assert out.rarity >= 0  # exact engine value verified separately


def test_compute_points_result_only_pick():
    """Correct-outcome-only pick: base_kind='result', base=5."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="finished", home_score=2, away_score=1)
    pred = _fake_pred(fid, 3, 0)  # home win predicted, home wins, scoreline wrong
    agreements = {fid: {"agrees_exact": 0, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    out = result[fid]
    assert out.base_kind == "result"
    assert out.base == 5


def test_compute_points_miss():
    """Wrong outcome: base_kind='miss', base=0, total=0."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="finished", home_score=2, away_score=1)
    pred = _fake_pred(fid, 0, 3)  # away win predicted, home wins
    agreements = {fid: {"agrees_exact": 0, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    out = result[fid]
    assert out.base_kind == "miss"
    assert out.base == 0
    assert out.total == 0


def test_compute_points_unfinished_fixture_excluded():
    """Unfinished fixture: not in the returned map (caller renders None)."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="scheduled")
    pred = _fake_pred(fid, 2, 1)
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], {}, SCORING_CONFIG
    )
    assert fid not in result


def test_compute_points_live_fixture_excluded():
    """LIVE fixture: not in the returned map (banking is at full-time)."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="live", home_score=1, away_score=0)
    pred = _fake_pred(fid, 2, 1)
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], {}, SCORING_CONFIG
    )
    assert fid not in result


def test_compute_points_total_equals_base_plus_rarity():
    """Invariant: total == base + rarity for every returned entry."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="finished", home_score=2, away_score=1)
    pred = _fake_pred(fid, 2, 1)
    agreements = {fid: {"agrees_exact": 1, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    out = result[fid]
    assert out.total == out.base + out.rarity


def test_compute_points_accepts_real_matchstatus_enum():
    """Real Fixture rows carry MatchStatus(str, Enum), not plain strings.
    str(MatchStatus.FINISHED) is "MatchStatus.FINISHED" on Python 3.11 —
    the helper must unwrap .value or it silently skips every finished
    fixture in production while string-based tests stay green."""
    from app.models.fixture import MatchStatus

    fid = uuid4()
    fixture = _fake_fixture(
        fid, status=MatchStatus.FINISHED, home_score=2, away_score=1
    )
    pred = _fake_pred(fid, 2, 1)
    agreements = {fid: {"agrees_exact": 1, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    assert fid in result
    assert result[fid].base_kind == "exact"
