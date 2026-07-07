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
    BonusSimulationConfig,
    MatchSpec,
    build_advancement,
    entry_ko_points,
    enumerate_scenarios,
    resolve_known_state,
    simulate_bonus_points,
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


def test_resolve_known_state_marks_a_finished_match_as_a_known_winner():
    matches = {
        101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
        102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
        104: MatchSpec(stage="final", home_ref=101, away_ref=102),
    }
    # 101 finished (A won); 102 and 104 not yet played.
    raw_outcomes = {101: "1"}

    known_winners, unresolved = resolve_known_state(matches, raw_outcomes)

    assert known_winners == {101: "A"}
    assert sorted(unresolved) == [102, 104]


def test_resolve_known_state_treats_a_match_as_unresolved_if_its_own_feeders_are_undecided():
    """A match can be marked FINISHED in the DB while its feeder match
    hasn't resolved (a transient data-lag edge case) — resolve_known_state
    must not crash on a stale/inconsistent outcome; it defers that match
    to `unresolved` rather than guessing."""
    matches = {
        101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
        102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
        104: MatchSpec(stage="final", home_ref=101, away_ref=102),
    }
    # 104 (the final) is reported as decided, but neither semi is —
    # its participants aren't actually known yet.
    raw_outcomes = {104: "1"}

    known_winners, unresolved = resolve_known_state(matches, raw_outcomes)

    assert known_winners == {}
    assert sorted(unresolved) == [101, 102, 104]


def test_resolve_known_state_fully_resolved_bracket_has_no_unresolved_matches():
    matches = {
        101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
        102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
        104: MatchSpec(stage="final", home_ref=101, away_ref=102),
    }
    raw_outcomes = {101: "1", 102: "2", 104: "2"}

    known_winners, unresolved = resolve_known_state(matches, raw_outcomes)

    assert known_winners == {101: "A", 102: "D", 104: "D"}
    assert unresolved == []


def test_simulate_pool_team_stage_odds_match_closed_form_2_pow_neg_rounds():
    """The plan promises team trophy-odds fall out of the same enumeration
    used for entry ranking, and that they must equal 2**-rounds — this
    pins that invariant at the simulate_pool level (not just the raw
    enumerate_scenarios level already covered above), since that's what
    the API endpoint will actually serve to the frontend."""
    matches = {
        101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
        102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
        104: MatchSpec(stage="final", home_ref=101, away_ref=102),
    }
    unresolved = [101, 102, 104]

    result = simulate_pool(
        matches,
        known_winners={},
        unresolved=unresolved,
        entries={"entry-a": [("A", "winner")]},
        points_by_stage=POINTS_BY_STAGE,
        base_points={"entry-a": 0},
    )

    for team in ("A", "B", "C", "D"):
        assert round(result.team_stage_odds[team]["semi_final"], 6) == 1.0
        assert round(result.team_stage_odds[team]["winner"], 6) == 0.25


def test_simulate_pool_result_carries_a_computed_at_timestamp():
    """The API's `meta.computed_at` must reflect when the simulation
    actually ran, not when a cached result happens to be served — so
    PoolSimulationResult stamps its own construction time."""
    from datetime import datetime, timezone

    matches = {104: MatchSpec(stage="final", home_ref="A", away_ref="B")}
    before = datetime.now(timezone.utc)

    result = simulate_pool(
        matches,
        known_winners={},
        unresolved=[104],
        entries={"entry-a": [("A", "winner")]},
        points_by_stage=POINTS_BY_STAGE,
        base_points={"entry-a": 0},
    )

    after = datetime.now(timezone.utc)
    assert before <= result.computed_at <= after


