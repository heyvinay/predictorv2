"""Standings calculation service.

Computes actual group standings from finished fixtures and scores.

Tiebreaker rules implemented (FIFA chain, partial):
  1. Points (descending)
  2. Goal difference (descending)
  3. Goals for (descending)
  4. Head-to-head points among tied teams (descending)
  5. Head-to-head goal difference (descending)
  6. Head-to-head goals scored (descending)
  7. Alphabetical by team name (deterministic last-resort, with warning)

FIFA's real rules continue past step 6 with fair-play points then drawing
of lots; we don't track either, so we stop at step 6 and resolve any
remaining ties alphabetically. Every alphabetical tiebreak emits a
TieWarning so callers can surface "this tie isn't really FIFA-resolved
— adjust your predictions if you want a different outcome" to the user.
"""

from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score


class TieWarning(TypedDict):
    """Indicates one set of teams whose tie required the alphabetical fallback.

    `context` distinguishes between in-group ranking ties (where H2H *was*
    attempted but couldn't separate the teams) and third-place qualifying
    ties (where H2H *isn't applicable* because the teams come from
    different groups).
    """

    group: str
    tied_teams: list[str]  # alphabetically sorted, for stable display
    context: str  # "group_standings" or "third_place_qualifying"


class TeamStanding:
    """Team standing in a group."""

    def __init__(self, team: str, group: str):
        self.team = team
        self.group = group
        self.played = 0
        self.won = 0
        self.drawn = 0
        self.lost = 0
        self.goals_for = 0
        self.goals_against = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def points(self) -> int:
        return self.won * 3 + self.drawn

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "team": self.team,
            "group": self.group,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "goal_difference": self.goal_difference,
            "points": self.points,
        }


# ---------------------------------------------------------------------------
# FIFA tiebreaker chain
# ---------------------------------------------------------------------------


def _apply_fifa_tiebreakers(
    teams: list[dict],
    *,
    group_matches: list[tuple[Fixture, Score]] | None = None,
    context: str,
) -> tuple[list[dict], list[TieWarning]]:
    """Rank `teams` per FWC2026 Regulations Article 13.

    Primary key is POINTS. Teams that finish level on points are resolved by
    head-to-head first (Step 1–2), then overall goal difference / goals
    (Step 2 d–e), then alphabetical as a deterministic fallback (FIFA's
    remaining criteria — conduct score, FIFA ranking, drawing of lots — are
    not predictable in this game). Returns (sorted_teams, warnings).

    Args:
        teams: team standings dicts (must contain 'team', 'group', 'points',
               'goal_difference', 'goals_for').
        group_matches: when provided (in-group sort), used to compute
               head-to-head stats among tied teams. Pass None (or empty) for
               cross-group sorts like third-place qualifying — H2H is N/A.
        context: free-form string passed into TieWarning so callers can
               distinguish in-group vs cross-group ties.
    """
    warnings: list[TieWarning] = []

    # Primary sort: points only. The tiebreaker chain triggers among teams
    # level on points (Article 13 opening clause).
    sorted_by_points = sorted(teams, key=lambda t: -t["points"])

    result: list[dict] = []
    i = 0
    while i < len(sorted_by_points):
        j = _segment_end(sorted_by_points, i, key=lambda t: (t["points"],))
        segment = sorted_by_points[i:j]
        if len(segment) == 1:
            result.append(segment[0])
        else:
            result.extend(
                _resolve_tied_segment(
                    segment,
                    group_matches=group_matches,
                    context=context,
                    warnings=warnings,
                )
            )
        i = j

    return result, warnings


def _segment_end(items: list[dict], start: int, *, key) -> int:
    """Return the first index `j` >= start+1 where the sort key changes."""
    base = key(items[start])
    j = start + 1
    while j < len(items) and key(items[j]) == base:
        j += 1
    return j


