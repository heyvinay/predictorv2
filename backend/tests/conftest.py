"""Pytest configuration and fixtures."""

import os
import pytest
from unittest.mock import patch

# Set test environment variables before importing app modules.
# DEBUG=true keeps the production-only JWT-secret strength validator
# (config.Settings._enforce_secret_strength) from rejecting the short test key.
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["DEBUG"] = "true"


@pytest.fixture
def mock_settings():
    """Mock application settings for testing."""
    with patch("app.config.get_settings") as mock:
        mock.return_value.database_url = "postgresql://test:test@localhost:5432/test"
        mock.return_value.jwt_secret_key = "test-secret-key"
        mock.return_value.jwt_algorithm = "HS256"
        mock.return_value.jwt_access_token_expire_minutes = 60
        mock.return_value.debug = True
        yield mock


@pytest.fixture
def mock_tournament_config():
    """Mock tournament configuration for testing."""
    config = {
        "tournament": {
            "name": "Test Tournament",
            "code": "TEST2026",
        },
        "format": {
            "total_teams": 48,
            "groups": 12,
        },
        "scoring": {
            "match": {
                "correct_outcome": 5,
                "exact_score": 10,
                "cap": 10,
            },
            "advancement": {
                "group_advance": 10,
                "group_position": 5,
                "round_of_32": 10,
                "round_of_16": 15,
                "quarter_final": 20,
                "semi_final": 40,
                "final": 60,
                "winner": 100,
            },
            "phase_multipliers": {
                "phase_1": 1.0,
                "phase_2": 0.7,
            },
        },
    }

    with patch("app.config.get_tournament_config") as mock:
        mock.return_value = config
        yield mock
