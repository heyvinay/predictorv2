"""Knockout match-detail service.

Builds the bundled response for /api/predictions/matches/{id}/ko-detail.
One service entry-point, one round-trip's worth of aggregations, fed by a
small set of focused queries so the endpoint stays fast.

Conventions (CLAUDE.md):
- PHASE_1 filter applied throughout (Phase 2 is dormant — joining
  prediction_entry_phases without this filter would double-count).
- Stage values are SINGULAR (`round_of_32`, `quarter_final`, etc.) —
  match Fixture.stage and the YAML scoring.advancement keys.
- "Eligible" entries = PHASE_1 SUBMITTED, not disabled, not withdrawn.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.user import User
from app.schemas.ko_match_detail import (
    KoCohortBreakdown,
    KoExposedEntry,
    KoImplications,
    KoImplicationSide,
    KoMatchDetailResponse,
    KoMostExposed,
    KoPoolRollEntry,
    KoPoolSplit,
    KoPoolSplitSide,
)
from app.services.scoring import get_scoring_config


# Knockout stage ordering — matches Fixture.stage / TeamPrediction.stage
# and the YAML scoring.advancement keys. `third_place` is intentionally
# absent (unscored — see the CLAUDE.md invariant).
_KNOCKOUT_STAGES: list[str] = [
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
    "winner",
]


def _cohort_of(employer: str | None) -> str:
    """Map User.employer onto the leaderboard's cohort buckets."""
    if employer == "atlas":
        return "atlas"
    if employer == "jmfa":
        return "jmfa"
    return "guests"


def _advancement_points(stage: str) -> int:
    """Look up the YAML scoring value for a stage, with a safe default.

    Pulled at request time rather than module-import time so tests that
    point at a different config get the right values.
    """
    cfg = get_scoring_config()
    advancement = cfg.get("advancement", {}) if isinstance(cfg, dict) else {}
    value = advancement.get(stage)
    return int(value) if isinstance(value, (int, float)) else 0


def _pct(part: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100 * part / total)