def _rank_by_overall_then_alpha(
    tied_teams: list[dict],
    *,
    context: str,
    warnings: list[TieWarning],
) -> list[dict]:
    """Step 2 d–e + fallback: rank a still-tied set by OVERALL goal difference,
    then overall goals, then alphabetical (with a TieWarning). Also the whole
    chain for cross-group (third-place) sorts where no head-to-head exists."""
    sorted_overall = sorted(
        tied_teams,
        key=lambda t: (-t["goal_difference"], -t["goals_for"]),
    )
    out: list[dict] = []
    i = 0
    while i < len(sorted_overall):
        j = _segment_end(
            sorted_overall, i,
            key=lambda t: (t["goal_difference"], t["goals_for"]),
        )
        sub = sorted_overall[i:j]
        if len(sub) > 1:
            warnings.append(
                TieWarning(
                    group=sub[0].get("group", ""),
                    tied_teams=sorted(t["team"] for t in sub),
                    context=context,
                )
            )
            sub = sorted(sub, key=lambda t: t["team"])
        out.extend(sub)
        i = j
    return out


def _resolve_group_tie(
    tied_teams: list[dict],
    *,
    group_matches: list[tuple[Fixture, Score]],
    context: str,
    warnings: list[TieWarning],
) -> list[dict]:
    """FWC2026 Article 13 Step 1 + Step 2 (head-to-head) for teams level on
    points. Recomputes the H2H mini-table for whatever subset is passed (Step 2:
    "applied to the matches between the remaining teams only"). Subsets H2H
    cannot split fall through to overall GD/goals then alphabetical. Recursion
    terminates because we only recurse into PROPER subsets."""
    if len(tied_teams) == 1:
        return tied_teams

    h2h_stats = _compute_h2h_stats(tied_teams, group_matches)
    sorted_by_h2h = sorted(
        tied_teams,
        key=lambda t: (
            -h2h_stats[t["team"]]["points"],
            -h2h_stats[t["team"]]["goal_difference"],
            -h2h_stats[t["team"]]["goals_for"],
        ),
    )

    out: list[dict] = []
    i = 0
    while i < len(sorted_by_h2h):
        j = _segment_end(
            sorted_by_h2h, i,
            key=lambda t: (
                h2h_stats[t["team"]]["points"],
                h2h_stats[t["team"]]["goal_difference"],
                h2h_stats[t["team"]]["goals_for"],
            ),
        )
        sub = sorted_by_h2h[i:j]
        if len(sub) == 1:
            out.append(sub[0])
        elif len(sub) < len(tied_teams):
            # Proper subset still tied → Step 2: recompute H2H among just them.
            out.extend(
                _resolve_group_tie(
                    sub,
                    group_matches=group_matches,
                    context=context,
                    warnings=warnings,
                )
            )
        else:
            # H2H separated no one → Step 2 d–e: overall GD/goals.
            out.extend(
                _rank_by_overall_then_alpha(sub, context=context, warnings=warnings)
            )
        i = j
    return out


def _resolve_tied_segment(
    tied_teams: list[dict],
    *,
    group_matches: list[tuple[Fixture, Score]] | None,
    context: str,
    warnings: list[TieWarning],
) -> list[dict]:
    """Resolve teams level on points. In-group sorts apply the Article 13 chain
    (head-to-head first); cross-group sorts (no group_matches) have no H2H, so
    go straight to overall GD/goals → alphabetical."""
    if not group_matches:
        return _rank_by_overall_then_alpha(tied_teams, context=context, warnings=warnings)
    return _resolve_group_tie(
        tied_teams, group_matches=group_matches, context=context, warnings=warnings
    )


def _compute_h2h_stats(
    tied_teams: list[dict],
    matches: list[tuple[Fixture, Score]],
) -> dict[str, dict[str, int]]:
    """Build a mini-table of points/GD/goals from matches BETWEEN the tied teams only."""
    tied_names = {t["team"] for t in tied_teams}
    stats = {
        t["team"]: {"points": 0, "goal_difference": 0, "goals_for": 0}
        for t in tied_teams
    }

    for fixture, score in matches:
        if score is None:
            continue
        if fixture.home_team not in tied_names or fixture.away_team not in tied_names:
            continue

        home, away = fixture.home_team, fixture.away_team
        if score.home_score > score.away_score:
            stats[home]["points"] += 3
        elif score.home_score < score.away_score:
            stats[away]["points"] += 3
        else:
            stats[home]["points"] += 1
            stats[away]["points"] += 1
        stats[home]["goals_for"] += score.home_score
        stats[home]["goal_difference"] += score.home_score - score.away_score
        stats[away]["goals_for"] += score.away_score
        stats[away]["goal_difference"] += score.away_score - score.home_score

    return stats


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_actual_group_standings(
    session: AsyncSession,
) -> dict[str, list[dict]]:
    """Compute actual group standings from finished group stage fixtures."""
    standings, _warnings = await get_actual_group_standings_with_warnings(session)
    return standings


