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
from app.services.standings import get_actual_group_standings


log = logging.getLogger(__name__)


class R32Resolver:
    """Bundled state for resolving slot placeholders within one request.

    Built once at the top of an endpoint; passed to each
    `resolve_team_name()` call. Caches the settled-groups set and the
    group_position → team map.

    Scope (v2.182.2): resolves ONLY group-position sources (1A, 2B,
    etc.). Third-place sources are returned as None — FIFA's Annex C
    assignment table determines which qualifying-third-placed team goes
    to which R32 slot, and we don't have that table locally. v2.183.0
    will layer in a Wikipedia parser as the authoritative source for
    third-place assignments once FIFA confirms them.
    """

    def __init__(
        self,
        *,
        settled_groups: set[str],
        positions: dict[str, str],  # "1A" → "Mexico"
    ):
        self._settled = settled_groups
        self._positions = positions

    def resolve_team_name(self, placeholder: str) -> str | None:
        """Map a `slot:round_of_32:{ext}:home|away` string to a real
        team name, or None if it can't be resolved yet.

        Returns None when:
          * The string isn't a recognised R32 slot.
          * The R32 external_id isn't in our seeding map.
          * The match's source is a third-place qualifier (deferred to
            2.183.0 — FIFA's Annex C assignment table required).
          * The match's group source references an unsettled group.
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

        if src["type"] != "group":
            # third_place source — deferred to 2.183.0.
            return None

        position = src["position"]
        group_letter = position[1:]
        if group_letter not in self._settled:
            return None
        return self._positions.get(position)


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

    return R32Resolver(
        settled_groups=settled,
        positions=positions,
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
