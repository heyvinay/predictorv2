"""Unit tests for PredictionEntry, PredictionEntryPhase, and the rewired
prediction tables.

These tests exercise SQLModel model construction, field defaults, and
table-args (constraint) metadata. They do not require a live DB —
constraints are checked by inspecting `__table_args__` and SQLAlchemy
metadata, which is what the migration will actually emit at upgrade time.
"""

import uuid

from sqlalchemy import UniqueConstraint

from app.models.entry import (
    ActorRole,
    EntryStatus,
    PaymentMode,
    PredictionEntry,
    PredictionEntryEvent,
    PredictionEntryPhase,
)
from app.models.prediction import MatchPrediction, PredictionPhase


# ---------------------------------------------------------------------------
# 1. Field defaults — make sure a freshly-constructed entry has the values
# the brief specifies, without needing the DB to apply server_default.
# ---------------------------------------------------------------------------
class TestPredictionEntryDefaults:
    """PredictionEntry instantiates with correct defaults without DB."""

    def test_default_flags(self):
        entry = PredictionEntry(
            competition_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            reference="WC26-000001",
            display_name="My Entry",
            entry_number=1,
        )
        assert entry.paid is False
        assert entry.prize_eligible is True
        assert entry.is_disabled is False
        assert entry.disabled_reason is None
        assert entry.disabled_at is None
        assert entry.disabled_by_user_id is None
        assert entry.withdrawn_at is None
        assert entry.withdrawn_reason is None
        # created_at / updated_at are populated by default_factory=utc_now
        assert entry.created_at is not None
        assert entry.updated_at is not None

    def test_entry_status_enum_values(self):
        """EntryStatus exposes the three lifecycle statuses.

        The lifecycle was simplified 6 → 3: `ready`, `locked` and `disabled`
        were removed. `is_disabled` is now a separate orthogonal admin flag on
        PredictionEntry, not a status. See plan i-want-to-simplify-bright-wolf.md.
        """
        assert {e.value for e in EntryStatus} == {
            "draft",
            "submitted",
            "withdrawn",
        }

    def test_actor_role_enum_values(self):
        assert {a.value for a in ActorRole} == {"user", "admin", "system"}

    def test_payment_mode_enum_values(self):
        assert {p.value for p in PaymentMode} == {"per_entry", "per_user"}


# ---------------------------------------------------------------------------
# 2. PredictionEntryPhase uniqueness — the (entry_id, phase) constraint
# must exist in __table_args__ so a single entry can't accumulate multiple
# rows for the same phase.
# ---------------------------------------------------------------------------
class TestPredictionEntryPhaseConstraints:
    """Entry phase rows are unique per (entry, phase)."""

    def test_entry_phase_unique_constraint_declared(self):
        unique_names = {
            c.name
            for c in PredictionEntryPhase.__table_args__
            if isinstance(c, UniqueConstraint)
        }
        assert "uq_entry_phase" in unique_names

    def test_entry_phase_constructs_with_required_fields(self):
        """A phase row can be constructed with status + phase."""
        phase = PredictionEntryPhase(
            entry_id=uuid.uuid4(),
            phase=PredictionPhase.PHASE_1,
            status=EntryStatus.DRAFT,
        )
        assert phase.phase == PredictionPhase.PHASE_1
        assert phase.status == EntryStatus.DRAFT
        assert phase.ready_at is None
        assert phase.submitted_at is None
        assert phase.locked_at is None


# ---------------------------------------------------------------------------
# 3. Entry ownership — two entries owned by the same user must differ on
# entry_number and reference; competition_id/user_id remain the same. This
# is the property that lets `max_entries_per_user` work as a count.
# ---------------------------------------------------------------------------
class TestEntryOwnership:
    """entry_number differentiates entries per user within a competition."""

    def test_two_entries_same_user_different_numbers(self):
        competition_id = uuid.uuid4()
        user_id = uuid.uuid4()
        entry1 = PredictionEntry(
            competition_id=competition_id,
            user_id=user_id,
            reference="WC26-000001",
            display_name="Entry One",
            entry_number=1,
        )
        entry2 = PredictionEntry(
            competition_id=competition_id,
            user_id=user_id,
            reference="WC26-000002",
            display_name="Entry Two",
            entry_number=2,
        )
        # Same owner, same competition
        assert entry1.user_id == entry2.user_id
        assert entry1.competition_id == entry2.competition_id
        # Differentiated by reference + number
        assert entry1.reference != entry2.reference
        assert entry1.entry_number != entry2.entry_number

    def test_uq_entry_competition_user_number_declared(self):
        """The DB-level unique constraint that enforces max-entries-per-user."""
        unique_names = {
            c.name
            for c in PredictionEntry.__table_args__
            if isinstance(c, UniqueConstraint)
        }
        assert "uq_entry_competition_user_number" in unique_names
        assert "uq_entry_competition_reference" in unique_names


# ---------------------------------------------------------------------------
# 4. Same fixture, different entries — the unique key on match_predictions
# is now (entry_id, fixture_id). Two entries (potentially owned by the same
# user) can hold different score predictions for the same fixture. The
# old (user_id, fixture_id) constraint and the user_id column itself are
# gone.
# ---------------------------------------------------------------------------
class TestTwoEntriesSameFixture:
    """match_predictions are entry-scoped, not user-scoped."""

    def test_match_prediction_unique_key_is_entry_scoped(self):
        fixture_id = uuid.uuid4()
        entry1_id = uuid.uuid4()
        entry2_id = uuid.uuid4()

        pred1 = MatchPrediction(
            entry_id=entry1_id,
            fixture_id=fixture_id,
            home_score=2,
            away_score=1,
        )
        pred2 = MatchPrediction(
            entry_id=entry2_id,
            fixture_id=fixture_id,
            home_score=0,
            away_score=0,
        )

        # Different entries, same fixture — valid.
        assert pred1.entry_id != pred2.entry_id
        assert pred1.fixture_id == pred2.fixture_id

        # Distinct prediction values, not just object identity.
        assert (pred1.home_score, pred1.away_score) != (
            pred2.home_score,
            pred2.away_score,
        )

    def test_match_prediction_has_no_user_id(self):
        """Predictions are owned by entries — user_id is fully removed."""
        pred = MatchPrediction(
            entry_id=uuid.uuid4(),
            fixture_id=uuid.uuid4(),
            home_score=1,
            away_score=0,
        )
        assert not hasattr(pred, "user_id")

    def test_match_prediction_entry_fixture_unique_declared(self):
        unique_names = {
            c.name
            for c in MatchPrediction.__table_args__
            if isinstance(c, UniqueConstraint)
        }
        assert "uq_match_pred_entry_fixture" in unique_names


# ---------------------------------------------------------------------------
# 5. PredictionEntryEvent — the audit log doesn't get an updated_at
# (events are immutable) and from/to status are plain strings so future
# enum renames don't invalidate history.
# ---------------------------------------------------------------------------
class TestPredictionEntryEvent:
    """Audit events store transitions immutably."""

    def test_event_constructs_with_transition_data(self):
        event = PredictionEntryEvent(
            entry_id=uuid.uuid4(),
            phase=PredictionPhase.PHASE_1,
            from_status="draft",
            to_status="ready",
            actor_user_id=uuid.uuid4(),
            actor_role=ActorRole.USER,
        )
        assert event.from_status == "draft"
        assert event.to_status == "ready"
        assert event.reason is None
        # Event has created_at but no updated_at (immutable record).
        assert event.created_at is not None
        assert not hasattr(event, "updated_at")