async def get_actual_group_standings_with_warnings(
    session: AsyncSession,
) -> tuple[dict[str, list[dict]], list[TieWarning]]:
    """Same as get_actual_group_standings but also returns alphabetical-tie warnings.

    Use this variant when surfacing the warnings to the user is important
    (e.g. the predictions wizard, or any UI that explains the standings).
    """
    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            Fixture.stage == "group",
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    # Build raw standings + collect per-group match lists for H2H lookup.
    standings_by_group: dict[str, dict[str, TeamStanding]] = {}
    matches_by_group: dict[str, list[tuple[Fixture, Score]]] = {}

    for fixture, score in rows:
        if not score or not fixture.group:
            continue
        group = fixture.group
        standings_by_group.setdefault(group, {})
        matches_by_group.setdefault(group, []).append((fixture, score))

        for name in (fixture.home_team, fixture.away_team):
            if name not in standings_by_group[group]:
                standings_by_group[group][name] = TeamStanding(name, group)

        home = standings_by_group[group][fixture.home_team]
        away = standings_by_group[group][fixture.away_team]

        home.played += 1
        away.played += 1
        home.goals_for += score.home_score
        home.goals_against += score.away_score
        away.goals_for += score.away_score
        away.goals_against += score.home_score

        if score.home_score > score.away_score:
            home.won += 1
            away.lost += 1
        elif score.home_score < score.away_score:
            away.won += 1
            home.lost += 1
        else:
            home.drawn += 1
            away.drawn += 1

    # Sort each group with FIFA tiebreakers and accumulate warnings.
    out_standings: dict[str, list[dict]] = {}
    out_warnings: list[TieWarning] = []
    for group, teams_dict in standings_by_group.items():
        teams = [t.to_dict() for t in teams_dict.values()]
        sorted_teams, warnings = _apply_fifa_tiebreakers(
            teams,
            group_matches=matches_by_group.get(group, []),
            context="group_standings",
        )
        out_standings[group] = sorted_teams
        out_warnings.extend(warnings)

    return out_standings, out_warnings


async def get_group_positions(session: AsyncSession) -> dict[str, str]:
    """Get team positions in each group (e.g., '1A' -> 'France')."""
    standings = await get_actual_group_standings(session)
    positions: dict[str, str] = {}
    for group, teams in standings.items():
        for i, team in enumerate(teams):
            positions[f"{i + 1}{group}"] = team["team"]
    return positions


async def get_qualifying_third_place_teams(
    session: AsyncSession,
) -> list[dict]:
    """Get the 8 best third-place teams that qualify for knockout stage."""
    qualifying, _warnings = await get_qualifying_third_place_teams_with_warnings(session)
    return qualifying


async def get_qualifying_third_place_teams_with_warnings(
    session: AsyncSession,
) -> tuple[list[dict], list[TieWarning]]:
    """Same as get_qualifying_third_place_teams but also returns warnings.

    Note: head-to-head isn't applicable here because the third-placed teams
    come from different groups — they never played each other. So any tie on
    points/GD/GF goes straight to alphabetical with a warning.
    """
    standings, group_warnings = await get_actual_group_standings_with_warnings(session)

    # Collect all third-place teams.
    third_place_teams = []
    for group, teams in standings.items():
        if len(teams) >= 3:
            third_place_teams.append({**teams[2], "group": group})

    sorted_third, third_warnings = _apply_fifa_tiebreakers(
        third_place_teams,
        group_matches=None,  # H2H not applicable cross-group
        context="third_place_qualifying",
    )

    # Top 8 qualify. Note: warnings about ties that straddle the 8/9 boundary
    # are particularly important — they affect who actually advances. Callers
    # see all warnings; surfacing logic decides which to display.
    return sorted_third[:8], group_warnings + third_warnings
