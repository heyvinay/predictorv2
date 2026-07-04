"""Pinned cross-reference: Football-Data ext_id ↔ FIFA match number (v2.183.1).

Earlier code ASSUMED `ext_id - 537342 = FIFA match number` for the R32
fixtures. Football-Data's ext_ids do NOT correspond linearly to FIFA
match numbers, so every R32 fixture displayed under the wrong kickoff
for 2.181.1 → 2.183.0.

These tests pin the kickoff-validated mapping. If Football-Data
re-issues ext_ids (rare but possible) OR if FIFA reschedules a match
in a way that changes the ordering of ext_ids by kickoff, this test
catches it BEFORE wrong team names reach production.

Source of truth:
  - Wikipedia 2026 FWC Round of 32 page (kickoff times + FIFA match
    numbers): https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_round_of_32
  - Production DB kickoff field (Football-Data ingested) as of
    2026-06-28: used to derive the ext_id ↔ kickoff side of the pair.
"""

from __future__ import annotations

from app.services.bracket_seeding import EXT_ID_TO_MATCH_NUMBER, R32_SOURCES


# Kickoff cross-reference pinned against Wikipedia. Format:
#   ext_id  →  (FIFA match number, kickoff ISO-UTC, expected matchup label)
# Labels carry the bracket-seeding pair so a reviewer can sanity-check
# without leaving this file.
PINNED: dict[str, tuple[int, str, str]] = {
    "537417": (73, "2026-06-28T19:00:00+00:00", "2A vs 2B"),   # SA vs Canada
    "537423": (76, "2026-06-29T17:00:00+00:00", "1C vs 2F"),   # Brazil vs Japan
    "537415": (74, "2026-06-29T20:30:00+00:00", "1E vs 3rd"),  # Germany vs Paraguay
    "537418": (75, "2026-06-30T01:00:00+00:00", "1F vs 2C"),   # Netherlands vs Morocco
    "537424": (78, "2026-06-30T17:00:00+00:00", "2E vs 2I"),   # Ivory Coast vs Norway
    "537416": (77, "2026-06-30T21:00:00+00:00", "1I vs 3rd"),  # France vs Sweden
    "537425": (79, "2026-07-01T01:00:00+00:00", "1A vs 3rd"),  # Mexico vs Ecuador
    "537426": (80, "2026-07-01T16:00:00+00:00", "1L vs 3rd"),  # England vs 3rd[I/K]
    "537422": (82, "2026-07-01T20:00:00+00:00", "1G vs 3rd"),  # Belgium vs 3rd[A/I/J]
    "537421": (81, "2026-07-02T00:00:00+00:00", "1D vs 3rd"),  # USA vs Bosnia
    "537420": (84, "2026-07-02T19:00:00+00:00", "1H vs 2J"),   # Spain vs 2J
    "537419": (83, "2026-07-02T23:00:00+00:00", "2K vs 2L"),   # 2K vs Croatia
    "537429": (85, "2026-07-03T03:00:00+00:00", "1B vs 3rd"),  # Switzerland vs 3rd[G/J]
    "537428": (88, "2026-07-03T18:00:00+00:00", "2D vs 2G"),   # Australia vs Egypt
    "537427": (86, "2026-07-03T22:00:00+00:00", "1J vs 2H"),   # Argentina vs Cape Verde
    "537430": (87, "2026-07-04T01:30:00+00:00", "1K vs 3rd"),  # 1K vs Ghana
}


def test_pinned_ext_id_to_match_number_matches_implementation():
    """The implementation's map MUST agree with the pinned cross-reference."""
    for ext_id, (expected_match_num, _kickoff, _label) in PINNED.items():
        actual = EXT_ID_TO_MATCH_NUMBER.get(ext_id)
        assert actual == expected_match_num, (
            f"ext_id {ext_id}: expected M{expected_match_num} per "
            f"Wikipedia, got M{actual}"
        )


def _r32_slice() -> dict[str, int]:
    """R32-only slice of the (now KO-wide) implementation map.

    EXT_ID_TO_MATCH_NUMBER was extended in v2.195.x to cover R16 through
    Final; this file tests the R32 slice only. Downstream stages are
    pinned separately in test_ko_ext_id_mapping.py.
    """
    return {k: v for k, v in EXT_ID_TO_MATCH_NUMBER.items() if 73 <= v <= 88}


def test_all_16_r32_ext_ids_pinned():
    """The pinned table must cover every R32 ext_id we know about."""
    assert set(PINNED.keys()) == set(_r32_slice().keys()), (
        "Pinned set and implementation R32 slice must match"
    )
    assert len(PINNED) == 16


def test_each_pinned_match_number_has_bracket_source():
    """Every pinned FIFA match number must have a matching entry in
    R32_SOURCES — otherwise resolution would fail silently."""
    for ext_id, (match_num, _kickoff, _label) in PINNED.items():
        assert match_num in R32_SOURCES, (
            f"ext_id {ext_id} pinned to M{match_num} but R32_SOURCES "
            f"doesn't define that match"
        )


def test_no_match_number_appears_twice():
    """Sanity: each FIFA match number is unique across the KO-wide map."""
    values = list(EXT_ID_TO_MATCH_NUMBER.values())
    assert len(values) == len(set(values)), (
        f"Duplicate match numbers in EXT_ID_TO_MATCH_NUMBER: {values}"
    )


def test_match_numbers_cover_73_to_88():
    """All 16 FIFA R32 match numbers (73..88) must appear exactly once
    in the R32 slice of the KO-wide map."""
    assert set(_r32_slice().values()) == set(range(73, 89))
