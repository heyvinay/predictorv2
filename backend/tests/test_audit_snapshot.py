"""Regression tests for audit_top3_v2's step-4 frozen-snapshot path.

Three layers of protection:

1. **Constants pin** — ``_SNAPSHOT_PATH`` / ``_SNAPSHOT_LABEL`` cannot
   change without an explicit code edit that also bumps this test.

2. **Hash pin** — the committed CSV's SHA-256 must match the value
   recorded in ``backend/snapshots/MANIFEST.md``. If anyone modifies
   the committed file after capture, this fires — the snapshot is
   meant to be immutable, full stop.

3. **Function behaviour** — synthetic in-tmp CSVs via monkeypatch
   cover the missing-file, empty-file, ref-found-in-identity-row,
   ref-found-via-fallback-scan, and ref-not-found cases.
"""

import hashlib
from pathlib import Path

import pytest

from scripts.audit_top3_v2 import (
    _SNAPSHOT_LABEL,
    _SNAPSHOT_PATH,
    _fetch_sheet_predictions_for_entry,
)


# ─────────────────────────────────────────────────────────────────────
# Constants pin
# ─────────────────────────────────────────────────────────────────────

def test_snapshot_constants_match_manifest() -> None:
    """If you capture a NEW snapshot (e.g. before the final), bump
    these to the new file and add a new MANIFEST.md entry — never
    edit an existing committed snapshot."""
    assert _SNAPSHOT_LABEL == "2026-06-28"
    assert _SNAPSHOT_PATH == Path(
        "/app/snapshots/predictions-snapshot-2026-06-28.csv"
    )


# ─────────────────────────────────────────────────────────────────────
# Hash pin (immutability via test)
# ─────────────────────────────────────────────────────────────────────

_EXPECTED_SHA256 = (
    "58623d46ba0c30c3e233394064a7f9129839901248e33045fcbeddf90c93b518"
)


def test_committed_snapshot_hash_matches_manifest() -> None:
    """The committed CSV's SHA-256 must match MANIFEST.md. If this
    fails, either the file was modified after capture (a contract
    violation — the snapshot is meant to be immutable) or this hash
    pin is wrong. The fix is almost always 'revert the file change',
    not 'update the hash here'."""
    if not _SNAPSHOT_PATH.exists():
        pytest.skip(
            f"Snapshot {_SNAPSHOT_PATH} not present in container — "
            f"either the file hasn't been deployed yet or the "
            f"./backend/snapshots volume mount is missing in "
            f"docker-compose.yml."
        )
    actual = hashlib.sha256(_SNAPSHOT_PATH.read_bytes()).hexdigest()
    assert actual == _EXPECTED_SHA256, (
        f"Snapshot file SHA-256 has changed.\n"
        f"  expected (per MANIFEST.md): {_EXPECTED_SHA256}\n"
        f"  actual:                     {actual}\n"
        f"The audit's frozen-reference contract relies on this file "
        f"being immutable. Restore from git, OR if you intentionally "
        f"need a newer reference point, capture a NEW dated snapshot "
        f"alongside the old one — do not edit the existing file."
    )


# ─────────────────────────────────────────────────────────────────────
# Function behaviour (synthetic CSV via monkeypatch)
# ─────────────────────────────────────────────────────────────────────

def _write_synthetic_csv(tmp_path: Path, content: list[list[str]]) -> Path:
    import csv
    p = tmp_path / "snapshot.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(content)
    return p


def test_returns_unavailable_when_snapshot_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "scripts.audit_top3_v2._SNAPSHOT_PATH",
        tmp_path / "does-not-exist.csv",
    )
    result = _fetch_sheet_predictions_for_entry("WC26-000085")
    assert result["available"] is False
    assert "not found" in result["reason"].lower()


def test_returns_unavailable_when_snapshot_empty(monkeypatch, tmp_path) -> None:
    p = _write_synthetic_csv(tmp_path, [])
    monkeypatch.setattr("scripts.audit_top3_v2._SNAPSHOT_PATH", p)
    result = _fetch_sheet_predictions_for_entry("WC26-000085")
    assert result["available"] is False
    assert "empty" in result["reason"].lower()


def test_picks_column_when_reference_found_in_identity_rows(
    monkeypatch, tmp_path
) -> None:
    p = _write_synthetic_csv(
        tmp_path,
        [
            ["", "WC26-000085", "WC26-000104", "WC26-000083"],  # identity row
            ["Mexico vs S. Korea", "2-1", "1-1", "0-2"],
            ["Brazil vs Senegal", "3-0", "2-2", "1-1"],
        ],
    )
    monkeypatch.setattr("scripts.audit_top3_v2._SNAPSHOT_PATH", p)
    result = _fetch_sheet_predictions_for_entry("WC26-000104")
    assert result["available"] is True
    assert result["target_col"] == 2
    assert result["picks_column"] == ["WC26-000104", "1-1", "2-2"]
    assert result["row_labels"] == [
        "",
        "Mexico vs S. Korea",
        "Brazil vs Senegal",
    ]
    assert result["snapshot_label"] == _SNAPSHOT_LABEL
    assert result["snapshot_kind"].startswith("frozen:")


def test_picks_column_when_reference_in_late_row(monkeypatch, tmp_path) -> None:
    """The function scans rows 0-13 first for speed; refs in later
    rows trigger the full-scan fallback."""
    rows = [["padding"] * 5 for _ in range(20)]
    rows[18][3] = "WC26-000083"
    rows.append(["after-ref-row"] + ["x"] * 4)
    p = _write_synthetic_csv(tmp_path, rows)
    monkeypatch.setattr("scripts.audit_top3_v2._SNAPSHOT_PATH", p)
    result = _fetch_sheet_predictions_for_entry("WC26-000083")
    assert result["available"] is True
    assert result["target_col"] == 3
    assert result["picks_column"][18] == "WC26-000083"


def test_unavailable_when_reference_not_found(monkeypatch, tmp_path) -> None:
    p = _write_synthetic_csv(
        tmp_path,
        [
            ["", "WC26-000001", "WC26-000002"],
            ["row1", "a", "b"],
        ],
    )
    monkeypatch.setattr("scripts.audit_top3_v2._SNAPSHOT_PATH", p)
    result = _fetch_sheet_predictions_for_entry("WC26-999999")
    assert result["available"] is False
    assert "not found" in result["reason"].lower()