async def get_ko_match_detail(
    session: AsyncSession,
    fixture: Fixture,
) -> KoMatchDetailResponse:
    """Build the knockout match-detail bundle for one fixture.

    Caller is responsible for the blind-pool / authorisation gate — this
    function assumes the data is allowed to be returned.
    """
    home_team = fixture.home_team
    away_team = fixture.away_team
    sides = (home_team, away_team)

    # ── Query 1: eligible entries + their cohort + leaderboard rank ──
    # One row per eligible entry. Includes user.employer for the cohort
    # split. PHASE_1 SUBMITTED, not disabled, not withdrawn.
    elig_rows = (
        await session.execute(
            select(
                PredictionEntry.id,
                PredictionEntry.reference,
                PredictionEntry.display_name,
                User.name,
                User.email,
                User.employer,
            )
            .join(User, PredictionEntry.user_id == User.id)
            .join(
                PredictionEntryPhase,
                (PredictionEntryPhase.entry_id == PredictionEntry.id)
                & (PredictionEntryPhase.phase == PredictionPhase.PHASE_1),
            )
            .where(PredictionEntry.withdrawn_at.is_(None))
            .where(PredictionEntry.is_disabled.is_(False))
            .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
        )
    ).all()

    eligible_ids: set[uuid.UUID] = set()
    entry_meta: dict[uuid.UUID, dict] = {}
    for entry_id, ref, display_name, user_name, user_email, employer in elig_rows:
        eligible_ids.add(entry_id)
        entry_meta[entry_id] = {
            "reference": ref,
            "entry_name": display_name,
            "user_name": user_name or (user_email.split("@")[0] if user_email else "Unknown"),
            "cohort": _cohort_of(employer),
        }

    # ── Cached leaderboard for rank lookup ──
    from app.services.leaderboard import calculate_leaderboard

    leaderboard = await calculate_leaderboard(session, phase=None)
    rank_by_entry: dict[uuid.UUID, int] = {
        e.entry_id: e.position for e in leaderboard.entries
    }

    # ── Query 2: all TeamPrediction rows for either side, any knockout stage ──
    # One query feeds pool split, implications, AND most-exposed. We slice
    # in Python below — cheaper than four separate aggregations and the
    # row count is bounded (≤ 6 stages × 2 teams × ~200 entries).
    tp_rows: list = []
    if eligible_ids:
        tp_rows = (
            await session.execute(
                select(
                    TeamPrediction.entry_id,
                    TeamPrediction.team,
                    TeamPrediction.stage,
                )
                .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
                .where(TeamPrediction.team.in_(sides))
                .where(TeamPrediction.stage.in_(_KNOCKOUT_STAGES))
                .where(TeamPrediction.entry_id.in_(eligible_ids))
            )
        ).all()

    # Build a {(team, stage): set(entry_id)} index from the rows.
    picks_by_team_stage: dict[tuple[str, str], set[uuid.UUID]] = defaultdict(set)
    # Also a {entry_id: {team: set(stage)}} index for most-exposed.
    stages_by_entry_team: dict[uuid.UUID, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for entry_id, team, stage in tp_rows:
        picks_by_team_stage[(team, stage)].add(entry_id)
        stages_by_entry_team[entry_id][team].add(stage)

    # ── Pool split — who picked which side to advance from THIS fixture ──
    def build_split_side(team: str) -> KoPoolSplitSide:
        pick_ids = picks_by_team_stage.get((team, fixture.stage), set())
        cohorts = KoCohortBreakdown(atlas=0, jmfa=0, guests=0)
        for eid in pick_ids:
            meta = entry_meta.get(eid)
            if not meta:
                continue
            bucket = meta["cohort"]
            if bucket == "atlas":
                cohorts.atlas += 1
            elif bucket == "jmfa":
                cohorts.jmfa += 1
            else:
                cohorts.guests += 1
        return KoPoolSplitSide(
            team=team,
            count=len(pick_ids),
            pct=_pct(len(pick_ids), len(eligible_ids)),
            cohorts=cohorts,
        )

    pool_split = KoPoolSplit(
        total=len(eligible_ids),
        home=build_split_side(home_team),
        away=build_split_side(away_team),
    )

    # ── Implications — alive-at-stage counts per side ──
    def build_implication_side(team: str) -> KoImplicationSide:
        def at(stage: str) -> int:
            return len(picks_by_team_stage.get((team, stage), set()))

        return KoImplicationSide(
            team=team,
            r32_outcome=at(fixture.stage),
            alive_r16=at("round_of_16"),
            alive_qf=at("quarter_final"),
            alive_sf=at("semi_final"),
            alive_final=at("final"),
            alive_winner=at("winner"),
        )

    implications = KoImplications(
        home=build_implication_side(home_team),
        away=build_implication_side(away_team),
    )

    # ── Most exposed — top 5 by cumulative points-at-stake per side ──
    def build_exposed_side(team: str, limit: int = 5) -> list[KoExposedEntry]:
        candidates: list[KoExposedEntry] = []
        for entry_id, by_team in stages_by_entry_team.items():
            stages = by_team.get(team, set())
            if not stages:
                continue
            stage_list = [s for s in _KNOCKOUT_STAGES if s in stages]
            points = sum(_advancement_points(s) for s in stage_list)
            meta = entry_meta.get(entry_id)
            if not meta:
                continue
            candidates.append(
                KoExposedEntry(
                    entry_id=entry_id,
                    user_name=meta["user_name"],
                    entry_reference=meta["reference"],
                    entry_name=meta["entry_name"],
                    rank=rank_by_entry.get(entry_id),
                    points_at_stake=points,
                    stages_at_stake=stage_list,
                )
            )
        # Sort by points desc, then by rank asc (best-ranked entry first
        # when tied — gives a stable, intuitive ordering for the UI).
        candidates.sort(
            key=lambda c: (-c.points_at_stake, c.rank if c.rank is not None else 10**9)
        )
        return candidates[:limit]

    most_exposed = KoMostExposed(
        home=build_exposed_side(home_team),
        away=build_exposed_side(away_team),
    )

    # ── Pool roll — full list with each entry's R32 pick ──
    # An entry might have neither team in their picks (incomplete bracket
    # corner case); we skip those rather than render an empty pick.
    pool_roll: list[KoPoolRollEntry] = []
    for entry_id, meta in entry_meta.items():
        pick: str | None = None
        for team in sides:
            if entry_id in picks_by_team_stage.get((team, fixture.stage), set()):
                pick = team
                break
        if not pick:
            continue
        pool_roll.append(
            KoPoolRollEntry(
                entry_id=entry_id,
                user_name=meta["user_name"],
                entry_reference=meta["reference"],
                entry_name=meta["entry_name"],
                pick=pick,
                rank=rank_by_entry.get(entry_id),
            )
        )
    # Stable sort: rank ascending, unranked last.
    pool_roll.sort(key=lambda r: (r.rank if r.rank is not None else 10**9, r.entry_name))

    return KoMatchDetailResponse(
        fixture_id=fixture.id,
        home_team=home_team,
        away_team=away_team,
        stage=fixture.stage,
        pool_split=pool_split,
        implications=implications,
        most_exposed=most_exposed,
        pool_roll=pool_roll,
    )
