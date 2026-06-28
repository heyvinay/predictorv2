"""Read-time resolver for R32 slot placeholders (v2.182.1).

Football-Data writes R32 fixtures with placeholder team names
(`slot:round_of_32:{external_id}:home` / `:away`) until FIFA publishes
the lineup and FD ingests it — typically hours after the last group
match finishes. Our system can deduce qualifiers from group standings
the moment a group's six matches are all FINISHED, so we resolve those
placeholders at READ time and surface real team names everywhere.

Design:
  * DB stays untouched. When Football-Data eventually writes real names
    via score_sync, that's the source of truth; our resolver becomes a
    no-op for that fixture (placeholder no longer matches).
  * Resolution is per-request: build the standings map once per
    request, then pass it into resolve_r32_team_name() for each row.
  * Only resolves groups that are FULLY SETTLED (every fixture
    FINISHED). Partial-group standings can still shift if the last
    match flips the order, so resolving them would surface a name
    that might be wrong by kickoff.
"""

from __future__ import annotations

import logging
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


class R32Resolver:
    """Bundled state for resolving slot placeholders within one request.

    Built once at the top of an endpoint; passed to each
    `resolve_team_name()` call. Caches the settled-groups set, the
    group_position → team map, and the third-place qualifier pool.
    """

    def __init__(
        self,
        *,
        settled_groups: set[str],
        positions: dict[str, str],  # "1A" → "Mexico"
        third_qualifiers: list[dict[str, Any]],
    ):
        self._settled = settled_groups
        self._positions = positions
        # Greedy third-place assignment: track which group letters have
        # been claimed across the 8 R32 third-place slots. Same shape
        # as scripts/dev_populate_r32.py — first eligible qualifier
        # from each match's possible_groups list, in match_number order.
        self._third_assigned: dict[int, str] = {}
        self._third_qualifiers = third_qualifiers
        # Pre-compute all R32 third-place assignments in match order so
        # the resolver's output is deterministic regardless of which
        # fixture happens to be looked up first.
        self._assign_thirds_greedy()

    def _assign_thirds_greedy(self) -> None:
        used_groups: set[str] = set()
        for match_num in sorted(R32_SOURCES):
            for src in R32_SOURCES[match_num]:
                if src["type"] != "third_place":
                    continue
                possible = src["possible_groups"]
                pick = self._pick_third(possible, used_groups)
                if pick:
                    self._third_assigned[match_num] = pick["team"]
                    used_groups.add(pick["group"])
                # Each R32 match has at most one third_place source,
                # so we only need one entry per match.
                break

    def _pick_third(
        self, possible_groups: list[str], used: set[str]
    ) -> dict[str, Any] | None:
        for q in self._third_qualifiers:
            grp = q.get("group")
            if not grp or grp in used:
                continue
            if grp not in possible_groups:
                continue
            # All eight third-place teams must come from settled groups;
            # if their parent group isn't settled, treat the qualifier
            # as unresolved.
            if grp not in self._settled:
                continue
            return q
        return None

    def resolve_team_name(self, placeholder: str) -> str | None:
        """Map a `slot:round_of_32:{ext}:home|away` string to a real
        team name, or None if it can't be resolved yet.

        Returns None when:
          * The string isn't a recognised R32 slot.
          * The R32 external_id isn't in our seeding map.
          * The match's source needs a group that isn't fully settled.
          * The match's third-place source has no available qualifier
            (shouldn't happen once all 12 groups settle, but possible
            mid-progression).
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

        # third_place source — return the pre-assigned team for this match.
        return self._third_assigned.get(match_num)


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

    third_qualifiers = await get_qualifying_third_place_teams(session)

    return R32Resolver(
        settled_groups=settled,
        positions=positions,
        third_qualifiers=third_qualifiers,
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
