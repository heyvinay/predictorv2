"""Standings drift verification (v2.182.0).

Detect-only verifier that cross-checks our computed group standings
against a trusted external source. Disagreements are recorded as
`StandingsDriftEvent` rows that an admin reviews and resolves via the
admin UI; the verifier never overwrites `/standings`.

Source order (to be expanded in 2.182.1):
  Tier 1: Football-Data /standings (already integrated, same provider
          as our match results — same-provider sanity check)
  Tier 2: ESPN /standings (TODO 2.182.1)
  Tier 3: Wikipedia parse (TODO 2.182.1)

For 2.182.0 only Tier 1 is implemented. The chain function signature
is forward-compatible so 2.182.1 can drop in the other sources without
touching callers.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.standings_drift import TrustedSource
from app.services.external.football_data import (
    FootballDataClient,
    FootballDataError,
)
from app.services.locking import get_active_competition
from app.services.standings import get_actual_group_standings


log = logging.getLogger(__name__)


class TrustedSourceUnavailable(Exception):
    """All trusted sources failed — no drift verdict possible."""


# Fields compared per row when looking for drift. Order doesn't matter;
# any inequality on any of these triggers a disagreement.
_COMPARED_FIELDS = ("position", "points", "goal_difference", "goals_for", "goals_against")


# ---------------------------------------------------------------------------
# Source adapters: each returns dict[group_letter -> list[normalised row]]
# ---------------------------------------------------------------------------


def _normalize_team_name(name: str) -> str:
    """Cheap normaliser for cross-source comparison. Both Football-Data
    and our DB use Football-Data canonical names today, so this is
    mostly a no-op safety guard."""
    return (name or "").strip()


def _football_data_to_normalized(
    payload: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Map Football-Data /standings response to our canonical row shape.

    Football-Data: group="Group A", table rows have `draw`, `goalsFor`,
    `goalsAgainst`, `goalDifference`, `playedGames`, `team.name`.

    Output: {"A": [{"position":1, "team":"Mexico", "played":3, ...}, ...]}
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for group_payload in payload:
        group_label = group_payload.get("group", "")
        # Skip non-TOTAL or non-group tables defensively.
        if group_payload.get("type", "TOTAL") != "TOTAL":
            continue
        # "Group A" → "A"; tolerant of casing / spacing.
        letter = group_label.replace("Group", "").strip().upper()[:1]
        if not letter:
            continue
        rows: list[dict[str, Any]] = []
        for row in group_payload.get("table", []):
            team = row.get("team", {}) or {}
            rows.append(
                {
                    "position": int(row.get("position", 0)),
                    "team": _normalize_team_name(team.get("name", "")),
                    "played": int(row.get("playedGames", 0)),
                    "won": int(row.get("won", 0)),
                    "drawn": int(row.get("draw", 0)),
                    "lost": int(row.get("lost", 0)),
                    "points": int(row.get("points", 0)),
                    "goals_for": int(row.get("goalsFor", 0)),
                    "goals_against": int(row.get("goalsAgainst", 0)),
                    "goal_difference": int(row.get("goalDifference", 0)),
                }
            )
        out[letter] = sorted(rows, key=lambda r: r["position"])
    return out


def _ours_to_normalized(
    payload: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Map services.standings output to the same canonical shape.

    Input from get_actual_group_standings: {group_letter: list[dict with
    team/group/played/won/drawn/lost/goals_for/goals_against/
    goal_difference/points]} — list is already sorted by FIFA tiebreakers
    so we assign positions by index.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for group_letter, rows in payload.items():
        normalised: list[dict[str, Any]] = []
        for i, r in enumerate(rows, start=1):
            normalised.append(
                {
                    "position": i,
                    "team": _normalize_team_name(r.get("team", "")),
                    "played": int(r.get("played", 0)),
                    "won": int(r.get("won", 0)),
                    "drawn": int(r.get("drawn", 0)),
                    "lost": int(r.get("lost", 0)),
                    "points": int(r.get("points", 0)),
                    "goals_for": int(r.get("goals_for", 0)),
                    "goals_against": int(r.get("goals_against", 0)),
                    "goal_difference": int(r.get("goal_difference", 0)),
                }
            )
        out[group_letter] = normalised
    return out


async def fetch_football_data_standings(
    code: str,
) -> dict[str, list[dict[str, Any]]]:
    """Tier-1 trusted source. Raises FootballDataError on any failure."""
    client = FootballDataClient()
    payload = await client.get_standings(code)
    return _football_data_to_normalized(payload)


async def fetch_trusted_standings(
    code: str,
) -> tuple[TrustedSource, dict[str, list[dict[str, Any]]]]:
    """Try sources in order; return the first one that returns a non-empty
    standings dict. Raises TrustedSourceUnavailable if all sources fail.

    For 2.182.0 only Football-Data is wired; ESPN + Wikipedia get added
    in 2.182.1 inside this function (no caller changes needed).
    """
    try:
        data = await fetch_football_data_standings(code)
        if data:
            return TrustedSource.FOOTBALL_DATA, data
    except FootballDataError as exc:
        log.warning("Football-Data standings unavailable: %s", exc)

    raise TrustedSourceUnavailable(
        "No trusted source returned standings — drift verdict skipped"
    )


# ---------------------------------------------------------------------------
# Pure comparator — testable in isolation
# ---------------------------------------------------------------------------


def compare_standings(
    ours: dict[str, list[dict[str, Any]]],
    theirs: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Compare two normalised standings dicts. Returns only the groups
    that actually disagree.

    Two groups disagree if:
      * Either side reports a team the other side doesn't, OR
      * Any compared field (position/points/GD/GF/GA) differs for any team
        on either side, when matched by team name.

    Output shape:
        {"A": {"ours": [<rows>], "theirs": [<rows>]}, "C": {...}}
    """
    groups = sorted(set(ours.keys()) | set(theirs.keys()))
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for group in groups:
        our_rows = ours.get(group, [])
        their_rows = theirs.get(group, [])

        our_by_team = {r["team"]: r for r in our_rows}
        their_by_team = {r["team"]: r for r in their_rows}

        if set(our_by_team.keys()) != set(their_by_team.keys()):
            out[group] = {"ours": our_rows, "theirs": their_rows}
            continue

        disagrees = False
        for team_name in our_by_team:
            our_row = our_by_team[team_name]
            their_row = their_by_team[team_name]
            for field in _COMPARED_FIELDS:
                if our_row.get(field) != their_row.get(field):
                    disagrees = True
                    break
            if disagrees:
                break

        if disagrees:
            out[group] = {"ours": our_rows, "theirs": their_rows}
    return out


