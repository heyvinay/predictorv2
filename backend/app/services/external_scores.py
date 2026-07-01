"""External score fetching service.

Two providers with one job each:
  - ESPN (unofficial public JSON) paints ALL scores (pre/in-play/finished)
    with per-period enrichment for past-regulation matches. Sets
    final_authoritative=True once the summary split is successfully overlaid.
  - Football-Data.org resolves per-fixture finals (FT/ET/pens split) and
    is the bulk live fallback if ESPN errors on a tick.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta

from app.models._datetime import utc_now
from app.models.fixture import MatchStatus
from app.services.external.espn import (
    LEAGUE_SLUGS,
    EspnClient,
    EspnError,
    KnockoutSplit,
    canonical_team_name,
    competition_past_regulation,
    map_event_status,
    parse_minute,
    parse_summary_split,
)
from app.services.external.football_data import FootballDataClient, map_status


logger = logging.getLogger(__name__)


@dataclass
class ExternalScore:
    """Score data from external API."""

    external_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    status: MatchStatus
    minute: int | None = None
    home_score_et: int | None = None
    away_score_et: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None
    # Match period (soccer): 1/2 = halves, 3/4 = extra time, 5 = shootout.
    # >2 means the match went past regulation. None when provider doesn't
    # expose it (Football-Data). Used by the 90-min freeze in score_sync.
    period: int | None = None
    # True when this result carries the full FT/ET/pens split and score_sync
    # should accept it as final without routing to the FD resolution pass.
    # ESPN scoreboard events start as False; set to True after summary
    # enrichment overlays the per-period split. FD always emits True.
    final_authoritative: bool = True
    # ESPN scoreboard event id — used only to fetch that event's summary for
    # the per-period split. Not a match key. None for FD and un-enrichable events.
    espn_event_id: str | None = None
    # False when the provider had NO score values (nulls) and home/away
    # are merely the 0-coercion of missing data. Football-Data transiently
    # served FINISHED-with-null-fullTime at the WC2026 opener's final
    # whistle — writing that fabricated a 0-0 result. score_sync refuses
    # to act on score-bearing statuses when this is False.
    has_score: bool = True


class ScoreProviderBase(ABC):
    """Base class for score providers (kept abstract for testability)."""

    @abstractmethod
    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        ...

    @abstractmethod
    async def fetch_fixture_score(
        self,
        fixture_id: str,
        *,
        home_team: str | None = None,
        away_team: str | None = None,
    ) -> ExternalScore | None:
        ...


class FootballDataScoreProvider(ScoreProviderBase):
    """Live-score provider using football-data.org via the shared client."""

    # Live-only on purpose: finished matches are landed by score_sync's
    # resolution pass (per-fixture fetch by external_id), which catches a
    # final whistle that falls between polls. Do NOT rely on this filter
    # to deliver FINISHED — it never does.
    LIVE_STATUS_FILTER = "LIVE,IN_PLAY,PAUSED"

    def __init__(self, client: FootballDataClient | None = None) -> None:
        self._client = client or FootballDataClient()

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        """Fetch live scores for a competition (e.g. competition_id='WC')."""
        matches = await self._client.get_matches(competition_id, status=self.LIVE_STATUS_FILTER)
        return [self._to_external_score(m) for m in matches]

    async def fetch_fixture_score(
        self,
        fixture_id: str,
        *,
        home_team: str | None = None,
        away_team: str | None = None,
    ) -> ExternalScore | None:
        match = await self._client.get_match(fixture_id)
        if match is None:
            return None
        return self._to_external_score(match)

    @staticmethod
    def _to_external_score(match: dict) -> ExternalScore:
        score = match.get("score") or {}
        full_time = score.get("fullTime") or {}
        regular_time = score.get("regularTime") or {}
        extra_time = score.get("extratime") or score.get("extraTime") or {}
        penalty = score.get("penalty") or score.get("penalties") or {}
        home_team = match.get("homeTeam") or {}
        away_team = match.get("awayTeam") or {}

        # FD's `fullTime` is the COMBINED total for the whole match
        # (regulation + ET + pen-shootout goals), NOT the 90-min result.
        # On ET/pens KO games FD exposes the 90-min split separately via
        # `regularTime` — our `home_score` IS regulation, so prefer it.
        # On a normal 90-min match `regularTime` is absent and `fullTime`
        # IS the 90-min score, so the fallback handles group matches too.
        reg_home = regular_time.get("home")
        reg_away = regular_time.get("away")
        if reg_home is None:
            reg_home = full_time.get("home")
            reg_away = full_time.get("away")

        # Our `home_score_et` is the cumulative score AFTER extra time,
        # but FD's `extraTime` is the ET-PERIOD delta only — add to the
        # regulation total to land the right cumulative. Only emit a
        # cumulative when FD actually gave us both halves of the split.
        cumulative_et_home: int | None = None
        cumulative_et_away: int | None = None
        if (
            regular_time.get("home") is not None
            and extra_time.get("home") is not None
        ):
            cumulative_et_home = regular_time["home"] + extra_time["home"]
            cumulative_et_away = regular_time["away"] + extra_time["away"]

        # Shootout reconstruction: FD's `penalty` field has been observed
        # to misreport the shootout result for the 2026 WC R32 — Germany
        # vs Paraguay served `penalties: 4-4, winner: None` and
        # Netherlands vs Morocco served `penalties: 3-3, winner: None`
        # despite duration=PENALTY_SHOOTOUT in both cases. BUT FD's
        # `fullTime` is the COMBINED total (regulation + ET + shootout
        # goals), so the shootout legs can be recovered exactly as
        # `fullTime − (regularTime + extraTime)`. Use that as the
        # primary source when the match was decided by pens; fall back
        # to FD's reported `penalty` field if derivation isn't possible
        # (e.g. fullTime or regularTime missing).
        duration = score.get("duration") or ""
        pen_home = penalty.get("home")
        pen_away = penalty.get("away")
        if duration == "PENALTY_SHOOTOUT":
            ft_home = full_time.get("home")
            ft_away = full_time.get("away")
            et_delta_home = extra_time.get("home") or 0
            et_delta_away = extra_time.get("away") or 0
            if (
                ft_home is not None
                and ft_away is not None
                and regular_time.get("home") is not None
            ):
                derived_home = ft_home - regular_time["home"] - et_delta_home
                derived_away = ft_away - regular_time["away"] - et_delta_away
                # Guard against bad arithmetic (negative legs, equal legs
                # — a pen shootout NEVER ends level): fall through to FD's
                # reported field if the math doesn't yield a winner.
                if derived_home >= 0 and derived_away >= 0 and derived_home != derived_away:
                    pen_home = derived_home
                    pen_away = derived_away

        # Shootout-decided matches need a resolvable winner. If neither
        # derivation nor the raw `penalty` field gave us unequal legs,
        # there's no way to advance whoever won — flag has_score=False so
        # score_sync can route to alternate resolution.
        shootout_resolved = (
            pen_home is not None
            and pen_away is not None
            and pen_home != pen_away
        )
        shootout_payload_usable = (
            duration != "PENALTY_SHOOTOUT" or shootout_resolved
        )

        return ExternalScore(
            external_id=str(match.get("id", "")),
            home_team=home_team.get("name") or "",
            away_team=away_team.get("name") or "",
            home_score=reg_home if reg_home is not None else 0,
            away_score=reg_away if reg_away is not None else 0,
            status=map_status(match.get("status", "")),
            minute=match.get("minute"),
            home_score_et=cumulative_et_home,
            away_score_et=cumulative_et_away,
            home_penalties=pen_home,
            away_penalties=pen_away,
            # Null regulation score means FD hasn't published a result —
            # observed alongside status FINISHED at the WC2026 opener.
            # 0-coerced values must not be mistaken for a real 0-0.
            # Pen-shootout matches additionally need a resolvable winner,
            # else the fallback chain takes over (see comment above).
            has_score=(
                reg_home is not None
                and reg_away is not None
                and shootout_payload_usable
            ),
        )


class EspnScoreProvider(ScoreProviderBase):
    """ESPN scoreboard + summary enrichment for knockout splits.

    Emits ALL events (pre/in-play/finished) with final_authoritative=False.
    For matches past regulation, concurrently fetches the per-event summary
    to overlay the authoritative per-period split and set final_authoritative=True.
    score_sync uses final_authoritative to decide whether to route to the
    Football-Data resolution pass (False → route, True → accept as final).

    ExternalScore.external_id is left blank — ESPN event ids don't match the
    Football-Data ids stored on fixtures. Matching goes through (home_team,
    away_team) name fallback with ESPN→canonical aliases.
    """

    def __init__(self, client: EspnClient | None = None) -> None:
        self._client = client or EspnClient()

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        slug = LEAGUE_SLUGS.get(competition_id, "fifa.world")
        now = utc_now()
        dates = (
            f"{(now - timedelta(days=1)).strftime('%Y%m%d')}"
            f"-{(now + timedelta(days=1)).strftime('%Y%m%d')}"
        )
        events = await self._client.get_scoreboard(slug, dates)
        scores: list[ExternalScore] = []
        to_enrich: list[ExternalScore] = []

        for event in events:
            ext = self._to_external_score(event)
            if ext is None:
                continue
            scores.append(ext)
            # Enrich past-regulation events so score_sync gets the authoritative split
            try:
                comp = event["competitions"][0]
            except (KeyError, IndexError, TypeError):
                comp = {}
            if ext.espn_event_id and competition_past_regulation(comp):
                to_enrich.append(ext)
            else:
                # Regulation-time finish: ESPN's FT score is authoritative — no
                # ET/pens split to fetch. Mark it so score_sync doesn't defer to
                # FD resolution (which may be 403 on free-tier subscriptions).
                stype = comp.get("status", {}).get("type", {})
                if stype.get("state") == "post" and stype.get("completed"):
                    ext.final_authoritative = True

        if to_enrich:
            await self._enrich_knockout_splits(slug, to_enrich)

        return scores

    async def _enrich_knockout_splits(
        self, slug: str, scores: list[ExternalScore]
    ) -> None:
        """Overlay the authoritative per-period split onto each past-regulation score.

        Fetches are concurrent. Any failure (HTTP error, malformed JSON, inconsistent
        linescores, tied pens) leaves the base score untouched and logs a warning —
        never breaks the tick.
        """

        async def overlay(ext: ExternalScore) -> None:
            try:
                summary = await self._client.get_summary(slug, ext.espn_event_id)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "espn summary fetch failed for event %s (%s vs %s): %s",
                    ext.espn_event_id,
                    ext.home_team,
                    ext.away_team,
                    exc,
                )
                return
            split = parse_summary_split(summary)
            if split is None:
                logger.warning(
                    "espn summary split unavailable/inconsistent for %s vs %s "
                    "(event %s) — leaving base score for score_sync to handle",
                    ext.home_team,
                    ext.away_team,
                    ext.espn_event_id,
                )
                return
            ext.home_score = split.home_reg
            ext.away_score = split.away_reg
            ext.home_score_et = split.home_et
            ext.away_score_et = split.away_et
            ext.home_penalties = split.home_pen
            ext.away_penalties = split.away_pen
            ext.final_authoritative = True

        await asyncio.gather(*(overlay(s) for s in scores))

    async def fetch_fixture_score(
        self,
        fixture_id: str,
        *,
        home_team: str | None = None,
        away_team: str | None = None,
    ) -> ExternalScore | None:
        # ESPN can't resolve by Football-Data external_id. Enrichment happens
        # in the live loop; per-fixture resolution goes to Football-Data only.
        return None

    @staticmethod
    def _to_external_score(event: dict) -> ExternalScore | None:
        try:
            comp = event["competitions"][0]
            status = map_event_status(comp.get("status", {}).get("type", {}))
            if status is None:
                return None  # abandoned/postponed — skip
            sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            home, away = sides.get("home"), sides.get("away")
            if not home or not away:
                return None
            shootout_home = home.get("shootoutScore")
            shootout_away = away.get("shootoutScore")
            raw_period = comp.get("status", {}).get("period")
            period = int(raw_period) if isinstance(raw_period, (int, float)) else None
            return ExternalScore(
                external_id="",
                home_team=canonical_team_name(home.get("team", {}).get("displayName", "")),
                away_team=canonical_team_name(away.get("team", {}).get("displayName", "")),
                home_score=int(home.get("score") or 0),
                away_score=int(away.get("score") or 0),
                status=status,
                minute=parse_minute(comp.get("status", {}).get("displayClock")),
                period=period,
                home_penalties=int(shootout_home) if shootout_home is not None else None,
                away_penalties=int(shootout_away) if shootout_away is not None else None,
                final_authoritative=False,
                espn_event_id=str(event.get("id")) if event.get("id") is not None else None,
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return None


class FallbackScoreProvider(ScoreProviderBase):
    """ESPN-first live score chain with Football-Data as the sole per-fixture resolver.

    Live scores try each provider in order, falling through on exceptions.
    Per-fixture resolution goes to Football-Data only — ESPN can't resolve by
    Football-Data external_id, and the summary enrichment loop handles all
    knockout splits during the live phase.
    """

    def __init__(
        self,
        live_providers: list[ScoreProviderBase],
        resolver: ScoreProviderBase,
    ) -> None:
        self._live_providers = live_providers
        self._resolver = resolver

    async def fetch_live_scores(self, competition_id: str) -> list[ExternalScore]:
        last_exc: Exception | None = None
        for provider in self._live_providers:
            try:
                return await provider.fetch_live_scores(competition_id)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "score provider %s failed, trying next: %s",
                    type(provider).__name__,
                    exc,
                )
        raise last_exc if last_exc else RuntimeError("no live score providers configured")

    async def fetch_fixture_score(
        self,
        fixture_id: str,
        *,
        home_team: str | None = None,
        away_team: str | None = None,
    ) -> ExternalScore | None:
        return await self._resolver.fetch_fixture_score(
            fixture_id, home_team=home_team, away_team=away_team
        )


def get_score_provider() -> ScoreProviderBase:
    """ESPN paints live scores and enriches knockout splits via summary endpoint.
    Football-Data resolves per-fixture finals (FT/ET/pens split) and is the
    bulk live fallback if ESPN errors.
    """
    football_data = FootballDataScoreProvider()
    return FallbackScoreProvider(
        live_providers=[EspnScoreProvider(), football_data],
        resolver=football_data,
    )
