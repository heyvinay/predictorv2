"""Cross-language parity for match-points scoring.

Backend half of a two-language guarantee: the SAME golden cases in
`shared/scoring-parity-cases.json` are also run by the frontend Vitest suite
(`frontend/src/lib/utils/matchBreakdown.parity.test.ts`). Both `compute_match_points`
(Python) and `computeMatchPoints` (TypeScript) must return identical
points/correct_outcome/exact_score for every case, so the Results-card
projection can never drift from the points the backend actually awards.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.scoring import compute_match_points


def _find_file(relative: str) -> Path | None:
    cur = Path(__file__).resolve()
    for parent in [cur.parent, *cur.parents]:
        candidate = parent / relative
        if candidate.exists():
            return candidate
    return None


_CASES_FILE = _find_file("shared/scoring-parity-cases.json")


def _load_cases() -> list[dict]:
    assert _CASES_FILE is not None, (
        "shared/scoring-parity-cases.json not found via parent-walk. In the "
        "backend container it must be mounted (docker-compose.yml: "
        "'./shared:/app/shared:ro')."
    )
    return json.loads(_CASES_FILE.read_text())["cases"]


def test_scoring_parity_file_is_available() -> None:
    """Guard: the golden fixture must be present/mounted, else parity is untested."""
    assert _CASES_FILE is not None and _CASES_FILE.exists(), (
        "shared/scoring-parity-cases.json missing — restore it or remount the "
        "./shared volume. Without it the frontend/backend scoring implementations "
        "are no longer pinned to agree."
    )


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_scoring_parity(case: dict) -> None:
    points, correct_outcome, exact_score = compute_match_points(
        mode=case["mode"],
        predicted_home=case["predicted_home"],
        predicted_away=case["predicted_away"],
        actual_home=case["actual_home"],
        actual_away=case["actual_away"],
        total_predictors=case["total_predictors"],
        correct_predictors=case["correct_predictors"],
        outcome_points=case["outcome_points"],
        exact_points=case["exact_points"],
        cap=case["cap"],
    )
    assert points == case["expected_points"], (
        f"[{case['name']}] points: expected {case['expected_points']}, got {points}"
    )
    assert correct_outcome == case["expected_correct_outcome"], (
        f"[{case['name']}] correct_outcome mismatch"
    )
    assert exact_score == case["expected_exact_score"], (
        f"[{case['name']}] exact_score mismatch"
    )
