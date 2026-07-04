"""FIFA World Cup 2026 R32 bracket seeding map (v2.182.1).

Ported from `frontend/src/lib/config/bracketConfig.ts` so the backend
can resolve `slot:round_of_32:{external_id}:home` placeholders against
group-standings without a frontend round-trip. Source:
  https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage

Each R32 match has TWO sources:
  - `("group", "1A")` — group A's 1st-placed team
  - `("group", "2B")` — group B's 2nd-placed team
  - `("third_place", ["A","B","C","D","F"])` — best third-placed team
     whose group is in the list (consumed from the qualifying-8 pool)

R32 external IDs run 537415..537430, mapping to match numbers 73..88.
Resolution only applies once a group is fully settled (all six fixtures
FINISHED); during in-play group games, slot placeholders stay TBD.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class GroupSource(TypedDict):
    type: Literal["group"]
    position: str  # e.g. "1A", "2B"


class ThirdPlaceSource(TypedDict):
    type: Literal["third_place"]
    possible_groups: list[str]


# R32 source map: match_number → (home_source, away_source).
# Keep in lock-step with frontend/src/lib/config/bracketConfig.ts.
R32_SOURCES: dict[int, tuple[dict, dict]] = {
    73: ({"type": "group", "position": "2A"}, {"type": "group", "position": "2B"}),
    74: ({"type": "group", "position": "1E"}, {"type": "third_place", "possible_groups": ["A", "B", "C", "D", "F"]}),
    75: ({"type": "group", "position": "1F"}, {"type": "group", "position": "2C"}),
    76: ({"type": "group", "position": "1C"}, {"type": "group", "position": "2F"}),
    77: ({"type": "group", "position": "1I"}, {"type": "third_place", "possible_groups": ["C", "D", "F", "G", "H"]}),
    78: ({"type": "group", "position": "2E"}, {"type": "group", "position": "2I"}),
    79: ({"type": "group", "position": "1A"}, {"type": "third_place", "possible_groups": ["C", "E", "F", "H", "I"]}),
    80: ({"type": "group", "position": "1L"}, {"type": "third_place", "possible_groups": ["E", "H", "I", "J", "K"]}),
    81: ({"type": "group", "position": "1D"}, {"type": "third_place", "possible_groups": ["B", "E", "F", "I", "J"]}),
    82: ({"type": "group", "position": "1G"}, {"type": "third_place", "possible_groups": ["A", "E", "H", "I", "J"]}),
    83: ({"type": "group", "position": "2K"}, {"type": "group", "position": "2L"}),
    84: ({"type": "group", "position": "1H"}, {"type": "group", "position": "2J"}),
    85: ({"type": "group", "position": "1B"}, {"type": "third_place", "possible_groups": ["E", "F", "G", "I", "J"]}),
    86: ({"type": "group", "position": "1J"}, {"type": "group", "position": "2H"}),
    87: ({"type": "group", "position": "1K"}, {"type": "third_place", "possible_groups": ["D", "E", "I", "J", "L"]}),
    88: ({"type": "group", "position": "2D"}, {"type": "group", "position": "2G"}),
}

# Map Football-Data external_id → FIFA match number, across all knockout
# stages R32 → R16 → QF → SF → Final. Two swaps have burned us; the R16
# swap (v2.195.x, Paraguay–France ↔ Canada–Morocco) had exactly the same
# shape as the earlier R32 swap (v2.181.1 → v2.183.0):
#
#   * v2.181.1 assumed `ext_id - 537342 = FIFA match number` for R32.
#     Wrong — Football-Data assigns ext_ids by creation order, not FIFA
#     numbering. Every R32 fixture displayed under the wrong kickoff.
#   * v2.184.x fixed R32 with this hand-verified map, but kept a
#     kickoff-sort fallback in ko_lineup_resolver.py for R16+ stages,
#     assuming FIFA schedules match numbers chronologically. That
#     assumption held for M91-M96 but broke for the M89/M90 pair on
#     Saturday 4 July 2026 — Canada–Morocco (M90) kicks off in Houston
#     at 17:00Z, four hours BEFORE Paraguay–France (M89, Philadelphia,
#     21:00Z). Kickoff-sort therefore labelled the Houston row as M89,
#     which then walked ROUND_OF_16_SOURCES[89] and painted "winner of
#     Paraguay match, winner of France match" onto Canada–Morocco.
#
# Lesson: FIFA match numbers are STRUCTURAL (bracket geometry). Kickoff
# times are OPERATIONAL (broadcast schedule). Never derive one from the
# other. Hand-verify every ext_id against BOTH the ROUND_OF_*_SOURCES
# bracket structure AND the UTC kickoff in backend/data/wc2026_fixtures.json.
#
# Pinned by:
#   * tests/test_r32_ext_id_mapping.py (R32, ext_ids 537415-537430)
#   * tests/test_ko_ext_id_mapping.py  (R16+, ext_ids 537375-537390)
# Note the ext_id ranges DECREASE from R32 to R16 — Football-Data's
# publication order for the tournament is not stage-ordered, so ID
# arithmetic is meaningless. Trust only the hand-verified map + tests.
EXT_ID_TO_MATCH_NUMBER: dict[str, int] = {
    # ── R32 (73-88, ext_ids 537415-537430) ─────────────────────────────
    "537417": 73,  # Sun 28 Jun 19:00 UTC — South Africa vs Canada
    "537423": 76,  # Mon 29 Jun 17:00 UTC — Brazil vs Japan
    "537415": 74,  # Mon 29 Jun 20:30 UTC — Germany vs Paraguay
    "537418": 75,  # Tue 30 Jun 01:00 UTC — Netherlands vs Morocco
    "537424": 78,  # Tue 30 Jun 17:00 UTC — Ivory Coast vs Norway
    "537416": 77,  # Tue 30 Jun 21:00 UTC — France vs Sweden
    "537425": 79,  # Wed 01 Jul 01:00 UTC — Mexico vs Ecuador
    "537426": 80,  # Wed 01 Jul 16:00 UTC — England vs 3rd[I/K]
    "537422": 82,  # Wed 01 Jul 20:00 UTC — Belgium vs 3rd[A/I/J]
    "537421": 81,  # Thu 02 Jul 00:00 UTC — USA vs Bosnia
    "537420": 84,  # Thu 02 Jul 19:00 UTC — Spain vs 2J
    "537419": 83,  # Thu 02 Jul 23:00 UTC — 2K vs Croatia
    "537429": 85,  # Fri 03 Jul 03:00 UTC — Switzerland vs 3rd[G/J]
    "537428": 88,  # Fri 03 Jul 18:00 UTC — Australia vs Egypt
    "537427": 86,  # Fri 03 Jul 22:00 UTC — Argentina vs Cape Verde
    "537430": 87,  # Sat 04 Jul 01:30 UTC — 1K vs Ghana
    # ── R16 (89-96, ext_ids 537375-537382) ─────────────────────────────
    # Structural: ROUND_OF_16_SOURCES[89]=(M74w, M77w)=Paraguay+France;
    #             ROUND_OF_16_SOURCES[90]=(M73w, M75w)=Canada+Morocco.
    # M89 kicks off AFTER M90 — the exception that broke the resolver.
    "537375": 89,  # Sat 04 Jul 21:00 UTC — Paraguay vs France (Philadelphia)
    "537376": 90,  # Sat 04 Jul 17:00 UTC — Canada vs Morocco (Houston)
    "537377": 91,  # Sun 05 Jul 20:00 UTC — winners M76 (Brazil) vs M78 (Norway)
    "537378": 92,  # Mon 06 Jul 00:00 UTC — winners M79 (Mexico) vs M80 (England)
    "537379": 93,  # Mon 06 Jul 19:00 UTC — winners M83 vs M84 (Croatia vs Spain)
    "537380": 94,  # Tue 07 Jul 00:00 UTC — winners M81 (USA) vs M82 (Belgium)
    "537381": 95,  # Tue 07 Jul 16:00 UTC — winners M86 (Argentina) vs M88 (Australia)
    "537382": 96,  # Tue 07 Jul 20:00 UTC — winners M85 (Switzerland) vs M87
    # ── QF (97-100, ext_ids 537383-537386) ─────────────────────────────
    # Cross-referenced against beIN/ESPN/olympics.com QF schedule.
    # M97 kicks off first (Foxborough Jul 9), M100 last (Kansas City Jul 11 evening
    # = 12 Jul 01:00Z). Match-number ordering happens to match kickoff for QFs.
    "537383": 97,   # Thu 09 Jul 20:00 UTC — winners M89 vs M90
    "537384": 98,   # Fri 10 Jul 19:00 UTC — winners M93 vs M94
    "537385": 99,   # Sat 11 Jul 21:00 UTC — winners M91 vs M92
    "537386": 100,  # Sun 12 Jul 01:00 UTC — winners M95 vs M96
    # ── SF (101-102, ext_ids 537387-537388) ────────────────────────────
    "537387": 101,  # Tue 14 Jul 19:00 UTC — winners M97 vs M98
    "537388": 102,  # Wed 15 Jul 19:00 UTC — winners M99 vs M100
    # ── Final (104, ext_id 537390) ─────────────────────────────────────
    # M103 (third_place, ext_id 537389) intentionally OMITTED — unscored
    # per CLAUDE.md invariant. Resolver's stage filter excludes it too.
    "537390": 104,  # Sun 19 Jul 19:00 UTC — winners M101 vs M102
}


def is_r32_slot_placeholder(name: str | None) -> bool:
    """True if a team-name string is the `slot:round_of_32:...` placeholder
    Football-Data writes before publishing the real lineup."""
    return bool(name) and name.startswith("slot:round_of_32:")


def parse_r32_slot(name: str) -> tuple[str, str] | None:
    """Parse `slot:round_of_32:{external_id}:home` → (external_id, side).

    Returns None if the string doesn't match the expected shape.
    """
    if not is_r32_slot_placeholder(name):
        return None
    parts = name.split(":")
    # Expected: ['slot', 'round_of_32', '<ext>', 'home' | 'away']
    if len(parts) != 4 or parts[3] not in ("home", "away"):
        return None
    return parts[2], parts[3]


# ─── Downstream KO bracket sources (v2.184.x) ──────────────────────────────
# Ported from frontend/src/lib/config/bracketConfig.ts:177-330.
# Each entry: match_number → (home_source, away_source) where each source is
# a dict {"type": "winner", "match_number": N}. Walking is recursive:
# R16 sources reference R32 winners; QF references R16; SF references QF;
# Final references SF. third_place is intentionally absent — unscored stage.
#
# Match numbers per FIFA 2026 schedule:
#   R32:  73-88   (16 matches)
#   R16:  89-96   (8 matches)
#   QF:   97-100  (4 matches)
#   SF:   101-102 (2 matches)
#   F:    104     (1 match; M103 is third_place playoff, omitted)

ROUND_OF_16_SOURCES: dict[int, tuple[dict, dict]] = {
    89: ({"type": "winner", "match_number": 74}, {"type": "winner", "match_number": 77}),
    90: ({"type": "winner", "match_number": 73}, {"type": "winner", "match_number": 75}),
    91: ({"type": "winner", "match_number": 76}, {"type": "winner", "match_number": 78}),
    92: ({"type": "winner", "match_number": 79}, {"type": "winner", "match_number": 80}),
    93: ({"type": "winner", "match_number": 83}, {"type": "winner", "match_number": 84}),
    94: ({"type": "winner", "match_number": 81}, {"type": "winner", "match_number": 82}),
    95: ({"type": "winner", "match_number": 86}, {"type": "winner", "match_number": 88}),
    96: ({"type": "winner", "match_number": 85}, {"type": "winner", "match_number": 87}),
}

QUARTER_FINAL_SOURCES: dict[int, tuple[dict, dict]] = {
    97: ({"type": "winner", "match_number": 89}, {"type": "winner", "match_number": 90}),
    98: ({"type": "winner", "match_number": 93}, {"type": "winner", "match_number": 94}),
    99: ({"type": "winner", "match_number": 91}, {"type": "winner", "match_number": 92}),
    100: ({"type": "winner", "match_number": 95}, {"type": "winner", "match_number": 96}),
}

SEMI_FINAL_SOURCES: dict[int, tuple[dict, dict]] = {
    101: ({"type": "winner", "match_number": 97}, {"type": "winner", "match_number": 98}),
    102: ({"type": "winner", "match_number": 99}, {"type": "winner", "match_number": 100}),
}

FINAL_SOURCES: dict[int, tuple[dict, dict]] = {
    104: ({"type": "winner", "match_number": 101}, {"type": "winner", "match_number": 102}),
}


# Stage → first match number in that stage (used to map kickoff-sorted
# index back to FIFA match number for stages R16+).
STAGE_FIRST_MATCH_NUMBER: dict[str, int] = {
    "round_of_16": 89,
    "quarter_final": 97,
    "semi_final": 101,
    "final": 104,
}


def is_downstream_ko_slot_placeholder(name: str | None) -> bool:
    """True if a team-name string is a downstream KO slot placeholder
    (`slot:round_of_16:...` / `slot:quarter_final:...` / ...).

    R32 slots are handled separately by `is_r32_slot_placeholder`; this
    helper covers R16 / QF / SF / F.
    """
    if not name:
        return False
    return any(
        name.startswith(f"slot:{stage}:")
        for stage in ("round_of_16", "quarter_final", "semi_final", "final")
    )


def parse_downstream_ko_slot(name: str) -> tuple[str, str, str] | None:
    """Parse `slot:{stage}:{external_id}:{side}` → (stage, external_id, side).

    Returns None if the string doesn't match the expected shape.
    """
    if not is_downstream_ko_slot_placeholder(name):
        return None
    parts = name.split(":")
    if len(parts) != 4 or parts[3] not in ("home", "away"):
        return None
    return parts[1], parts[2], parts[3]
