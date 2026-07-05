"""Stage-name normalization (v2.161.0).

Canonical TeamPrediction.stage values are SINGULAR ("quarter_final",
"semi_final"). The frontend historically wrote plural; these tests pin:

1. The write path (`replace_bracket_predictions`) normalizes plural
   payloads and de-dupes rows that collapse to the same key.
2. Advancement scoring pays QF/SF picks and buckets them into
   `quarter_final_points` / `semi_final_points`.
3. `_organize_bracket` maps singular stored values to the plural
   BracketPrediction response fields (and tolerates legacy plural rows).
4. Submit validation accepts an all-singular bracket and flags missing
   QF picks.

Uses in-memory SQLite per the project convention.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import app.models  # noqa: F401  — registers all models
from app.api.entry_predictions import _organize_bracket
from app.models.competition import Competition
from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import (
    PredictionPhase,
    TeamPrediction,
    normalize_stage,
)
from app.models.score import Score, ScoreSource
from app.models.user import AuthProvider, User
from app.services.entries import EntryValidationError, _validate_phase1_complete
from app.services.predictions import replace_bracket_predictions
from app.services.scoring import calculate_entry_points


@pytest.fixture(autouse=True)
def _fixed_scoring_config():
    config = {
        "mode": "fixed",
        "match": {"correct_outcome": 5, "exact_score": 10, "hybrid_cap": 10},
        "advancement": {
            "group_advance": 10,
            "group_position": 5,
            "round_of_32": 20,
            "round_of_16": 30,
            "quarter_final": 40,
            "semi_final": 50,
            "final": 75,
            "winner": 100,
        },
        "phase_multipliers": {"phase_1": 1.0, "phase_2": 0.7},
    }
    with patch("app.services.scoring.get_scoring_config", return_value=config):
        yield


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(
        name="Test WC 2026",
        external_id="WC",
        is_active=True,
        # Deadline far in the future so the write path stays open.
        phase1_deadline=datetime(2099, 1, 1, tzinfo=timezone.utc),
        # calculate_entry_points gates advancement scoring on this flag;
        # tests need it True or every KO bucket comes back as 0.
        knockout_scoring_enabled=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def alice(session: AsyncSession) -> User:
    u = User(
        email="alice@example.com",
        name="Alice",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _make_entry(
    session: AsyncSession,
    *,
    user: User,
    competition: Competition,
    status: EntryStatus = EntryStatus.DRAFT,
) -> PredictionEntry:
    entry = PredictionEntry(
        competition_id=competition.id,
        user_id=user.id,
        reference=f"WC26-{uuid.uuid4().hex[:6].upper()}",
        display_name="Entry 1",
        entry_number=1,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    for phase in (PredictionPhase.PHASE_1, PredictionPhase.PHASE_2):
        session.add(
            PredictionEntryPhase(entry_id=entry.id, phase=phase, status=status)
        )
    await session.commit()
    # Eager-load phases — _validate_writeable accesses entry.phases and a
    # lazy load would raise MissingGreenlet under the async driver.
    await session.refresh(entry, attribute_names=["phases"])
    return entry


# ---------------------------------------------------------------------------
# 0. The helper itself
# ---------------------------------------------------------------------------
class TestNormalizeStage:
    def test_plural_maps_to_singular(self):
        assert normalize_stage("quarter_finals") == "quarter_final"
        assert normalize_stage("semi_finals") == "semi_final"

    def test_canonical_values_pass_through(self):
        for stage in (
            "group", "round_of_32", "round_of_16",
            "quarter_final", "semi_final", "final", "winner",
        ):
            assert normalize_stage(stage) == stage


# ---------------------------------------------------------------------------
# 1. Write path normalizes + de-dupes
# ---------------------------------------------------------------------------
class TestWritePathNormalization:
    async def test_plural_payload_stored_singular_and_deduped(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        """A stale-bundle payload carrying BOTH spellings for the same team
        stores ONE singular row — no unique-constraint violation."""
        entry = await _make_entry(session, user=alice, competition=competition)
        picks = [
            {"team": "Brazil", "stage": "quarter_finals", "group_position": None},
            {"team": "Brazil", "stage": "quarter_final", "group_position": None},
            {"team": "France", "stage": "semi_finals", "group_position": None},
            {"team": "Spain", "stage": "round_of_16", "group_position": None},
        ]
        rows = await replace_bracket_predictions(
            session,
            entry=entry,
            user=alice,
            competition=competition,
            picks=picks,
        )
        await session.commit()

        stored = {(r.team, r.stage) for r in rows}
        assert stored == {
            ("Brazil", "quarter_final"),
            ("France", "semi_final"),
            ("Spain", "round_of_16"),
        }

        db_rows = (
            (
                await session.execute(
                    select(TeamPrediction).where(
                        TeamPrediction.entry_id == entry.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(db_rows) == 3
        assert all("finals" not in r.stage for r in db_rows)


# ---------------------------------------------------------------------------
# 2. QF/SF picks pay and bucket correctly
# ---------------------------------------------------------------------------
class TestAdvancementPayout:
    async def test_qf_sf_picks_pay_into_their_buckets(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        """Champion chain: Brazil wins a FINISHED final → reaches `winner`,
        so singular QF/SF picks pay 40/50 into the right buckets. (This is
        the exact path the plural bug silently zeroed.)"""
        entry = await _make_entry(
            session, user=alice, competition=competition,
            status=EntryStatus.SUBMITTED,
        )
        # Advancement is LINEUP-BASED (CLAUDE.md invariant, v2.161.0):
        # "reached stage X" credit fires when a team is seeded into a
        # stage-X fixture. So we need Brazil seeded into QF + SF + Final
        # fixtures — not just the Final — for the QF/SF picks to earn credit.
        # The Final also needs FINISHED + scored for the `winner` credit
        # this test's docstring names as the champion-chain contract.
        for stage_name, kickoff in (
            ("quarter_final", datetime(2026, 7, 9, 19, 0, tzinfo=timezone.utc)),
            ("semi_final", datetime(2026, 7, 14, 19, 0, tzinfo=timezone.utc)),
        ):
            session.add(Fixture(
                competition_id=competition.id,
                home_team="Brazil",
                away_team="TBD",
                kickoff=kickoff,
                stage=stage_name,
                group=None,
                status=MatchStatus.SCHEDULED,
            ))
        final = Fixture(
            competition_id=competition.id,
            home_team="Brazil",
            away_team="France",
            kickoff=datetime(2026, 7, 19, 19, 0, tzinfo=timezone.utc),
            stage="final",
            group=None,
            status=MatchStatus.FINISHED,
        )
        session.add(final)
        await session.commit()
        await session.refresh(final)
        session.add(
            Score(
                fixture_id=final.id,
                home_score=2,
                away_score=1,
                outcome="1",
                source=ScoreSource.MANUAL,
                verified=True,
            )
        )
        for stage in ("quarter_final", "semi_final"):
            session.add(
                TeamPrediction(
                    entry_id=entry.id,
                    team="Brazil",
                    stage=stage,
                    phase=PredictionPhase.PHASE_1,
                )
            )
        await session.commit()

        breakdown = await calculate_entry_points(session, entry.id)
        assert breakdown.phase1.quarter_final_points == 40
        assert breakdown.phase1.semi_final_points == 50
        assert breakdown.total == 90


# ---------------------------------------------------------------------------
# 3. _organize_bracket: singular rows → plural response fields
# ---------------------------------------------------------------------------
class TestOrganizeBracket:
    def _row(self, team: str, stage: str) -> TeamPrediction:
        return TeamPrediction(
            entry_id=uuid.uuid4(),
            team=team,
            stage=stage,
            phase=PredictionPhase.PHASE_1,
        )

    def test_singular_rows_populate_plural_fields(self):
        rows = [
            self._row("Brazil", "quarter_final"),
            self._row("France", "semi_final"),
            self._row("Spain", "round_of_16"),
            self._row("Brazil", "final"),
            self._row("Brazil", "winner"),
        ]
        bracket = _organize_bracket(rows)
        assert bracket.quarter_finals == ["Brazil"]
        assert bracket.semi_finals == ["France"]
        assert bracket.round_of_16 == ["Spain"]
        assert bracket.final == ["Brazil"]
        assert bracket.winner == "Brazil"

    def test_legacy_plural_rows_still_map(self):
        """Read-side defense: any plural row that survives the migration
        still lands in the right response field."""
        rows = [
            self._row("Brazil", "quarter_finals"),
            self._row("France", "semi_finals"),
        ]
        bracket = _organize_bracket(rows)
        assert bracket.quarter_finals == ["Brazil"]
        assert bracket.semi_finals == ["France"]


# ---------------------------------------------------------------------------
# 4. Submit validation speaks singular
# ---------------------------------------------------------------------------
class TestSubmitValidation:
    async def _bracket_rows(
        self, session: AsyncSession, entry: PredictionEntry, *, drop_qf: bool
    ) -> None:
        """A chain-intact bracket: 16 R16 teams → 8 QF → 4 SF → 2 final
        → 1 winner, all singular. Optionally omit the QF rows."""
        teams = [f"Team{i:02d}" for i in range(16)]
        plan: list[tuple[str, list[str]]] = [
            ("round_of_16", teams),
            ("quarter_final", teams[:8]),
            ("semi_final", teams[:4]),
            ("final", teams[:2]),
            ("winner", teams[:1]),
        ]
        for stage, stage_teams in plan:
            if drop_qf and stage == "quarter_final":
                continue
            for team in stage_teams:
                session.add(
                    TeamPrediction(
                        entry_id=entry.id,
                        team=team,
                        stage=stage,
                        phase=PredictionPhase.PHASE_1,
                    )
                )
        await session.commit()

    async def test_complete_singular_bracket_passes(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        entry = await _make_entry(session, user=alice, competition=competition)
        await self._bracket_rows(session, entry, drop_qf=False)
        # No group fixtures and no bonus questions exist in this DB, so a
        # complete bracket should validate cleanly.
        with patch(
            "app.services.bonus.get_questions", return_value=[]
        ):
            await _validate_phase1_complete(session, entry=entry)

    async def test_missing_qf_flagged_with_singular_name(
        self, session: AsyncSession, alice: User, competition: Competition
    ):
        entry = await _make_entry(session, user=alice, competition=competition)
        await self._bracket_rows(session, entry, drop_qf=True)
        with patch(
            "app.services.bonus.get_questions", return_value=[]
        ):
            with pytest.raises(EntryValidationError) as exc:
                await _validate_phase1_complete(session, entry=entry)
        msg = str(exc.value)
        assert "quarter final" in msg
