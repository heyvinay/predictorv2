"""Read-time resolver for R32 slot placeholders (v2.183.0).

Football-Data writes R32 fixtures with placeholder team names
(`slot:round_of_32:{external_id}:home` / `:away`) until FIFA publishes
the lineup and FD ingests it — typically hours after the last group
match finishes. Our system can deduce qualifiers from group standings
the moment a group's six matches are all FINISHED, so we resolve those
placeholders at READ time and surface real team names everywhere.

Third-place assignment (v2.183.0): uses the FIFA Annex C lookup table
(`thirdPlaceMapping.json`, 495 rows) mirrored from the entry wizard's
`frontend/src/lib/config/thirdPlaceMapping.json`. Same source of
truth as `frontend/src/lib/utils/bracketResolver.ts:resolveMatchSource`
— so a user's predicted-bracket view and the live /results bracket
view will always show the same assignment.

Design:
  * DB stays untouched. When Football-Data eventually writes real names
    via score_sync, that's the source of truth; our resolver becomes a
    no-op for that fixture (placeholder no longer matches).
  * Resolution is per-request: build the resolver once per request,
    then pass into resolve_r32_pair() for each row.
  * Only resolves group positions whose source group is FULLY SETTLED
    (every fixture FINISHED).
  * Third-place sources only resolve once all eight third-place groups
    are settled (the groupKey is fully determined). Until then they
    stay TBD — partial knowledge of which 8 groups qualify isn't
    enough to look up Annex C.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.services.bracket_seeding import (
    EXT_ID_TO_MATCH_NUMBER,
    R32_SOURCES,
    is_r32_slot_placeholder,
    parse_r32_slot,
)
from app.services.standings import (
    get_actual_group_standings,
    get_qualifying_third_place_teams,
)


log = logging.getLogger(__name__)


# Map of R32 match_number → group-winner-position key used to index
# into the FIFA Annex C table. Mirrors MATCH_TO_WINNER_KEY in
# frontend/src/lib/utils/bracketResolver.ts:58. The eight R32 matches
# that take a third-place opponent are 74, 77, 79, 80, 81, 82, 85, 87.
_MATCH_TO_WINNER_KEY: dict[int, str] = {
    74: "1E",
    77: "1I",
    79: "1A",
    80: "1L",
    81: "1D",
    82: "1G",
    85: "1B",
    87: "1K",
}


def _load_third_place_mapping() -> dict[str, dict[str, str]]:
    """Load the FIFA Annex C third-place assignment table.

    The same file lives at frontend/src/lib/config/thirdPlaceMapping.json
    — the backend copy is kept in sync manually for now (single-source
    refactor deferred until we have a shared/ mount for tournament
    config). 495 rows; outer key is the alphabetically-sorted 8-letter
    string of qualifying groups (e.g. 'ABDEFGIL'); inner key is the
    group-winner position ('1A', '1B', ..., '1L'); value is the source
    slot of the third-placed team to face them (e.g. '3E').
    """
    path = Path(__file__).parent / "thirdPlaceMapping.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Loaded once at import time — 495 rows × ~8 entries each. Small enough
# to live in memory; never mutated.
_THIRD_PLACE_MAPPING = _load_third_place_mapping()


class R32Resolver:
    """Bundled state for resolving slot placeholders within one request.

    Built once at the top of an endpoint; passed to each
    `resolve_team_name()` call. Caches the settled-groups set, the
    group_position → team map, the qualifying third-place teams, and
    the FIFA Annex C key derived from those qualifiers.

    Group-position sources (1A, 2B, ...) resolve as soon as their
    source group is settled. Third-place sources resolve only once
    all 12 groups are settled (so the qualifying-8 list is final and
    the Annex C key is fully determined).
    """

    def __init__(
        self,
        *,
        settled_groups: set[str],
        positions: dict[str, str],  # "1A" → "Mexico"
        third_qualifier_by_group: dict[str, str] | None,  # "E" → "Ecuador"
        annex_c_key: str | None,  # e.g. "ABDEFGIL"
    ):
        self._settled = settled_groups
        self._positions = positions
        self._third_by_group = third_qualifier_by_group or {}
        self._annex_c_key = annex_c_key
        self._annex_c_row = (
            _THIRD_PLACE_MAPPING.get(annex_c_key) if annex_c_key else None
        )

    def resolve_team_name(self, placeholder: str) -> str | None:
        """Map a `slot:round_of_32:{ext}:home|away` string to a real
        team name, or None if it can't be resolved yet.

        Returns None when:
          * The string isn't a recognised R32 slot.
          * The R32 external_id isn't in our seeding map.
          * The match's group source references an unsettled group.
          * The match's third_place source can't be looked up yet —
            either not all 12 groups are settled (annex_c_key is None)
            or the lookup table doesn't contain this key (shouldn't
            happen for valid 8-letter combinations).
        """
        parsed = parse_r32_slot(placeholder)
        if not parsed:
            return None
        ext_id, side = parsed
        match_num = EXT_ID_TO_MATCH_NUMBER.get(ext_id)
        if match_num is None:
            return None
        home_src, away_src = R32_SOURCES[match_num]
        src = home_src if side == "home" else away_src

        if src["type"] == "group":
            position = src["position"]
            group_letter = position[1:]
            if group_letter not in self._settled:
                return None
            return self._positions.get(position)

        # third_place source — official FIFA Annex C lookup (matches the
        # entry wizard's bracketResolver.ts exactly).
        if self._annex_c_row is None:
            return None
        winner_pos = _MATCH_TO_WINNER_KEY.get(match_num)
        if not winner_pos:
            return None
        target_slot = self._annex_c_row.get(winner_pos)  # e.g. "3E"
        if not target_slot:
            return None
        target_group = target_slot[1:]  # "E"
        return self._third_by_group.get(target_group)


async def build_r32_resolver(session: AsyncSession) -> R32Resolver:
    """Build a resolver from the DB. Call once per request that needs
    to surface R32 team names."""
    # Settled groups: every fixture in the group is FINISHED.
    result = await session.execute(
        select(Fixture.group, Fixture.status).where(Fixture.stage == "group")
    )
    by_group: dict[str, list[MatchStatus]] = {}
    for grp, status in result.all():
        if grp:
            by_group.setdefault(grp, []).append(status)
    settled = {
        g for g, statuses in by_group.items()
        if all(s == MatchStatus.FINISHED for s in statuses)
    }

    raw_standings = await get_actual_group_standings(session)
    # Build "1A" → team-name map ONLY for settled groups; for unsettled
    # groups the order could still flip on the last match.
    positions: dict[str, str] = {}
    for grp, rows in raw_standings.items():
        if grp not in settled:
            continue
        for i, row in enumerate(rows, start=1):
            positions[f"{i}{grp}"] = row["team"]

    # Third-place qualifiers: only meaningful once ALL 12 groups are
    # settled. Until then, the qualifying-8 list could shift on the
    # last match of any unsettled group, which would re-key the
    # Annex C lookup. So we only build the lookup state when settled
    # covers all 12 groups.
    third_by_group: dict[str, str] | None = None
    annex_c_key: str | None = None
    if len(settled) == 12:
        qualifiers = await get_qualifying_third_place_teams(session)
        third_by_group = {q["group"]: q["team"] for q in qualifiers}
        # Annex C key: alphabetically-sorted 8-letter string of
        # qualifying groups (matches the frontend bracketResolver
        # behaviour exactly).
        annex_c_key = "".join(sorted(third_by_group.keys()))

    return R32Resolver(
        settled_groups=settled,
        positions=positions,
        third_qualifier_by_group=third_by_group,
        annex_c_key=annex_c_key,
    )


def resolve_r32_pair(
    resolver: R32Resolver,
    home: str | None,
    away: str | None,
) -> tuple[str | None, str | None]:
    """Apply the resolver to a single fixture's (home, away) pair.

    Returns the resolved names, or the originals if they aren't
    placeholders / can't be resolved. Pure function — caller decides
    whether to write the resolved name to the response.
    """
    if home and is_r32_slot_placeholder(home):
        resolved = resolver.resolve_team_name(home)
        if resolved:
            home = resolved
    if away and is_r32_slot_placeholder(away):
        resolved = resolver.resolve_team_name(away)
        if resolved:
            away = resolved
    return home, away