class TestBonusSimulation:
    """Dark Horse / Bottlers are auto-computed from bracket progress
    (services.bonus.compute_dark_horse / compute_bottlers) — their
    "correct answer" can change as the knockout bracket plays out, so
    an UNRESOLVED question (no admin-confirmed BonusAnswer yet) must be
    simulated per scenario just like a KO advancement pick. A RESOLVED
    question must NOT be re-simulated — its real, fixed answer is
    already baked into the entry's banked base_points."""

    def test_unresolved_dark_horse_awards_points_only_in_matching_scenarios(self):
        matches = {
            101: MatchSpec(stage="semi_final", home_ref="A", away_ref="B"),
            102: MatchSpec(stage="semi_final", home_ref="C", away_ref="D"),
            104: MatchSpec(stage="final", home_ref=101, away_ref=102),
        }
        config = BonusSimulationConfig(
            fifa_top_teams=frozenset({"A", "B"}),
            unresolved_questions=frozenset({"dark_horse"}),
            points_by_question={"dark_horse": 20},
        )
        picks = {"dark_horse": "C"}

        won_weight = 0.0
        for winners, weight in enumerate_scenarios(matches, {}, [101, 102, 104]):
            advancement = build_advancement(matches, winners)
            won_weight += weight * (simulate_bonus_points(picks, advancement, config) > 0)

        # C is a non-top team; it's the dark horse exactly when it goes
        # further than D (the other non-top team) — i.e. whenever C wins
        # its semi (P=0.5), regardless of the final's outcome.
        assert round(won_weight, 6) == 0.5

    def test_resolved_question_is_never_simulated_even_if_pick_would_match(self):
        """Future-proofing: once a question is resolved, this function
        must ignore it entirely — the real settled points live in
        base_points, not here. Passing a config that omits the question
        from unresolved_questions must produce zero regardless of what
        the scenario's computed answer would have been."""
        matches = {104: MatchSpec(stage="final", home_ref="A", away_ref="B")}
        config = BonusSimulationConfig(
            fifa_top_teams=frozenset(),
            unresolved_questions=frozenset(),  # both questions already resolved
            points_by_question={"dark_horse": 20, "flop": 20},
        )
        picks = {"dark_horse": "A", "flop": "B"}

        for winners, _ in enumerate_scenarios(matches, {}, [104]):
            advancement = build_advancement(matches, winners)
            assert simulate_bonus_points(picks, advancement, config) == 0

    def test_mixed_resolution_only_simulates_the_unresolved_one(self):
        """dark_horse resolved, flop still open — only flop should ever
        contribute points from this function."""
        matches = {104: MatchSpec(stage="final", home_ref="A", away_ref="B")}
        config = BonusSimulationConfig(
            fifa_top_teams=frozenset({"A", "B"}),
            unresolved_questions=frozenset({"flop"}),
            points_by_question={"dark_horse": 20, "flop": 20},
        )
        # A correct dark_horse pick must never pay here (resolved); a
        # correct flop pick (A is a top team eliminated at the final,
        # i.e. it lost) must pay.
        picks = {"dark_horse": "A", "flop": "A"}

        for winners, _ in enumerate_scenarios(matches, {}, [104]):
            advancement = build_advancement(matches, winners)
            points = simulate_bonus_points(picks, advancement, config)
            # A "bottles" (flop) only in the scenario where it LOSES the
            # final (winners[104] == "B") — winning it is not bottling.
            if winners[104] == "B":
                assert points == 20
            else:
                assert points == 0

    def test_simulate_pool_folds_bonus_points_into_scores(self):
        """End-to-end: simulate_pool must add the bonus delta on top of
        base_points + KO delta, not require a second enumeration pass.

        entry-1: base 100 + flop pick "A" (unresolved, +20 whenever A
        loses the final). entry-2: flat base 110, no bonus picks.
        Without the bonus wired in, entry-2 always wins (110 > 100) —
        P(entry-1 wins) would be 0. With it wired in, entry-1 overtakes
        entry-2 (120 > 110) exactly when A loses, so P(entry-1 wins)
        must land at 0.5, not 0 — proving the delta actually changed
        who wins, not just that it computed without crashing.
        """
        matches = {104: MatchSpec(stage="final", home_ref="A", away_ref="B")}
        unresolved = [104]
        config = BonusSimulationConfig(
            fifa_top_teams=frozenset({"A", "B"}),
            unresolved_questions=frozenset({"flop"}),
            points_by_question={"dark_horse": 20, "flop": 20},
        )
        entries = {"entry-1": [], "entry-2": []}
        bonus_picks = {"entry-1": {"flop": "A"}}

        result = simulate_pool(
            matches,
            known_winners={},
            unresolved=unresolved,
            entries=entries,
            points_by_stage=POINTS_BY_STAGE,
            base_points={"entry-1": 100, "entry-2": 110},
            entry_bonus_picks=bonus_picks,
            bonus_config=config,
        )

        assert round(result.entries["entry-1"].p_win, 6) == 0.5
        assert round(result.entries["entry-2"].p_win, 6) == 0.5
