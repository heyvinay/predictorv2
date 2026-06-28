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

# Map Football-Data R32 external_id → FIFA match number (v2.183.1).
#
# Cross-referenced against the official 2026 FWC Round of 32 schedule on
# Wikipedia (https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_round_of_32)
# by matching each fixture's UTC kickoff to FIFA's published match number.
#
# An earlier release (2.181.1) ASSUMED that Football-Data's ext_ids count
# up in FIFA's match-number order (537415 = M73, 537416 = M74, ...). That
# assumption was wrong — Football-Data's IDs follow a different ordering
# (likely an internal one keyed on creation order at fixture-publish time).
# Every R32 fixture displayed under the wrong kickoff for the duration
# 2.181.1 → 2.183.0 was live, until this fix.
#
# Pinned by tests/test_r32_ext_id_mapping.py — if Football-Data ever
# changes their ext_ids OR if FIFA reschedules a match between IDs, the
# test catches it.
EXT_ID_TO_MATCH_NUMBER: dict[str, int] = {
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
