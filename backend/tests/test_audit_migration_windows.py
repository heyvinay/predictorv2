"""Regression tests for audit_top3_v2's known-migration-windows filter.

The filter exists so the top-entry auditor isn't alarmed by system-level
row updates (stage-rename migrations, batched normalisations) — only
genuine post-submission value changes are surfaced as "needs review".
If a NEW system migration ships without being registered in
``_KNOWN_MIGRATION_WINDOWS``, every audited entry will surface those rows
as unexplained tampering and waste auditor time.

These tests pin two things:

1. The exact list of currently-registered windows. If the list changes
   in ``audit_top3_v2.py``, the snapshot below must be updated to match.
   That forces an explicit decision when a new migration is added: you
   cannot silently extend the live filter without also updating this
   pin.

2. The filter's semantics — timestamps inside the tolerance match,
   timestamps outside do not, and an arbitrary tampering timestamp
   never matches.
"""

from datetime import datetime, timedelta, timezone

from scripts.audit_top3_v2 import (
    _KNOWN_MIGRATION_WINDOWS,
    _is_known_migration_modification,
)


# Snapshot of every registered window: (timestamp, tolerance_ms, reason).
# Update this list whenever you add or remove an entry in
# ``_KNOWN_MIGRATION_WINDOWS`` in ``backend/scripts/audit_top3_v2.py``.
_EXPECTED_WINDOWS: list[tuple[datetime, int, str]] = [
    (
        datetime(2026, 6, 10, 12, 43, 12, 727813, tzinfo=timezone.utc),
        5000,
        "v2.161.0 stage-rename migration (system-level)",
    ),
]


def test_registered_windows_match_snapshot() -> None:
    """Pin the registered windows so silent drift is caught at CI time.

    If this assertion fails, you added/removed/modified an entry in
    ``_KNOWN_MIGRATION_WINDOWS``. Confirm every recent migration that
    touched prediction rows is registered, then update
    ``_EXPECTED_WINDOWS`` above to match the new live list.
    """
    actual = [(w["ts"], w["tol_ms"], w["reason"]) for w in _KNOWN_MIGRATION_WINDOWS]
    assert actual == _EXPECTED_WINDOWS, (
        "Migration-window list drifted from the pinned snapshot. "
        "If you added a new system migration that touched prediction "
        "rows, register it in _KNOWN_MIGRATION_WINDOWS AND update "
        "_EXPECTED_WINDOWS in this test."
    )


def test_timestamp_at_window_center_is_known() -> None:
    for w in _KNOWN_MIGRATION_WINDOWS:
        assert _is_known_migration_modification(w["ts"]) is True, (
            f"Window {w['reason']!r} should match its own center timestamp"
        )


def test_timestamp_within_tolerance_is_known() -> None:
    """Tolerance is symmetric: ts ± tol_ms milliseconds both match."""
    for w in _KNOWN_MIGRATION_WINDOWS:
        tol = w["tol_ms"]
        inside_before = w["ts"] - timedelta(milliseconds=tol - 1)
        inside_after = w["ts"] + timedelta(milliseconds=tol - 1)
        assert _is_known_migration_modification(inside_before) is True
        assert _is_known_migration_modification(inside_after) is True


def test_timestamp_outside_tolerance_is_unknown() -> None:
    """A timestamp ~tolerance+1 ms outside any window must NOT match."""
    for w in _KNOWN_MIGRATION_WINDOWS:
        tol = w["tol_ms"]
        outside_before = w["ts"] - timedelta(milliseconds=tol + 1)
        outside_after = w["ts"] + timedelta(milliseconds=tol + 1)
        assert _is_known_migration_modification(outside_before) is False
        assert _is_known_migration_modification(outside_after) is False


def test_unrelated_timestamp_is_unknown() -> None:
    """An arbitrary 'tampering' timestamp far from every window must
    be flagged (i.e. NOT recognised as a known migration)."""
    arbitrary = datetime(2026, 6, 25, 14, 32, 0, tzinfo=timezone.utc)
    assert _is_known_migration_modification(arbitrary) is False
