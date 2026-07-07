"""Tests for the knockout win-probability simulation engine.

Pure-function tests only in this file — no DB session, no async. The
engine's core (bracket enumeration + advancement collapse) is designed to
be exercised standalone; DB wiring (loading the live bracket state,
per-entry predictions, caching) is covered separately once the pure core
is proven correct.
"""

import uuid

from app.models.prediction import PredictionPhase, TeamPrediction
from app.services.scoring import calculate_advancement_points
from app.services.win_probability import (
    MatchSpec,
    build_advancement,
    entry_ko_points,
    enumerate_scenarios,
    simulate_pool,
)


def test_build_advancement_credits_seeding_and_winner_stage():
    """A fully-resolved 3-match tree (2 semis + a final) credits every
    seeded team with reaching the semi_final, and additionally credits
    each match's winner with reaching the next stage."""
    matches = {
        101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
        102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
        104: MatchSpec(stage="final", home_ref=101, away_ref=102),
    }
    winners = {101: "A", 102: "C", 104: "A"}

    advancement = build_advancement(matches, winners)

    assert advancement == {
        "A": "winner",
        "B": "semi_final",
        "C": "final",
        "D": "semi_final",
    }


def test_enumerate_scenarios_four_team_bracket_champion_odds_are_2_pow_neg_rounds():
    """Hand-enumerable case: 4 teams, 2 semis + a final, fully 50/50.

    Every team is 2 rounds from the trophy, so under a uniform per-match
    model each team's title probability must be exactly 2**-2 = 0.25 —
    the closed-form check the plan promised for team trophy-odds.
    """
    matches = {
        101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
        102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
        104: MatchSpec(stage="final", home_ref=101, away_ref=102),
    }
    unresolved = [101, 102, 104]

    champion_weight: dict[str, float] = {}
    total_weight = 0.0
    for winners, weight in enumerate_scenarios(matches, {}, unresolved):
        advancement = build_advancement(matches, winners)
        total_weight += weight
        for team, stage in advancement.items():
            if stage == "winner":
                champion_weight[team] = champion_weight.get(team, 0.0) + weight

    assert total_weight == 1.0
    assert set(champion_weight) == {"A", "B", "C", "D"}
    for team in ("A", "B", "C", "D"):
        assert champion_weight[team] == 0.25


def test_enumerate_scenarios_respects_already_known_winners():
    """A match already FINISHED (in known_winners) is not a free variable —
    only the matches in `unresolved` fork the scenario tree."""
    matches = {
        101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
        102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
        104: MatchSpec(stage="final", home_ref=101, away_ref=102),
    }
    # Semi 101 already finished: A beat B. Only 102 and 104 remain open.
    known_winners = {101: "A"}
    unresolved = [102, 104]

    scenarios = list(enumerate_scenarios(matches, known_winners, unresolved))

    assert len(scenarios) == 4  # 2**2, not 2**3
    for winners, weight in scenarios:
        assert winners[101] == "A"
        assert weight == 0.25


def test_enumerate_scenarios_single_unresolved_match_is_a_coin_flip():
    """A team already clinched a spot in the final (m=1) has exactly a
    50% title chance, and the other finalist the complementary 50%."""
    matches = {
        104: MatchSpec(stage="final", home_ref="A", away_ref="B"),
    }
    unresolved = [104]

    champion_weight: dict[str, float] = {}
    for winners, weight in enumerate_scenarios(matches, {}, unresolved):
        advancement = build_advancement(matches, winners)
        champion = advancement["A" if winners[104] == "A" else "B"]
        assert champion == "winner"
        champion_weight[winners[104]] = champion_weight.get(winners[104], 0.0) + weight

    assert champion_weight == {"A": 0.5, "B": 0.5}


POINTS_BY_STAGE = {
    "round_of_32": 20,
    "round_of_16": 30,
    "quarter_final": 40,
    "semi_final": 50,
    "final": 75,
    "winner": 100,
}


