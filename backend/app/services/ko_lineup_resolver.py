"""Read-time resolver for downstream KO slot placeholders (v2.184.x).

Extends the v2.183.x `r32_resolver` design philosophy ("DB stays untouched;
resolve at read time; Football-Data eventually wins when it lands") from
R32 only to the whole knockout chain: R32 → R16 → QF → SF → Final.

The gap this closes: when an R32 match finishes, the system already knows
who advanced (the scoring engine credits the winner internally via
`scoring.get_actual_advancement`), but the R16 fixture rows still hold
`slot:round_of_16:NNN:home` placeholders. /api/fixtures and
/api/predictions/matches/{id}/ko-detail then surface those slot strings,
which the frontend's `teamName.ts` renders as "TBD" — for hours, until
Football-Data ingests FIFA's confirmed lineup and someone re-runs
fixture_sync. This resolver bridges that lag by walking the bracket:

  • R32 fixture → defer to R32Resolver (group-standings-based)
  • R16 fixture → look up its two source R32 matches, check FINISHED, pick winners
  • QF fixture → recurse one level up; needs both feeding R16s finished
  • SF, Final → same recursion

Caching: resolved (home, away) per match_number within a single
resolver instance — recursion never re-walks the same subtree.

Source maps live in `bracket_seeding.py` (mirrored from frontend
`bracketConfig.ts`). Match numbers per FIFA 2026 schedule: R32 = 73-88,
R16 = 89-96, QF = 97-100, SF = 101-102, F = 104. Third-place playoff
(M103) is intentionally absent — unscored stage per the CLAUDE.md invariant.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.services.bracket_seeding import (
    EXT_ID_TO_MATCH_NUMBER,
    FINAL_SOURCES,
    QUARTER_FINAL_SOURCES,
    ROUND_OF_16_SOURCES,
    SEMI_FINAL_SOURCES,
    STAGE_FIRST_MATCH_NUMBER,
    is_downstream_ko_slot_placeholder,
    is_r32_slot_placeholder,
)
from app.services.r32_resolver import (
    R32Resolver,
    build_r32_resolver,
    resolve_r32_pair,
)

log = logging.getLogger(__name__)


# Aggregated source dict: any KO match's match_number → (home_source, away_source)
# Built once at module load — pure data, no mutation.
_ALL_KO_SOURCES: dict[int, tuple[dict, dict]] = {
    **ROUND_OF_16_SOURCES,
    **QUARTER_FINAL_SOURCES,
    **SEMI_FINAL_SOURCES,
    **FINAL_SOURCES,
}


class KoLineupResolver:
    """Bundled state for resolving slot placeholders across all KO stages.

    Construction loads all KO fixtures + their Scores once; the resolve()
    method then walks the bracket in memory. Pure read — never writes
    back to the DB.
    """

    def __init__(
        self,
        *,
        fixtures_by_match: dict[int, Fixture],
        fixtures_by_id: dict[uuid.UUID, Fixture],
        scores_by_fixture_id: dict[uuid.UUID, Score],
        r32_resolver: R32Resolver,
    ):
        self._fixtures_by_match = fixtures_by_match
        self._fixtures_by_id = fixtures_by_id
        self._scores = scores_by_fixture_id
        self._r32_resolver = r32_resolver
        self._cache: dict[int, tuple[Optional[str], Optional[str]]] = {}
        # Reverse lookup: fixture.id → match_number, populated on demand.
        self._match_num_by_fixture_id: dict[uuid.UUID, int] = {
            fix.id: num for num, fix in fixtures_by_match.items()
        }

    # ── Public API ────────────────────────────────────────────────────

    def resolve(self, fixture: Fixture) -> tuple[Optional[str], Optional[str]]:
        """Resolve a fixture's (home_team, away_team) to real team names
        where possible. Returns the originals (still TBD/slot strings)
        for any side whose upstream match isn't FINISHED yet.
        """
        match_num = self._match_num_by_fixture_id.get(fixture.id)
        if match_num is None:
            # Not in our recognised KO set (e.g. third_place fixture, or
            # data drift). Best-effort: try the R32 resolver on the
            # current strings, otherwise pass through.
            home, away = resolve_r32_pair(
                self._r32_resolver, fixture.home_team, fixture.away_team
            )
            return home, away

        return self._resolve_by_match_num(
            match_num,
            fallback_home=fixture.home_team,
            fallback_away=fixture.away_team,
        )

    # ── Internal: recursive walk ──────────────────────────────────────

    def _resolve_by_match_num(
        self,
        match_num: int,
        *,
        fallback_home: Optional[str],
        fallback_away: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        cached = self._cache.get(match_num)
        if cached is not None:
            return cached

        # R32 (matches 73-88) — base case. Defer to R32Resolver which
        # reads group standings.
        if 73 <= match_num <= 88:
            fix = self._fixtures_by_match.get(match_num)
            if fix is None:
                return fallback_home, fallback_away
            home, away = resolve_r32_pair(
                self._r32_resolver, fix.home_team, fix.away_team
            )
            result = (home, away)
            self._cache[match_num] = result
            return result

        # Downstream stages — walk sources.
        sources = _ALL_KO_SOURCES.get(match_num)
        if sources is None:
            return fallback_home, fallback_away
        home_src, away_src = sources
        home = self._resolve_source(home_src) or fallback_home
        away = self._resolve_source(away_src) or fallback_away
        result = (home, away)
        self._cache[match_num] = result
        return result

    def _resolve_source(self, source: dict) -> Optional[str]:
        """Resolve a single source descriptor to a team name, or None
        if the upstream match isn't FINISHED yet.
        """
        if source.get("type") != "winner":
            # Unknown source type (e.g. "loser" for the third_place
            # playoff). We don't handle it — caller falls back.
            return None
        src_match = source.get("match_number")
        if src_match is None:
            return None
        src_fix = self._fixtures_by_match.get(src_match)
        if src_fix is None:
            return None

        # Recursive: resolve the source match's own teams first so we
        # know what "winner of source" means when we read the score.
        src_home, src_away = self._resolve_by_match_num(
            src_match,
            fallback_home=src_fix.home_team,
            fallback_away=src_fix.away_team,
        )

        # Winner determination — needs the match FINISHED with a Score.
        if src_fix.status != MatchStatus.FINISHED:
            return None
        score = self._scores.get(src_fix.id)
        if score is None:
            return None
        # KO matches force ET / pens for draws, so outcome is always "1"
        # or "2" in well-formed data. Defensive: anything else returns None.
        if score.outcome == "1":
            return src_home
        if score.outcome == "2":
            return src_away
        return None


# ── Factory ──────────────────────────────────────────────────────────


async def build_ko_lineup_resolver(session: AsyncSession) -> KoLineupResolver:
    """Build a resolver from the DB. Call once per request that needs
    to surface knockout team lineups across all stages.

    Loads all knockout fixtures (every stage except `group` and `third_place`)
    plus their Score rows in a single query. Builds the match_number index
    using `EXT_ID_TO_MATCH_NUMBER` for R32 and kickoff-sorted ordering for
    R16+ (FIFA publishes R16/QF/SF/F matches in chronological order, so
    sorting by kickoff within each stage yields M89, M90, ... in sequence).
    """
    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(Fixture.stage.in_(
            ("round_of_32", "round_of_16", "quarter_final", "semi_final", "final")
        ))
    )
    rows = result.all()

    fixtures_by_match: dict[int, Fixture] = {}
    fixtures_by_id: dict[uuid.UUID, Fixture] = {}
    scores_by_fixture_id: dict[uuid.UUID, Score] = {}
    by_stage: dict[str, list[Fixture]] = {}

    for fix, score in rows:
        if fix.id in fixtures_by_id:
            # Multiple Score rows can exist if upstream code ever wrote
            # duplicates; keep the first. Defensive only — schema has
            # a uniqueness constraint.
            continue
        fixtures_by_id[fix.id] = fix
        if score is not None:
            scores_by_fixture_id[fix.id] = score
        by_stage.setdefault(fix.stage, []).append(fix)

    # R32: ext_id → match_number is hand-verified (see EXT_ID_TO_MATCH_NUMBER
    # docstring for the reasoning — Football-Data IDs do NOT follow FIFA's
    # match-number order).
    for fix in by_stage.get("round_of_32", []):
        ext_id = fix.external_id
        if ext_id and ext_id in EXT_ID_TO_MATCH_NUMBER:
            fixtures_by_match[EXT_ID_TO_MATCH_NUMBER[ext_id]] = fix

    # R16/QF/SF/F: kickoff-sorted index + stage base match number.
    # This is the same trust assumption FIFA makes in its own scheduling
    # — Match 89 kicks off before Match 90, etc. If FIFA ever schedules
    # a later-numbered match earlier (rare), the resolver would mis-pair;
    # a regression test pins this against the live competition schedule.
    for stage, base in STAGE_FIRST_MATCH_NUMBER.items():
        sorted_fixtures = sorted(by_stage.get(stage, []), key=lambda f: f.kickoff)
        for i, fix in enumerate(sorted_fixtures):
            fixtures_by_match[base + i] = fix

    r32_resolver = await build_r32_resolver(session)
    return KoLineupResolver(
        fixtures_by_match=fixtures_by_match,
        fixtures_by_id=fixtures_by_id,
        scores_by_fixture_id=scores_by_fixture_id,
        r32_resolver=r32_resolver,
    )


def resolve_ko_pair(
    resolver: KoLineupResolver,
    fixture: Fixture,
) -> tuple[Optional[str], Optional[str]]:
    """Apply the resolver to one fixture and return resolved (home, away).

    Pure function. Caller decides whether to surface the resolved values
    or fall back to the originals.
    """
    return resolver.resolve(fixture)


def is_any_ko_slot_placeholder(name: Optional[str]) -> bool:
    """True if a string is any KO slot placeholder (R32 or downstream)."""
    return is_r32_slot_placeholder(name) or is_downstream_ko_slot_placeholder(name)
