"""Tests for the knockout match-detail bundle.

Mirrors the testing style of test_community_predictions.py — schema
validation + pure-helper coverage + blind-pool gate replication. The
full integration of the service against a seeded DB lives in higher-
level fixture-aware tests; this file pins the building blocks.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.fixture import Fixture, MatchStatus
from app.schemas.ko_match_detail import (
    KoCohortBreakdown,
    KoExposedEntry,
    KoImplications,
    KoImplicationSide,
    KoMatchDetailResponse,
    KoMostExposed,
    KoPoolRollEntry,
    KoPoolSplit,
    KoPoolSplitSide,
)
from app.services.ko_match_detail import _cohort_of, _pct


class TestCohortMapping:
    """`_cohort_of` collapses User.employer to atlas/jmfa/guests."""

    def test_atlas(self):
        assert _cohort_of("atlas") == "atlas"

    def test_jmfa(self):
        assert _cohort_of("jmfa") == "jmfa"

    def test_neither_falls_to_guests(self):
        assert _cohort_of("neither") == "guests"

    def test_null_falls_to_guests(self):
        assert _cohort_of(None) == "guests"

    def test_unknown_employer_falls_to_guests(self):
        # Future-proofing — any new employer string lands in Guests rather
        # than silently appearing as its own cohort. Adding a new bucket
        # is a deliberate code change.
        assert _cohort_of("anthropic") == "guests"


class TestPercentHelper:
    """`_pct` is rounding-correct and zero-safe."""

    def test_zero_total_returns_zero(self):
        assert _pct(0, 0) == 0

    def test_negative_total_returns_zero(self):
        # Defensive — total should never be negative, but the guard
        # exists so a bad call doesn't crash the response.
        assert _pct(5, -3) == 0

    def test_exact_half(self):
        assert _pct(91, 183) == 50

    def test_rounds_half_to_even_or_up(self):
        # round() uses banker's rounding in Py3; 50.0 → 50 either way.
        # This pins behavior so a renumber here would be noticed.
        assert _pct(50, 100) == 50

    def test_rounds_high(self):
        assert _pct(142, 183) == 78

    def test_rounds_low(self):
        assert _pct(41, 183) == 22


class TestKoSchemas:
    """The bundled response composes correctly from its sub-objects."""

    def _split_side(self, team: str, count: int, total: int) -> KoPoolSplitSide:
        return KoPoolSplitSide(
            team=team,
            count=count,
            pct=round(100 * count / total) if total else 0,
            cohorts=KoCohortBreakdown(atlas=0, jmfa=0, guests=count),
        )

    def test_round_trip_payload(self):
        fixture_id = uuid.uuid4()
        entry_a = uuid.uuid4()

        payload = KoMatchDetailResponse(
            fixture_id=fixture_id,
            home_team="South Africa",
            away_team="Canada",
            stage="round_of_32",
            pool_split=KoPoolSplit(
                total=183,
                home=self._split_side("South Africa", 41, 183),
                away=self._split_side("Canada", 142, 183),
            ),
            implications=KoImplications(
                home=KoImplicationSide(
                    team="South Africa",
                    r32_outcome=41,
                    alive_r16=12,
                    alive_qf=3,
                    alive_sf=0,
                    alive_final=0,
                    alive_winner=0,
                ),
                away=KoImplicationSide(
                    team="Canada",
                    r32_outcome=142,
                    alive_r16=88,
                    alive_qf=23,
                    alive_sf=8,
                    alive_final=2,
                    alive_winner=0,
                ),
            ),
            most_exposed=KoMostExposed(
                home=[],
                away=[
                    KoExposedEntry(
                        entry_id=entry_a,
                        user_name="James Vella",
                        entry_reference="WC26-000007",
                        entry_name="Entry 1",
                        rank=1,
                        points_at_stake=110,  # 20+40+50 — R32+QF+SF
                        stages_at_stake=["round_of_32", "quarter_final", "semi_final"],
                    ),
                ],
            ),
            pool_roll=[
                KoPoolRollEntry(
                    entry_id=entry_a,
                    user_name="James Vella",
                    entry_reference="WC26-000007",
                    entry_name="Entry 1",
                    pick="Canada",
                    rank=1,
                ),
            ],
        )

        assert payload.fixture_id == fixture_id
        assert payload.pool_split.total == 183
        assert payload.pool_split.home.pct == 22
        assert payload.pool_split.away.pct == 78
        assert payload.implications.away.alive_qf == 23
        assert payload.most_exposed.away[0].points_at_stake == 110
        assert payload.pool_roll[0].pick == "Canada"

    def test_empty_pool_is_valid(self):
        """Zero eligible entries shouldn't blow up the schema."""
        payload = KoMatchDetailResponse(
            fixture_id=uuid.uuid4(),
            home_team="A",
            away_team="B",
            stage="round_of_32",
            pool_split=KoPoolSplit(
                total=0,
                home=KoPoolSplitSide(
                    team="A", count=0, pct=0,
                    cohorts=KoCohortBreakdown(atlas=0, jmfa=0, guests=0),
                ),
                away=KoPoolSplitSide(
                    team="B", count=0, pct=0,
                    cohorts=KoCohortBreakdown(atlas=0, jmfa=0, guests=0),
                ),
            ),
            implications=KoImplications(
                home=KoImplicationSide(
                    team="A", r32_outcome=0, alive_r16=0, alive_qf=0,
                    alive_sf=0, alive_final=0, alive_winner=0,
                ),
                away=KoImplicationSide(
                    team="B", r32_outcome=0, alive_r16=0, alive_qf=0,
                    alive_sf=0, alive_final=0, alive_winner=0,
                ),
            ),
            most_exposed=KoMostExposed(home=[], away=[]),
            pool_roll=[],
        )
        assert payload.pool_split.total == 0
        assert payload.most_exposed.home == []