def test_entry_ko_points_awards_only_when_team_reached_at_least_predicted_stage():
    advancement = {"A": "winner", "B": "semi_final"}

    # Predicted exactly what happened.
    assert entry_ko_points([("A", "winner")], advancement, POINTS_BY_STAGE) == 100
    # Predicted less than the team actually achieved — still full credit
    # for the predicted (lower) stage, per calculate_advancement_points.
    assert entry_ko_points([("A", "semi_final")], advancement, POINTS_BY_STAGE) == 50
    # Predicted more than the team achieved — zero.
    assert entry_ko_points([("B", "final")], advancement, POINTS_BY_STAGE) == 0
    # Team not in advancement at all (eliminated before this stage) — zero.
    assert entry_ko_points([("Z", "round_of_32")], advancement, POINTS_BY_STAGE) == 0


def test_entry_ko_points_matches_real_calculate_advancement_points():
    """Parity check: our pure entry_ko_points must agree exactly with the
    live scoring engine's calculate_advancement_points for the same
    (team, stage, actual_advancement) inputs — this is the guarantee the
    whole simulator's per-entry scores rest on."""
    advancement = {"A": "winner", "B": "quarter_final", "C": "final"}
    cases = [
        ("A", "winner"),
        ("A", "semi_final"),
        ("B", "quarter_final"),
        ("B", "semi_final"),
        ("C", "final"),
        ("D", "round_of_16"),
    ]

    for team, stage in cases:
        ours = entry_ko_points([(team, stage)], advancement, POINTS_BY_STAGE)

        team_prediction = TeamPrediction(
            entry_id=uuid.uuid4(),
            team=team,
            stage=stage,
            phase=PredictionPhase.PHASE_1,
        )
        theirs = calculate_advancement_points(
            team_prediction, advancement, PredictionPhase.PHASE_1
        )

        assert ours == theirs, f"mismatch for ({team}, {stage}): {ours} != {theirs}"


def test_simulate_pool_four_team_bracket_ranks_entries_by_expected_outcome():
    """Hand-enumerable pool test: 2 semis + a final, 4 entries — one per
    team — each predicting only "my team wins the trophy". Since exactly
    one team becomes champion in every scenario, and each entry's score is
    either 100 (its pick won) or 0 (its pick didn't), each entry wins
    exactly when its team becomes champion: P(win) = 0.25 for all four,
    and — per the plan's "probabilities sum to 1" invariant — they sum to
    exactly 1.0 with no unattributed remainder.
    """
    matches = {
        101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
        102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
        104: MatchSpec(stage="final", home_ref=101, away_ref=102),
    }
    unresolved = [101, 102, 104]

    entries = {
        "entry-a": [("A", "winner")],
        "entry-b": [("B", "winner")],
        "entry-c": [("C", "winner")],
        "entry-d": [("D", "winner")],
    }

    result = simulate_pool(
        matches,
        known_winners={},
        unresolved=unresolved,
        entries=entries,
        points_by_stage=POINTS_BY_STAGE,
        base_points={eid: 0 for eid in entries},
    )

    total_p_win = sum(e.p_win for e in result.entries.values())
    assert round(total_p_win, 6) == 1.0

    for entry_id in entries:
        assert round(result.entries[entry_id].p_win, 6) == 0.25


def test_simulate_pool_ties_split_win_credit_evenly():
    """Two entries with identical predictions must split the win credit in
    every scenario where they'd otherwise tie for first — this is the
    "tie-splitting" the sum-to-1 invariant depends on."""
    matches = {104: MatchSpec(stage="final", home_ref="A", away_ref="B")}
    unresolved = [104]

    entries = {
        "entry-1": [("A", "winner")],
        "entry-2": [("A", "winner")],  # identical pick to entry-1
        "entry-3": [("B", "winner")],
    }

    result = simulate_pool(
        matches,
        known_winners={},
        unresolved=unresolved,
        entries=entries,
        points_by_stage=POINTS_BY_STAGE,
        base_points={eid: 0 for eid in entries},
    )

    # Whenever A wins (P=0.5), entry-1 and entry-2 tie for first and split
    # that scenario's win credit 50/50 -> each gets 0.25 from it.
    assert round(result.entries["entry-1"].p_win, 6) == 0.25
    assert round(result.entries["entry-2"].p_win, 6) == 0.25
    # entry-3 wins outright whenever B wins (P=0.5).
    assert round(result.entries["entry-3"].p_win, 6) == 0.5
    assert round(sum(e.p_win for e in result.entries.values()), 6) == 1.0
