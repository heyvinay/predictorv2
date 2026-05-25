"""SQLModel database models."""

from app.models.audit import AuditEvent
from app.models.bonus import BonusAnswer, BonusPrediction
from app.models.competition import Competition
from app.models.entry import (
    ActorRole,
    EntryStatus,
    PaymentMode,
    PredictionEntry,
    PredictionEntryEvent,
    PredictionEntryPhase,
)
from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.magic_link_token import MagicLinkToken
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import AuthProvider, User

__all__ = [
    "User",
    "ActorRole",
    "AuditEvent",
    "AuthProvider",
    "BonusAnswer",
    "BonusPrediction",
    "Competition",
    "EntryStatus",
    "Fixture",
    "MatchStatus",
    "LeaderboardSnapshot",
    "MagicLinkToken",
    "MatchPrediction",
    "PaymentMode",
    "PredictionEntry",
    "PredictionEntryEvent",
    "PredictionEntryPhase",
    "TeamPrediction",
    "PredictionPhase",
    "Score",
]