class TestKoBlindPoolGate:
    """The endpoint's gate is the same shape as /community's.

    Replicates the gate logic against fixture mocks so a future refactor
    of the endpoint can't silently invert the condition. The endpoint
    also adds a knockout-stage gate (404 for group fixtures) — that part
    is exercised here too.
    """

    LOCK_MINUTES = 5
    KNOCKOUT_STAGES = {
        "round_of_32", "round_of_16", "quarter_final", "semi_final", "final",
    }

    def _gate_403(
        self, fixture, *, deadline_passed: bool
    ) -> bool:
        """Replicate the visibility gate (same shape as the endpoint)."""
        return (
            not deadline_passed
            and not fixture.is_locked(self.LOCK_MINUTES)
            and fixture.status != MatchStatus.FINISHED
        )

    def _stage_404(self, fixture) -> bool:
        return fixture.stage not in self.KNOCKOUT_STAGES

    @pytest.fixture
    def r32_fixture_locked(self) -> Fixture:
        f = MagicMock(spec=Fixture)
        f.id = uuid.uuid4()
        f.stage = "round_of_32"
        f.status = MatchStatus.SCHEDULED
        f.is_locked.return_value = True
        return f

    @pytest.fixture
    def r32_fixture_open(self) -> Fixture:
        f = MagicMock(spec=Fixture)
        f.id = uuid.uuid4()
        f.stage = "round_of_32"
        f.status = MatchStatus.SCHEDULED
        f.is_locked.return_value = False
        return f

    @pytest.fixture
    def group_fixture(self) -> Fixture:
        f = MagicMock(spec=Fixture)
        f.id = uuid.uuid4()
        f.stage = "group"
        f.status = MatchStatus.SCHEDULED
        f.is_locked.return_value = True
        return f

    @pytest.fixture
    def third_place_fixture(self) -> Fixture:
        """Third-place playoff is unscored and must 404 — invariant."""
        f = MagicMock(spec=Fixture)
        f.id = uuid.uuid4()
        f.stage = "third_place"
        f.status = MatchStatus.SCHEDULED
        f.is_locked.return_value = True
        return f

    def test_pre_deadline_unlocked_is_blocked(self, r32_fixture_open):
        assert self._gate_403(r32_fixture_open, deadline_passed=False) is True

    def test_post_deadline_unlocked_is_visible(self, r32_fixture_open):
        # Once the global Phase-1 deadline passes, every KO fixture's
        # bundle becomes visible immediately (open-pool rule).
        assert self._gate_403(r32_fixture_open, deadline_passed=True) is False

    def test_pre_deadline_per_fixture_lock_unlocks(self, r32_fixture_locked):
        # Belt-and-braces fallback — if the deadline check fails for any
        # reason, the per-fixture 5-min lock still trips visibility.
        assert self._gate_403(r32_fixture_locked, deadline_passed=False) is False

    def test_group_stage_404(self, group_fixture):
        # ko-detail is knockout-only; group fixtures go to /community.
        assert self._stage_404(group_fixture) is True

    def test_third_place_404(self, third_place_fixture):
        # Invariant: third_place is unscored. Not in the KO whitelist.
        assert self._stage_404(third_place_fixture) is True

    def test_r32_passes_stage_gate(self, r32_fixture_locked):
        assert self._stage_404(r32_fixture_locked) is False
