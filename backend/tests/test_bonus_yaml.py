"""YAML-load tests for the bonus-question config.

These assertions pin down what `config/worldcup2026.yml` ships to the API
and downstream consumers. They double as drift guards — if someone adds an
awards question back without bumping the test, this fails fast; if the
fifa_top_teams list rotates a team out of the tournament, the
cross-reference test catches it before users see broken dropdowns.

No DB or HTTP fixtures — these read the real YAML via the same loader the
backend uses at runtime.
"""

from __future__ import annotations

from app.services.bonus import get_meta, get_questions


EXPECTED_QUESTION_IDS = {
    "most_goals_scored_group",
    "most_goals_conceded_group",
    "dark_horse",
    "flop",
}

EXPECTED_REMOVED_IDS = {
    "least_goals_scored_group",
    "least_goals_conceded_group",
    "best_player",
    "top_scorer",
    "best_young_player",
    "golden_glove",
}


class TestGetQuestions:
    def test_returns_exactly_four_questions(self):
        qs = get_questions()
        assert len(qs) == 4, f"Expected 4 questions, got {len(qs)}: {[q.id for q in qs]}"

    def test_ids_match_expected_set(self):
        ids = {q.id for q in get_questions()}
        assert ids == EXPECTED_QUESTION_IDS

    def test_removed_ids_are_absent(self):
        """All 6 removed question IDs (4 awards + 2 group-stage 'fewest')
        must not reappear. If they do, scoring rows that match them would
        be revived without the admin entering correct answers — silent."""
        ids = {q.id for q in get_questions()}
        for removed in EXPECTED_REMOVED_IDS:
            assert removed not in ids, f"Removed question {removed} is back"

    def test_group_stage_questions_worth_15_each(self):
        gs = [q for q in get_questions() if q.category == "group_stage"]
        assert len(gs) == 2
        for q in gs:
            assert q.points == 15, f"{q.id} should be 15 pts, got {q.points}"

    def test_top_flop_questions_worth_20_each(self):
        tf = [q for q in get_questions() if q.category == "top_flop"]
        assert len(tf) == 2
        for q in tf:
            assert q.points == 20, f"{q.id} should be 20 pts, got {q.points}"

    def test_dark_horse_input_type_is_team_outside_top_n(self):
        q = next(q for q in get_questions() if q.id == "dark_horse")
        assert q.input_type == "team_outside_top_n"

    def test_flop_input_type_is_team_in_top_n(self):
        q = next(q for q in get_questions() if q.id == "flop")
        assert q.input_type == "team_in_top_n"

    def test_group_stage_input_types_remain_plain_team(self):
        gs = [q for q in get_questions() if q.category == "group_stage"]
        for q in gs:
            assert q.input_type == "team", f"{q.id} should stay 'team', got {q.input_type}"

    def test_label_top_n_substitution(self):
        """Labels with `{top_n}` get the configured number injected."""
        meta = get_meta()
        dark_horse = next(q for q in get_questions() if q.id == "dark_horse")
        assert "{top_n}" not in dark_horse.label
        assert str(meta.top_n) in dark_horse.label


class TestGetMeta:
    def test_top_n_is_ten(self):
        assert get_meta().top_n == 10

    def test_fifa_top_teams_length_is_ten(self):
        assert len(get_meta().fifa_top_teams) == 10

    def test_morocco_present(self):
        """Morocco entered the top 10 in 2024 (currently rank 8) and is
        qualified for 2026 — the auto-resolver needs them in the list."""
        assert "Morocco" in get_meta().fifa_top_teams

    def test_italy_absent(self):
        """Italy fell to rank 12 and failed to qualify for 2026 — must
        not appear in fifa_top_teams or the `flop` dropdown would offer
        a team that can't be eliminated (because they aren't playing)."""
        assert "Italy" not in get_meta().fifa_top_teams

    def test_first_five_match_april_2026_ranking(self):
        """France #1, Spain #2, Argentina #3, England #4, Portugal #5.
        Order matters — the YAML keeps FIFA rank order so the UI can
        display the list in a meaningful sequence."""
        top5 = get_meta().fifa_top_teams[:5]
        assert top5 == ["France", "Spain", "Argentina", "England", "Portugal"]


class TestYamlCrossReference:
    def test_every_fifa_top_team_is_in_a_group(self):
        """A team in `fifa_top_teams` that doesn't appear in any group
        means the resolver would silently skip it. This guards against
        future drift where a renamed/removed team slips through.
        """
        from app.config import get_tournament_config

        cfg = get_tournament_config()
        groups = cfg.get("groups", {})
        all_teams_in_groups: set[str] = set()
        for teams in groups.values():
            all_teams_in_groups.update(teams)

        missing = [t for t in get_meta().fifa_top_teams if t not in all_teams_in_groups]
        assert not missing, (
            f"FIFA top teams not in any group (qualified but mis-named?): {missing}. "
            f"Check naming consistency between bonus.fifa_top_teams and groups: in YAML."
        )

    def test_groups_have_no_tbd_placeholders(self):
        """Pre-draw the YAML held 'TBD' placeholders. Post-draw (Dec 2025)
        every group must be fully populated."""
        from app.config import get_tournament_config

        cfg = get_tournament_config()
        groups = cfg.get("groups", {})
        offenders: list[tuple[str, str]] = []
        for letter, teams in groups.items():
            for t in teams:
                if t == "TBD" or not t:
                    offenders.append((letter, t))
        assert not offenders, f"Groups still have TBD placeholders: {offenders}"

    def test_groups_have_twelve_letters_of_four_teams(self):
        """48-team format: 12 groups × 4 teams. Sanity check."""
        from app.config import get_tournament_config

        cfg = get_tournament_config()
        groups = cfg.get("groups", {})
        assert len(groups) == 12, f"Expected 12 groups, got {len(groups)}"
        for letter, teams in groups.items():
            assert len(teams) == 4, f"Group {letter} has {len(teams)} teams"