# ---------------------------------------------------------------------------
# Top-level verification orchestrator
# ---------------------------------------------------------------------------


async def _groups_with_all_matches_finished(
    session: AsyncSession,
) -> set[str]:
    """Return the set of group letters where every group-stage fixture
    is FINISHED. Only fully-settled groups are eligible for drift
    verification (v2.182.0).

    Why: Football-Data's /standings endpoint INCLUDES in-play scores
    (a live 0-1 contributes 3 pts to the leading team), while our
    `get_actual_group_standings` only counts FINISHED matches. During
    a live group game, the two views disagree by definition — that
    looks like drift but isn't. Filtering to all-finished groups
    eliminates the false positives. Once a group's third matchday
    settles, this filter admits the group and the verifier produces a
    meaningful verdict.
    """
    result = await session.execute(
        select(Fixture.group, Fixture.status).where(Fixture.stage == "group")
    )
    by_group: dict[str, list[MatchStatus]] = {}
    for grp, status in result.all():
        if not grp:
            continue
        by_group.setdefault(grp, []).append(status)

    out: set[str] = set()
    for grp, statuses in by_group.items():
        if all(s == MatchStatus.FINISHED for s in statuses):
            out.add(grp)
    return out


async def run_verification(
    session: AsyncSession,
) -> tuple[TrustedSource | None, dict[str, dict[str, list[dict[str, Any]]]]]:
    """Compute our standings, fetch the trusted source, return any drift.

    Returns (source_used, disagreements). disagreements is empty dict on
    agreement. (None, {}) when no trusted source is available — the
    caller logs and moves on without opening a drift event.

    Only groups whose six fixtures are ALL FINISHED are eligible for
    comparison (see _groups_with_all_matches_finished). Groups with any
    in-play match are silently skipped — Football-Data's standings include
    live scores; ours don't.
    """
    competition = await get_active_competition(session)
    if not competition or not competition.external_id:
        log.warning("No active competition with external_id; verification skipped")
        return None, {}

    eligible_groups = await _groups_with_all_matches_finished(session)
    if not eligible_groups:
        log.info("No fully-settled groups yet; drift verification is a no-op")
        return None, {}

    raw_ours = await get_actual_group_standings(session)
    ours_norm = {k: v for k, v in _ours_to_normalized(raw_ours).items() if k in eligible_groups}

    try:
        source, theirs_norm_all = await fetch_trusted_standings(competition.external_id)
    except TrustedSourceUnavailable as exc:
        log.warning("%s", exc)
        return None, {}

    theirs_norm = {k: v for k, v in theirs_norm_all.items() if k in eligible_groups}

    disagreements = compare_standings(ours_norm, theirs_norm)
    return source, disagreements
