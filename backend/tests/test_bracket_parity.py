"""Bracket parity — backend bracket_seeding.py ↔ frontend
bracketConfig.ts via the shared snapshot (v2.184.x).

The two files encode the same FIFA 2026 World Cup knockout structure.
They're maintained by hand (the TS file is the user-facing definition
the entry wizard renders; the Python file mirrors it for backend
resolvers). Without this test, editing one without the other silently
diverges them and bugs surface only when the resolver places a team
into the wrong slot — visible in production but not in CI.

Mechanism: the frontend's bracketConfig.ts is parsed by
`backend/scripts/regen_bracket_parity_snapshot.py` into
`shared/bracket-sources-snapshot.json`. The shared directory is mounted
read-only into both the backend container (at /app/shared) and the
frontend-dev container; the same JSON is also committed to git so CI
runs the parity check against a known-good record. This test then
compares that snapshot against the Python source maps in
`app.services.bracket_seeding`.

Drift catches:
  * Edit Python without TS → backend != snapshot → test fails.
  * Edit TS without regenerating snapshot → snapshot stale →
    discrepancy with TS is masked, but you'd also see it in dev.
  * Edit both TS and Python in sync, but forget to regenerate
    snapshot → test fails because snapshot != Python.

If you touched bracketConfig.ts, regenerate via:
  python backend/scripts/regen_bracket_parity_snapshot.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.bracket_seeding import (
    FINAL_SOURCES,
    QUARTER_FINAL_SOURCES,
    R32_SOURCES,
    ROUND_OF_16_SOURCES,
    SEMI_FINAL_SOURCES,
)


def _find_snapshot() -> Path:
    """Locate shared/bracket-sources-snapshot.json.

    Inside the docker test container that's /app/shared/...; outside
    docker (rare for these tests, but supported) walk up from this
    file to find a `shared/` sibling.
    """
    candidates = [
        Path("/app/shared/bracket-sources-snapshot.json"),
    ]
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidates.append(ancestor / "shared" / "bracket-sources-snapshot.json")
        if (ancestor / "frontend").is_dir():
            break
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        "Couldn't locate shared/bracket-sources-snapshot.json. If this is "
        "the first run after pulling a fresh branch, regenerate via\n"
        "  python backend/scripts/regen_bracket_parity_snapshot.py"
    )


@pytest.fixture(scope="module")
def snapshot() -> dict[int, tuple[dict[str, Any], dict[str, Any]]]:
    """Parsed snapshot, keyed by integer match number."""
    raw = json.loads(_find_snapshot().read_text(encoding="utf-8"))
    sources = raw.get("sources", {})
    return {int(k): (v["home"], v["away"]) for k, v in sources.items()}


# ── Sanity ─────────────────────────────────────────────────────────


def test_snapshot_has_full_bracket(snapshot):
    """All 64 knockout matches present (M73-M104) — verifies the
    regen script captured the complete frontend definition."""
    expected = set(range(73, 89)) | set(range(89, 97)) | set(range(97, 101)) | {101, 102, 103, 104}
    got = set(snapshot.keys())
    missing = expected - got
    extra = got - expected
    assert not missing and not extra, f"missing={missing!r}, extra={extra!r}"


# ── Stage-by-stage parity ──────────────────────────────────────────


def _assert_parity(
    stage_label: str,
    backend_map: dict[int, tuple[dict[str, Any], dict[str, Any]]],
    snapshot_map: dict[int, tuple[dict[str, Any], dict[str, Any]]],
    expected_range: range,
) -> None:
    expected = set(expected_range)
    backend_nums = set(backend_map.keys())
    snap_subset = {n: snapshot_map[n] for n in snapshot_map if n in expected}

    assert backend_nums == expected, (
        f"{stage_label}: backend map missing/extra match numbers — "
        f"expected {sorted(expected)}, got {sorted(backend_nums)}"
    )
    assert set(snap_subset.keys()) == expected, (
        f"{stage_label}: snapshot missing/extra — expected {sorted(expected)}, "
        f"got {sorted(snap_subset.keys())}"
    )

    for num in sorted(expected):
        be_home, be_away = backend_map[num]
        snap_home, snap_away = snap_subset[num]
        assert be_home == snap_home, (
            f"{stage_label} M{num} HOME diverges:\n"
            f"  backend bracket_seeding: {be_home}\n"
            f"  frontend snapshot:      {snap_home}\n"
            f"If you just edited bracketConfig.ts, regenerate the snapshot via\n"
            f"  python backend/scripts/regen_bracket_parity_snapshot.py"
        )
        assert be_away == snap_away, (
            f"{stage_label} M{num} AWAY diverges:\n"
            f"  backend bracket_seeding: {be_away}\n"
            f"  frontend snapshot:      {snap_away}"
        )


def test_r32_sources_parity(snapshot):
    _assert_parity("R32", R32_SOURCES, snapshot, range(73, 89))


def test_round_of_16_sources_parity(snapshot):
    _assert_parity("R16", ROUND_OF_16_SOURCES, snapshot, range(89, 97))


def test_quarter_final_sources_parity(snapshot):
    _assert_parity("QF", QUARTER_FINAL_SOURCES, snapshot, range(97, 101))


def test_semi_final_sources_parity(snapshot):
    _assert_parity("SF", SEMI_FINAL_SOURCES, snapshot, range(101, 103))


def test_final_sources_parity(snapshot):
    _assert_parity("Final", FINAL_SOURCES, snapshot, range(104, 105))


# ── third_place asymmetry ──────────────────────────────────────────


def test_third_place_in_snapshot_but_not_backend(snapshot):
    """M103 (bronze-medal playoff) is part of FIFA's wallchart so the
    frontend renders it in the entry wizard, but the prediction game
    doesn't score it (CLAUDE.md invariant — third_place is unscored).
    Backend bracket_seeding therefore omits M103. Verify both halves
    of that intentional asymmetry hold.
    """
    assert 103 in snapshot, "Frontend should keep M103 in bracketConfig.ts for wallchart fidelity"
    home_src, away_src = snapshot[103]
    assert home_src["type"] == "loser" and away_src["type"] == "loser"
    assert {home_src["match_number"], away_src["match_number"]} == {101, 102}

    all_backend = (
        list(R32_SOURCES.keys())
        + list(ROUND_OF_16_SOURCES.keys())
        + list(QUARTER_FINAL_SOURCES.keys())
        + list(SEMI_FINAL_SOURCES.keys())
        + list(FINAL_SOURCES.keys())
    )
    assert 103 not in all_backend, (
        "Backend bracket_seeding includes M103 — but third_place is an "
        "UNSCORED stage per the CLAUDE.md invariant and must stay omitted."
    )
