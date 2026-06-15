"""Tests for the production JWT-secret strength validator (config.Settings).

The signing key is the entire trust anchor for auth, the blind pool, scoring,
and admin ops. In production (DEBUG=false) the app must refuse to boot with a
weak, short, or known-default key rather than start silently forgeable.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings

_STRONG = "x" * 48  # >= 32 chars, not a known placeholder
_DB = "postgresql://test:test@localhost:5432/test"


def _make(**overrides) -> Settings:
    base = dict(database_url=_DB, jwt_secret_key=_STRONG, debug=False)
    base.update(overrides)
    return Settings(**base)


def test_strong_secret_accepted_in_production():
    s = _make(jwt_secret_key=_STRONG, debug=False)
    assert s.jwt_secret_key == _STRONG


@pytest.mark.parametrize(
    "weak",
    [
        "super-secret-dev-key-change-in-prod",
        "your-super-secret-key-change-in-production",
        "changeme",
        "secret",
        "test-secret-key",
        "short",  # under 32 chars
        "",  # unset
    ],
)
def test_weak_secret_rejected_in_production(weak):
    with pytest.raises(ValidationError):
        _make(jwt_secret_key=weak, debug=False)


def test_weak_secret_allowed_in_debug():
    # Local dev/test ergonomics: the validator is production-only.
    s = _make(jwt_secret_key="test-secret-key", debug=True)
    assert s.jwt_secret_key == "test-secret-key"
