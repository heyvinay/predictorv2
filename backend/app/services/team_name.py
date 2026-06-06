"""Team-name display helpers (backend mirror of frontend `teamName.ts`).

Ports the SHORT_NAMES map and `display_team_name()` helper so backend
renderers (e.g. submission email recap) can apply the same abbreviations
the wizard uses, without round-tripping through the frontend. Keep this
list in sync with `frontend/src/lib/utils/teamName.ts:24-31`.
"""

from __future__ import annotations


_SLOT_PREFIX = "slot:"

# Shorter display strings for countries whose canonical names overflow
# tight UI / monospace surfaces (target ≤11 chars). Names not in this map
# render unchanged.
_SHORT_NAMES: dict[str, str] = {
    "Bosnia-Herzegovina": "Bosnia",
    "Cape Verde Islands": "Cape Verde",
    "United States": "USA",
    "Saudi Arabia": "S. Arabia",
    "South Africa": "S. Africa",
    "South Korea": "S. Korea",
}


def is_placeholder_team(name: str | None) -> bool:
    return isinstance(name, str) and name.startswith(_SLOT_PREFIX)


def display_team_name(name: str | None) -> str:
    """Format a team name for display.

    Placeholder slot strings render as "TBD"; real names pass through,
    with a small set of long names shortened.
    """
    if not name:
        return "TBD"
    if is_placeholder_team(name):
        return "TBD"
    return _SHORT_NAMES.get(name, name)
