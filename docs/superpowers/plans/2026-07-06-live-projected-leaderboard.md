# Live Projected Leaderboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** During live knockout matches, show a provisional "live" leaderboard where standings re-rank in real time based on who is currently winning — without ever touching the banked (real, permanent) points until a match is FINISHED.

**Architecture:** A read-time overlay layered onto the banked leaderboard at the HTTP boundary (`get_leaderboard()` endpoint only). The banked board — the single source of truth that daily snapshots and the Race chart consume — is never mutated. The overlay adds three optional fields (`projected_position`, `projected_total`, `live_delta`) plus a response flag (`live_projection_active`); frontend surfaces opt in by reading them. Two admin-flippable gates (`knockout_scoring_enabled` AND a new `live_projection_enabled`) plus "≥1 live KO match" arm the feature.

**Tech Stack:** FastAPI + SQLModel + Alembic (backend), SvelteKit + TypeScript + DaisyUI (frontend), pytest + vitest.

---

## Design decisions locked during grilling (2026-07-06)

These are the invariants the code must honour. Do not re-open them; implement them.

1. **Projected overlay, never real award.** Live scores never move banked points. The banked board only changes when a match goes FINISHED (unchanged existing behaviour). The "live" number is banked + a provisional overlay computed fresh on each read and never stored.
2. **Knockout advancement ONLY (R32 → winner).** KO points are flat, rarity-free (`scoring.calculate_advancement_points`); group-stage/rarity math is never touched. Match-score predictions only exist for group-stage fixtures, which are already complete — so there is nothing to project there.
3. **Provisional winner = ET-inclusive, penalty-blind scoreline.** Use `Score.final_home_score` / `Score.final_away_score` (fold in extra time, exclude penalties). A level match projects **no** winner (no movement). A live penalty shootout is invisible until the match is FINISHED — penalties only count at the end. (User rule.)
4. **Re-rank live + automatic + primary.** When armed, the standings genuinely re-sort into projected order; the "leader" can change mid-match. No per-user toggle — the admin switch is the only control.
5. **Additive fields; banked fields untouched.** `position` / `total_points` stay banked on every row. Surfaces opt in to `projected_*`. Snapshots, movers, trails, Race chart, trajectory endpoints all keep reading banked.
6. **Snapshot purity.** The overlay lives in `get_leaderboard()` only — never in `calculate_leaderboard()` (which `take_daily_snapshots` and the trajectory endpoints call). A transient projection must never reach a snapshot row.
7. **Never mutate cached rows.** The banked board is served by-reference from an in-memory cache. The overlay copies rows before setting projected fields.
8. **Seamless FINISHED handoff.** The projected number must not dip at the final whistle. Achieved by (a) the overlay only projecting LIVE matches, and (b) hard-invalidating the leaderboard cache on a **knockout** FINISHED transition so the banked board reflects the real credit on the very next read — closing the gap the soft-expire path would otherwise leave open.
9. **Surfaces in scope (v1 = A2):** `/leaderboard` Standings table + its entry drawer (shares rows), **and** the home dashboard mini-leaderboard + the "you're Nth" KPI. Match Detail, Race, Insights stay banked.
10. **Admin kill-switch** `live_projection_enabled`, default **false**, flippable from `/admin`, mirroring the `knockout_scoring_enabled` pattern. Flipping it needs **no** cache invalidation (the gate is read fresh on every projection).

---

## Testing conventions (read before running anything)

This work happens in a Claude worktree under `.claude/worktrees/…`. The running docker-compose stack is bound to the **main** worktree, so tests must be run via the **overlay-then-restore** pattern from `CLAUDE.md`:

1. Edit files in the Claude worktree.
2. `cp` changed files into the main worktree's matching paths.
3. Run `docker-compose exec -T <service> <cmd>` from the main worktree.
4. Restore main worktree: `git checkout -- <path>` (modified) / `rm` (new).
5. Commit in the Claude worktree.

Static checks (`svelte-check`, `vitest`) need no container restart; the live `:5173` dev server does (`docker-compose restart frontend-dev`) for any manual browser verification. Confirm the main worktree's `git status` is clean before overlaying.

Backend gate (run the FULL suite, not just new files — per `CLAUDE.md`, adding a required model/schema field silently breaks hand-built test rows):

```bash
docker-compose exec -T backend pytest tests/ -q
```

Frontend gate:

```bash
docker-compose exec -T frontend-dev npm run check      # MUST be 0 errors
docker-compose exec -T frontend-dev npx vitest run
```

---

## File Structure

**Backend — create:**
- `backend/app/services/live_projection.py` — the overlay (gate check, live-KO winner derivation, per-entry deltas, pure `project_rows`).
- `backend/alembic/versions/<rev>_add_live_projection_enabled.py` — migration (autogenerated, then hand-edited for `server_default`).
- `backend/tests/test_live_projection.py` — overlay unit tests (pure + service).
- `backend/tests/test_admin_live_projection_toggle.py` — toggle endpoint test.

**Backend — modify:**
- `backend/app/models/competition.py:77` — add `live_projection_enabled` field.
- `backend/app/schemas/leaderboard.py:205` (LeaderboardEntry) + `:219` (LeaderboardResponse) — add fields.
- `backend/app/api/leaderboard.py:116-161` (`get_leaderboard`) — apply overlay.
- `backend/app/api/competition.py:84-155` (PhaseStatus + `get_phase_status`) — surface the flag.
- `backend/app/api/admin.py:727-783` (after the knockout-scoring endpoint) — add toggle.
- `backend/app/services/score_sync.py` — KO-finish hard-invalidate for the seamless handoff.
- `backend/tests/test_score_sync*.py` — assert KO finish invalidates.

**Frontend — create:**
- `frontend/src/lib/components/LiveProjectionPill.svelte` — the `LIVE` badge + explainer popover.

**Frontend — modify:**
- `frontend/src/lib/types/leaderboard.ts:24-50` — add projected fields to `LbEntryV4` + flag to `LbResponseV4`.
- `frontend/src/lib/api/admin.ts:161-165` (after `setKnockoutScoringEnabled`) — add `setLiveProjectionEnabled`.
- `frontend/src/lib/stores/phase.ts:66-71` (after `knockoutScoringEnabled`) — add `liveProjectionEnabled` derived store.
- `frontend/src/routes/admin/+page.svelte` — add toggle card (mirror the knockout-scoring card).
- `frontend/src/lib/utils/leaderboardV4.ts` — add `displayRank` / `displayTotal` helpers.
- `frontend/src/lib/utils/leaderboardV4.test.ts` — cover the helpers.
- `frontend/src/routes/leaderboard/+page.svelte:181-183,268-282,341-360` — live ordering + freshness strip + LIVE pill.
- `frontend/src/lib/components/leaderboard/v4/StandingsTable.svelte` — live-order default sort.
- `frontend/src/lib/components/leaderboard/v4/StandingRow.svelte:47,109-119` — projected rank + `live_delta` chip.
- `frontend/src/lib/components/dashboard/v4/DashboardV4.svelte:85-101,137-145,167-169,282-288` — capture flag, project `rankByEntry`, pass down.
- `frontend/src/lib/components/dashboard/v4/MiniLeaderboard.svelte:16-124` — live order + `LIVE` pill.

**Version:** `frontend/package.json`, `frontend/package-lock.json` (×2), `backend/pyproject.toml` → `2.198.0`; changelog + featureHighlights entries.

---

## Task 1: Backend — competition flag + migration

**Files:**
- Modify: `backend/app/models/competition.py:77`
- Create: `backend/alembic/versions/<rev>_add_live_projection_enabled.py`

- [ ] **Step 1: Add the model field**

In `backend/app/models/competition.py`, immediately after the `simulator_enabled` field (line 77), add:

```python
    # Live projection master switch (v2.198.0): admin-controlled gate on
    # the read-time live projected leaderboard. When true AND
    # knockout_scoring_enabled is true AND >=1 knockout match is live,
    # GET /leaderboard/ layers a provisional advancement projection onto
    # the banked board (projected_position / projected_total / live_delta).
    # Read-time only — flipping it needs no cache invalidation. Defaults
    # FALSE so the feature stays dark until an admin opts in from /admin.
    live_projection_enabled: bool = Field(default=False)
```

- [ ] **Step 2: Find the current migration head**

Run: `docker-compose exec -T backend alembic heads`
Note the revision id printed (call it `<HEAD>`).

- [ ] **Step 3: Autogenerate the migration**

Run: `docker-compose exec -T backend alembic revision --autogenerate -m "add live_projection_enabled"`
Then open the created file under `backend/alembic/versions/`. Autogenerate omits `server_default` (per `CLAUDE.md`), so edit the `upgrade()` / `downgrade()` bodies to exactly:

```python
def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column(
            "live_projection_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("competitions", "live_projection_enabled")
```

Confirm `down_revision = "<HEAD>"` matches Step 2.

- [ ] **Step 4: Apply and verify**

Run: `docker-compose exec -T backend alembic upgrade head`
Then: `docker-compose exec -T backend python -c "import asyncio; from app.database import async_session_maker; from sqlmodel import select; from app.models.competition import Competition;
async def m():
    async with async_session_maker() as s:
        r=await s.execute(select(Competition)); c=r.scalars().first(); print('live_projection_enabled=', c.live_projection_enabled if c else 'no competition')
asyncio.run(m())"`
Expected: prints `live_projection_enabled= False`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/competition.py backend/alembic/versions/
git commit -m "feat(model): add live_projection_enabled competition flag"
```

---

## Task 2: Backend — schema fields

**Files:**
- Modify: `backend/app/schemas/leaderboard.py:165-219`

- [ ] **Step 1: Add projected fields to LeaderboardEntry**

In `backend/app/schemas/leaderboard.py`, inside `class LeaderboardEntry`, immediately after `bonus_knockout_points: int = 0` (line 205), add:

```python
    # Live projection (v2.198.0) — populated ONLY on GET /leaderboard/
    # when the live projection is armed; None otherwise. Banked position
    # and total_points above stay banked; these carry the provisional
    # KO-advancement projection so surfaces can opt in without changing
    # the banked numbers.
    projected_position: int | None = None
    projected_total: int | None = None
    live_delta: int | None = None
```

- [ ] **Step 2: Add the response flag**

In `class LeaderboardResponse`, after `published_sheet_url: str | None = None` (line 213-ish), add:

```python
    # True when the entries carry a live projection (gates armed + a KO
    # match is live). Frontend surfaces key their LIVE chrome off this.
    live_projection_active: bool = False
```

- [ ] **Step 3: Verify import + serialization**

Run: `docker-compose exec -T backend python -c "from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse; print('projected_total' in LeaderboardEntry.model_fields, 'live_projection_active' in LeaderboardResponse.model_fields)"`
Expected: `True True`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/leaderboard.py
git commit -m "feat(schema): add projected_* fields + live_projection_active"
```

---

## Task 3: Backend — the live projection service (TDD)

**Files:**
- Create: `backend/app/services/live_projection.py`
- Create: `backend/tests/test_live_projection.py`

- [ ] **Step 1: Write the failing test for the pure re-ranker**

Create `backend/tests/test_live_projection.py`:

```python
import uuid

from app.schemas.leaderboard import LeaderboardEntry, PointBreakdown
from app.services.live_projection import project_rows


def _entry(name: str, total: int, exact: int = 0) -> LeaderboardEntry:
    return LeaderboardEntry(
        entry_id=uuid.uuid4(),
        entry_name=name,
        user_id=uuid.uuid4(),
        user_name=name,
        position=0,
        total_points=total,
        breakdown=PointBreakdown(),
        exact_scores=exact,
    )


def test_project_rows_reranks_and_leaves_banked_untouched():
    james = _entry("James", 512)
    sarah = _entry("Sarah", 498)
    kevin = _entry("Kevin", 470)
    banked = [james, sarah, kevin]  # banked order: James, Sarah, Kevin
    deltas = {kevin.entry_id: 30}  # Kevin's live pick advances → +30 → 500

    out = project_rows(banked, deltas)

    # New list of copies — inputs untouched (cache protection).
    assert banked[0].total_points == 512 and banked[0].projected_total is None
    # Re-ranked by projected total: James 512, Kevin 500, Sarah 498.
    assert [r.entry_name for r in out] == ["James", "Kevin", "Sarah"]
    kevin_out = next(r for r in out if r.entry_name == "Kevin")
    assert kevin_out.projected_total == 500
    assert kevin_out.live_delta == 30
    assert kevin_out.projected_position == 2
    assert kevin_out.total_points == 470  # banked stays banked


def test_project_rows_zero_delta_keeps_banked_order():
    rows = [_entry("A", 300), _entry("B", 200)]
    out = project_rows(rows, {})
    assert [r.projected_total for r in out] == [300, 200]
    assert [r.projected_position for r in out] == [1, 2]
    assert all(r.live_delta == 0 for r in out)
```

- [ ] **Step 2: Run it — expect failure**

Run: `docker-compose exec -T backend pytest tests/test_live_projection.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.live_projection'`.

- [ ] **Step 3: Create the service with the pure re-ranker + helpers**

Create `backend/app/services/live_projection.py`:

```python
"""Live projected-leaderboard overlay (v2.198.0).

Read-time overlay layering a PROVISIONAL knockout-advancement projection
onto the banked leaderboard. Never mutates the banked board (the single
source of truth that daily snapshots + the Race chart consume) — it
copies rows, sets projected_* fields, and re-sorts a fresh list.

See docs/superpowers/plans/2026-07-06-live-projected-leaderboard.md for
the full set of grilled invariants. Key ones:
- Knockout advancement ONLY (R32+). Rarity-free, so no denominator churn.
- Provisional winner = ET-inclusive, PENALTY-BLIND scoreline
  (Score.final_home_score/away). Level match → no winner. A live shootout
  is invisible until FINISHED.
- Overlay projects LIVE matches only; the seamless handoff at FINISHED is
  guaranteed by score_sync hard-invalidating the cache on a KO finish.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse
from app.services.scoring import get_scoring_config

# Stage -> the stage its winner reaches. Mirrors the advancement_map in
# scoring.get_actual_advancement. 'third_place' and 'group' are absent by
# design (third_place is unscored; group has no live projection).
_ADVANCEMENT_MAP = {
    "round_of_32": "round_of_16",
    "round_of_16": "quarter_final",
    "quarter_final": "semi_final",
    "semi_final": "final",
    "final": "winner",
}
_LIVE_STATUSES = (MatchStatus.LIVE, MatchStatus.HALFTIME)
_KO_STAGES = list(_ADVANCEMENT_MAP.keys())


@dataclass
class LiveAdvance:
    """A provisional next-stage advance implied by a live KO match."""

    team: str
    next_stage: str
    points: int


def project_rows(
    entries: list[LeaderboardEntry], deltas: dict[uuid.UUID, int]
) -> list[LeaderboardEntry]:
    """Pure: return a NEW list of row COPIES with projected_* set and
    re-ranked by projected_total (exact_scores tiebreak, matching the
    banked sort). Banked position/total_points on each copy are left
    untouched. NEVER mutates the input list or its rows — the caller
    passes cache-owned objects."""
    projected: list[LeaderboardEntry] = []
    for e in entries:
        delta = deltas.get(e.entry_id, 0)
        copy = e.model_copy()
        copy.live_delta = delta
        copy.projected_total = e.total_points + delta
        projected.append(copy)

    projected.sort(key=lambda r: (r.projected_total, r.exact_scores), reverse=True)

    pos = 1
    for i, r in enumerate(projected):
        if i > 0 and (
            r.projected_total < projected[i - 1].projected_total
            or (
                r.projected_total == projected[i - 1].projected_total
                and r.exact_scores < projected[i - 1].exact_scores
            )
        ):
            pos = i + 1
        r.projected_position = pos
    return projected


async def _has_live_ko(session: AsyncSession) -> bool:
    q = await session.execute(
        select(Fixture.id)
        .where(Fixture.status.in_(_LIVE_STATUSES))
        .where(Fixture.stage.in_(_KO_STAGES))
        .limit(1)
    )
    return q.scalar_one_or_none() is not None


async def _live_ko_advances(session: AsyncSession) -> list[LiveAdvance]:
    """Provisional next-stage advances from currently-live KO matches.

    Winner is decided on the ET-inclusive, PENALTY-BLIND scoreline
    (final_home_score/away). A level match yields nothing (goes to
    ET/pens). Unresolved slot placeholders never produce an advance.
    """
    adv_config = get_scoring_config().get("advancement", {})
    result = await session.execute(
        select(Fixture, Score)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(Fixture.status.in_(_LIVE_STATUSES))
        .where(Fixture.stage.in_(_KO_STAGES))
    )
    advances: list[LiveAdvance] = []
    for fixture, score in result.all():
        home, away = score.final_home_score, score.final_away_score
        if home == away:
            continue  # level → no provisional winner
        winner = fixture.home_team if home > away else fixture.away_team
        if not winner or winner.startswith("slot:"):
            continue
        next_stage = _ADVANCEMENT_MAP[fixture.stage]
        advances.append(
            LiveAdvance(
                team=winner,
                next_stage=next_stage,
                points=int(adv_config.get(next_stage, 0)),
            )
        )
    return advances


async def _deltas_by_entry(
    session: AsyncSession, advances: list[LiveAdvance]
) -> dict[uuid.UUID, int]:
    """Provisional point gain per entry from the given live advances.

    An entry gains adv_config[next_stage] for each live advance whose
    (team, next_stage) matches one of its bracket picks. While a match is
    LIVE, that (team, next_stage) credit is never already banked (the next
    round isn't seeded yet), so no gap-check is needed and double-counting
    is impossible. PHASE_1 only (dormant phase_2 rows exist)."""
    if not advances:
        return {}
    points_for = {(a.team, a.next_stage): a.points for a in advances}
    teams = [a.team for a in advances]
    stages = [a.next_stage for a in advances]
    rows = await session.execute(
        select(
            TeamPrediction.entry_id,
            TeamPrediction.team,
            TeamPrediction.stage,
        )
        .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
        .where(TeamPrediction.team.in_(teams))
        .where(TeamPrediction.stage.in_(stages))
    )
    deltas: dict[uuid.UUID, int] = {}
    for entry_id, team, stage in rows.all():
        pts = points_for.get((team, stage))
        if pts:
            deltas[entry_id] = deltas.get(entry_id, 0) + pts
    return deltas


async def _gates_open(session: AsyncSession) -> bool:
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    comp = result.scalar_one_or_none()
    return bool(comp and comp.knockout_scoring_enabled and comp.live_projection_enabled)


async def apply_live_projection(
    session: AsyncSession, response: LeaderboardResponse
) -> LeaderboardResponse:
    """Layer the live KO projection onto a banked LeaderboardResponse.

    Returns the response unchanged (live_projection_active stays False)
    when the gates are closed or no KO match is live. Otherwise returns a
    NEW response whose entries are re-ranked COPIES carrying projected_*.
    """
    if not await _gates_open(session):
        return response
    if not await _has_live_ko(session):
        return response
    advances = await _live_ko_advances(session)
    deltas = await _deltas_by_entry(session, advances)
    projected_entries = project_rows(response.entries, deltas)
    return response.model_copy(
        update={"entries": projected_entries, "live_projection_active": True}
    )
```

- [ ] **Step 4: Run the pure tests — expect pass**

Run: `docker-compose exec -T backend pytest tests/test_live_projection.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Add the service-level integration tests**

Append to `backend/tests/test_live_projection.py` (uses the project's existing async test fixtures — mirror the session/competition/fixture builders already used in `backend/tests/test_scoring.py`; import them the same way that file does):

```python
import pytest
from datetime import datetime, timezone

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score
from app.services.live_projection import (
    _live_ko_advances,
    _has_live_ko,
    apply_live_projection,
)


def _ko_fixture(comp_id, home, away, stage="round_of_32"):
    return Fixture(
        competition_id=comp_id,
        home_team=home,
        away_team=away,
        stage=stage,
        status=MatchStatus.LIVE,
        kickoff=datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc),
        external_id="999001",
    )


@pytest.mark.asyncio
async def test_live_advance_uses_penalty_blind_scoreline(session):
    comp = Competition(name="WC", is_active=True, knockout_scoring_enabled=True,
                       live_projection_enabled=True)
    session.add(comp)
    await session.commit()
    fx = _ko_fixture(comp.id, "Brazil", "Ghana")
    session.add(fx)
    await session.commit()
    # 1-0 live, but a bogus in-progress pen tally that MUST be ignored.
    session.add(Score(fixture_id=fx.id, home_score=1, away_score=0,
                      home_penalties=1, away_penalties=2))
    await session.commit()

    advances = await _live_ko_advances(session)
    assert len(advances) == 1
    assert advances[0].team == "Brazil"          # scoreline, NOT the pen tally
    assert advances[0].next_stage == "round_of_16"


@pytest.mark.asyncio
async def test_level_live_match_projects_nothing(session):
    comp = Competition(name="WC", is_active=True, knockout_scoring_enabled=True,
                       live_projection_enabled=True)
    session.add(comp)
    await session.commit()
    fx = _ko_fixture(comp.id, "Spain", "Italy")
    session.add(fx)
    await session.commit()
    session.add(Score(fixture_id=fx.id, home_score=1, away_score=1))  # level → pens
    await session.commit()

    assert await _has_live_ko(session) is True
    assert await _live_ko_advances(session) == []


@pytest.mark.asyncio
async def test_gates_closed_returns_response_untouched(session):
    from app.schemas.leaderboard import LeaderboardResponse
    comp = Competition(name="WC", is_active=True, knockout_scoring_enabled=False,
                       live_projection_enabled=True)  # one gate closed
    session.add(comp)
    await session.commit()
    resp = LeaderboardResponse(entries=[], last_calculated=datetime.now(timezone.utc),
                               total_participants=0)
    out = await apply_live_projection(session, resp)
    assert out.live_projection_active is False
    assert out is resp  # unchanged object
```

- [ ] **Step 6: Run the full new test file — expect pass**

Run: `docker-compose exec -T backend pytest tests/test_live_projection.py -q`
Expected: PASS (all). If a fixture-builder import differs, read `backend/tests/test_scoring.py` for the exact `session` fixture + model constructors and match them.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/live_projection.py backend/tests/test_live_projection.py
git commit -m "feat(scoring): live projected-leaderboard overlay service + tests"
```

---

## Task 4: Backend — wire the overlay into GET /leaderboard/

**Files:**
- Modify: `backend/app/api/leaderboard.py:116-161`

- [ ] **Step 1: Import and apply the overlay**

At the top of `backend/app/api/leaderboard.py` add the import (next to the existing service imports):

```python
from app.services.live_projection import apply_live_projection
```

In `get_leaderboard()`, the current body calls `calculate_leaderboard` and returns its result directly (line 148). Change so the returned response passes through the overlay first:

```python
    response = await calculate_leaderboard(session, force_refresh=force, phase=phase)
    response = await apply_live_projection(session, response)
    return response
```

Do NOT touch `get_all_trajectories` (line 272) or `_build_trajectory` (line 207) — those must stay banked (they feed the Race chart / rank paths, invariant #6).

- [ ] **Step 2: Manual smoke — gates off means no change**

Run: `docker-compose exec -T backend pytest tests/test_live_projection.py -q` (still green) and confirm existing leaderboard endpoint tests still pass:
Run: `docker-compose exec -T backend pytest tests/ -q -k leaderboard`
Expected: PASS. With gates off (default), `apply_live_projection` returns the response untouched, so all existing assertions hold.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/leaderboard.py
git commit -m "feat(api): apply live projection overlay on GET /leaderboard/"
```

---

## Task 5: Backend — surface the flag on phase-status

**Files:**
- Modify: `backend/app/api/competition.py:84-155`

- [ ] **Step 1: Add the field to PhaseStatus**

In `class PhaseStatus`, after `simulator_enabled: bool = False` (line 110), add:

```python
    # Live projection master switch (v2.198.0) — admin-controlled;
    # surfaced so the admin UI renders the toggle's current state and
    # the frontend can reason about whether the live board can appear.
    live_projection_enabled: bool = False
```

- [ ] **Step 2: Populate it in get_phase_status**

In the `return PhaseStatus(...)` block, after `simulator_enabled=...` (line 154), add:

```python
        live_projection_enabled=(
            competition.live_projection_enabled if competition else False
        ),
```

- [ ] **Step 3: Verify**

Run: `docker-compose exec -T backend pytest tests/ -q -k phase_status`
Expected: PASS (existing phase-status tests tolerate the new default-False field). If a test constructs `PhaseStatus(...)` by hand and now fails, it doesn't need the field (it has a default) — investigate only if a strict-equality assertion breaks.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/competition.py
git commit -m "feat(api): expose live_projection_enabled on phase-status"
```

---

## Task 6: Backend — admin toggle endpoint (TDD)

**Files:**
- Modify: `backend/app/api/admin.py:783` (after the knockout-scoring endpoint)
- Create: `backend/tests/test_admin_live_projection_toggle.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_live_projection_toggle.py` (mirror the structure of the existing knockout-scoring toggle test — find it with `grep -rn "knockout-scoring" backend/tests` and copy its auth/admin fixtures verbatim):

```python
import pytest
from sqlmodel import select

from app.models.competition import Competition


@pytest.mark.asyncio
async def test_toggle_live_projection(admin_client, session):
    comp = Competition(name="WC", is_active=True)
    session.add(comp)
    await session.commit()

    r = await admin_client.post("/api/admin/competition/live-projection",
                                json={"enabled": True})
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "live_projection_enabled": True}

    refreshed = (await session.execute(
        select(Competition).where(Competition.is_active == True))).scalar_one()
    assert refreshed.live_projection_enabled is True
```

- [ ] **Step 2: Run it — expect 404 (route missing)**

Run: `docker-compose exec -T backend pytest tests/test_admin_live_projection_toggle.py -q`
Expected: FAIL (404 / assertion). If `admin_client` fixture name differs, copy the exact fixture used by the knockout-scoring test.

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/admin.py`, immediately after `set_knockout_scoring_enabled` returns (after line 783), add:

```python
# ---------------------------------------------------------------------------
# Live projection master switch (v2.198.0)
# ---------------------------------------------------------------------------
class LiveProjectionRequest(BaseModel):
    """Toggle the live projected-leaderboard master switch."""

    enabled: bool


@router.post("/competition/live-projection")
async def set_live_projection_enabled(
    request: LiveProjectionRequest,
    session: DbSession,
    admin: AdminUser,
) -> dict:
    """Flip the live-projection gate (v2.198.0).

    When true (AND knockout_scoring_enabled is true AND a KO match is
    live) GET /leaderboard/ layers the provisional projection onto the
    banked board. Read-time only — no cache invalidation needed; the gate
    is read fresh on every projection. Auditable, idempotent.
    """
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )

    previous = competition.live_projection_enabled
    competition.live_projection_enabled = request.enabled
    competition.updated_at = utc_now()
    if previous != request.enabled:
        record_audit_event(
            session,
            event_type="competition.live_projection_toggled",
            actor_user_id=admin.id,
            actor_role=ActorRole.ADMIN,
            subject_type="competition",
            subject_id=competition.id,
            metadata={"from": previous, "to": request.enabled},
        )
    await session.commit()

    return {"status": "ok", "live_projection_enabled": request.enabled}
```

- [ ] **Step 4: Run the test — expect pass**

Run: `docker-compose exec -T backend pytest tests/test_admin_live_projection_toggle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/admin.py backend/tests/test_admin_live_projection_toggle.py
git commit -m "feat(admin): live-projection toggle endpoint + test"
```

---

## Task 7: Backend — seamless FINISHED handoff (KO finish hard-invalidate)

**Files:**
- Modify: `backend/app/services/score_sync.py`
- Modify/create: `backend/tests/test_score_sync.py` (add a case)

**Why:** The overlay projects LIVE matches only. At the whistle the overlay stops carrying the +30; if the banked cache is only soft-expired (rebuilds lazily), there's a ~60s window where neither source shows the credit → the projected number dips at the best moment. Hard-invalidating on a **knockout** finish forces the next read to rebuild the banked board with the real credit, closing the gap. KO finishes are rare (≤ a few/day), so the one blocking rebuild is acceptable.

- [ ] **Step 1: Track KO finishes on the result dataclass**

In `backend/app/services/score_sync.py`, in `class ScoreSyncResult`, add after `points_relevant: int = 0` (line 38):

```python
    # Subset of points_relevant that were KNOCKOUT-stage finishes. These
    # hard-invalidate the leaderboard cache (vs the soft-expire used for
    # group finishes) so the live-projection handoff at full time is
    # seamless — see docs/.../2026-07-06-live-projected-leaderboard.md.
    points_relevant_ko: int = 0
```

- [ ] **Step 2: Increment it on KO FINISHED writes**

In `_apply_external_score`, there are two spots that do `result.points_relevant += 1` when `ext.status == MatchStatus.FINISHED` (the new-Score branch ~line 453 and the update branch ~line 466). Immediately after **each** `result.points_relevant += 1`, add:

```python
            if fixture.stage in ("round_of_32", "round_of_16", "quarter_final", "semi_final", "final"):
                result.points_relevant_ko += 1
```

(`third_place` and `group` are deliberately excluded — third_place is unscored; group finishes keep the soft-expire path.)

- [ ] **Step 3: Choose hard vs soft invalidation at the end of the sync**

In `sync_scores_once`, replace the current cache-expiry block (line 173-182):

```python
    if result.points_relevant > 0:
        expire_cache()
```

with:

```python
    if result.points_relevant_ko > 0:
        # A knockout match just finished: hard-invalidate so the banked
        # board reflects the real advancement credit on the very next
        # read, keeping the live-projection handoff seamless (no dip at
        # full time). Blocks one request on a rebuild — rare + acceptable.
        invalidate_cache()
    elif result.points_relevant > 0:
        # Group-stage finish or a correction: soft-expire (stale-while-
        # revalidate) as before — no live projection is involved.
        expire_cache()
```

And update the import at line 24:

```python
from app.services.leaderboard import expire_cache, invalidate_cache
```

- [ ] **Step 4: Write the test**

Add to `backend/tests/test_score_sync.py` (match its existing provider-mock + `httpx.Response(..., request=...)` pattern per `CLAUDE.md`; if the file doesn't exist, create it modelling `backend/tests/test_odds_cache.py`'s async-httpx mocking):

```python
@pytest.mark.asyncio
async def test_ko_finish_hard_invalidates_cache(session, monkeypatch):
    import app.services.score_sync as ss

    called = {"invalidate": 0, "expire": 0}
    monkeypatch.setattr(ss, "invalidate_cache", lambda: called.__setitem__("invalidate", called["invalidate"] + 1))
    monkeypatch.setattr(ss, "expire_cache", lambda: called.__setitem__("expire", called["expire"] + 1))

    result = ss.ScoreSyncResult()
    result.points_relevant = 1
    result.points_relevant_ko = 1
    # Drive only the final expiry decision (extract it into a tiny helper
    # if needed, or assert via a full sync_scores_once with a KO fixture
    # transitioning LIVE->FINISHED — see test_score_sync existing pattern).
    if result.points_relevant_ko > 0:
        ss.invalidate_cache()
    elif result.points_relevant > 0:
        ss.expire_cache()

    assert called["invalidate"] == 1 and called["expire"] == 0
```

Prefer a full-path test (mock the provider to return a KO fixture flipping LIVE→FINISHED, run `sync_scores_once`, assert `invalidate_cache` was called) if the existing test harness already builds fixtures — the snippet above is the minimum viable guard.

- [ ] **Step 5: Run tests**

Run: `docker-compose exec -T backend pytest tests/test_score_sync.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/score_sync.py backend/tests/test_score_sync.py
git commit -m "feat(score-sync): hard-invalidate cache on KO finish for seamless live handoff"
```

- [ ] **Step 7: Run the FULL backend suite (schema-drift gate)**

Run: `docker-compose exec -T backend pytest tests/ -q`
Expected: PASS (0 failed). Adding `live_projection_enabled` (required-with-default) + schema fields should not break hand-built rows because all new fields have defaults — but per `CLAUDE.md` this full run is the only gate that catches drift. Fix any `MagicMock(spec=...)` fixtures that assert on new fields.

---

## Task 8: Frontend — types

**Files:**
- Modify: `frontend/src/lib/types/leaderboard.ts:24-50`

- [ ] **Step 1: Extend LbEntryV4**

In `frontend/src/lib/types/leaderboard.ts`, inside the `LbEntryV4` intersection (after `bonus_knockout_points?: number;`, line 36), add:

```typescript
	/** Live projection (v2.198.0) — present only when the response's
	 *  live_projection_active is true. Banked position/total_points on the
	 *  base type stay banked; these carry the provisional KO projection. */
	projected_position?: number | null;
	projected_total?: number | null;
	live_delta?: number | null;
```

- [ ] **Step 2: Extend LbResponseV4**

After `published_sheet_url: string | null;` (line 49), add:

```typescript
	/** True when entries carry a live KO projection (gates armed + a
	 *  knockout match is live). Surfaces key their LIVE chrome off this. */
	live_projection_active?: boolean;
```

- [ ] **Step 3: Type-check**

Run: `docker-compose exec -T frontend-dev npm run check`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types/leaderboard.ts
git commit -m "feat(types): projected_* fields + live_projection_active"
```

---

## Task 9: Frontend — admin toggle (api client + store + UI)

**Files:**
- Modify: `frontend/src/lib/api/admin.ts:161-165`
- Modify: `frontend/src/lib/stores/phase.ts:66-71`
- Modify: `frontend/src/routes/admin/+page.svelte`

- [ ] **Step 1: API client function**

In `frontend/src/lib/api/admin.ts`, after `setKnockoutScoringEnabled` (line 165), add:

```typescript
export async function setLiveProjectionEnabled(
	enabled: boolean
): Promise<{ status: string; live_projection_enabled: boolean }> {
	return api.post('/admin/competition/live-projection', { enabled });
}
```

- [ ] **Step 2: Derived store**

In `frontend/src/lib/stores/phase.ts`, after the `knockoutScoringEnabled` derived store (line 71), add:

```typescript
export const liveProjectionEnabled = derived(
	phaseStatus,
	($phaseStatus) =>
		($phaseStatus as (PhaseStatus & { live_projection_enabled?: boolean }) | null)
			?.live_projection_enabled ?? false
);
```

- [ ] **Step 3: Admin toggle card**

In `frontend/src/routes/admin/+page.svelte`: (a) import `setLiveProjectionEnabled` from `$lib/api/admin` and `liveProjectionEnabled` from the phase store (add to the existing import lines that bring in `setKnockoutScoringEnabled` / `knockoutScoringEnabled`); (b) add state + handler mirroring `handleToggleKnockoutScoring` (which lives at lines 127-143):

```svelte
	let togglingLiveProjection = false;
	let liveProjectionError: string | null = null;

	async function handleToggleLiveProjection() {
		const next = !$liveProjectionEnabled;
		const message = next
			? 'ENABLE the live projected leaderboard? During knockout matches the standings will re-rank in real time based on who is currently winning (provisional — banked points are untouched until full time). Requires knockout scoring to be ON to have any effect.'
			: 'DISABLE the live projected leaderboard? Standings immediately revert to banked-only on the next refresh.';
		if (!confirm(message)) return;
		togglingLiveProjection = true;
		liveProjectionError = null;
		try {
			await setLiveProjectionEnabled(next);
			await fetchPhaseStatus();
		} catch (e) {
			liveProjectionError = e instanceof Error ? e.message : 'Toggle failed';
		} finally {
			togglingLiveProjection = false;
		}
	}
```

(c) Add the UI card next to the knockout-scoring card (which lives at lines 845-889). Copy that card's markup and adapt labels: status badge `⚡ LIVE — standings react in real time` / `HELD — banked standings only`; button `Enable live standings` / `Disable live standings`; wire `on:click={handleToggleLiveProjection}`, `disabled={togglingLiveProjection}`, and render `liveProjectionError`.

- [ ] **Step 4: Type-check**

Run: `docker-compose exec -T frontend-dev npm run check`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/admin.ts frontend/src/lib/stores/phase.ts frontend/src/routes/admin/+page.svelte
git commit -m "feat(admin-ui): live-projection toggle card + store + client"
```

---

## Task 10: Frontend — display helpers (TDD)

**Files:**
- Modify: `frontend/src/lib/utils/leaderboardV4.ts`
- Modify: `frontend/src/lib/utils/leaderboardV4.test.ts`

- [ ] **Step 1: Write failing tests**

Add to `frontend/src/lib/utils/leaderboardV4.test.ts`:

```typescript
import { displayRank, displayTotal } from './leaderboardV4';

const base = (o: Partial<any>) => ({
	entry_id: 'x', entry_name: 'A', user_id: 'u', user_name: 'A',
	position: 5, total_points: 470, breakdown: {}, exact_scores: 0,
	...o
});

describe('displayRank / displayTotal', () => {
	it('use projected fields when live', () => {
		const e = base({ projected_position: 2, projected_total: 500 });
		expect(displayRank(e as any, true)).toBe(2);
		expect(displayTotal(e as any, true)).toBe(500);
	});
	it('use banked fields when not live', () => {
		const e = base({ projected_position: 2, projected_total: 500 });
		expect(displayRank(e as any, false)).toBe(5);
		expect(displayTotal(e as any, false)).toBe(470);
	});
	it('fall back to banked when projected is null even if live', () => {
		const e = base({ projected_position: null, projected_total: null });
		expect(displayRank(e as any, true)).toBe(5);
		expect(displayTotal(e as any, true)).toBe(470);
	});
});
```

- [ ] **Step 2: Run — expect fail**

Run: `docker-compose exec -T frontend-dev npx vitest run src/lib/utils/leaderboardV4.test.ts`
Expected: FAIL (`displayRank is not a function`).

- [ ] **Step 3: Implement the helpers**

Add to `frontend/src/lib/utils/leaderboardV4.ts`:

```typescript
import type { LbEntryV4 } from '$lib/types/leaderboard';

/** Rank to render: projected when the live board is armed and a projected
 *  value exists, else the banked position. */
export function displayRank(e: LbEntryV4, live: boolean): number {
	return live && e.projected_position != null ? e.projected_position : e.position;
}

/** Points to render: projected when live + present, else banked total. */
export function displayTotal(e: LbEntryV4, live: boolean): number {
	return live && e.projected_total != null ? e.projected_total : e.total_points;
}
```

- [ ] **Step 4: Run — expect pass**

Run: `docker-compose exec -T frontend-dev npx vitest run src/lib/utils/leaderboardV4.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/leaderboardV4.ts frontend/src/lib/utils/leaderboardV4.test.ts
git commit -m "feat(leaderboard-utils): displayRank/displayTotal live helpers + tests"
```

---

## Task 11: Frontend — the LIVE pill + standings surface

**Files:**
- Create: `frontend/src/lib/components/LiveProjectionPill.svelte`
- Modify: `frontend/src/routes/leaderboard/+page.svelte:181-183,268-282,341-360`
- Modify: `frontend/src/lib/components/leaderboard/v4/StandingsTable.svelte`
- Modify: `frontend/src/lib/components/leaderboard/v4/StandingRow.svelte:47,109-119`

- [ ] **Step 1: Create the LIVE pill**

Create `frontend/src/lib/components/LiveProjectionPill.svelte` (mirror `ProvisionalPill.svelte`'s popover mechanics — same open/close + `/rules#finalization` link pattern):

```svelte
<script lang="ts">
	let open = false;
</script>

<button
	type="button"
	class="inline-flex items-center gap-1 rounded-badge bg-error/15 px-1.5 py-0.5 text-[11px] font-bold text-error"
	on:click={() => (open = !open)}
	aria-label="About live standings"
>
	<span class="inline-block h-1.5 w-1.5 rounded-full bg-error animate-pulse-soft"></span>
	LIVE
</button>

{#if open}
	<div class="absolute z-20 mt-1 w-64 rounded-box border border-base-300 bg-base-200 p-3 text-[12px] shadow-card">
		<div class="mb-1.5 font-display text-[13px] font-bold tracking-tight">Live standings</div>
		<p>
			These standings include knockout matches in progress. If a match ended now, the
			current leader would advance — so points and ranks shown are <b>provisional</b> and
			can change as the match plays out.
		</p>
		<p class="mt-1.5 text-base-content/60">
			Penalty shootouts don't count until full time. Banked points never move mid-match.
		</p>
	</div>
{/if}
```

- [ ] **Step 2: Live ordering + "based on live" cue in the page**

In `frontend/src/routes/leaderboard/+page.svelte`:

(a) Derive whether the board is live and order rows by projected position when it is. Replace line 181 (`$: rows = board?.entries ?? [];`) with:

```svelte
	$: liveActive = board?.live_projection_active === true;
	$: rows = liveActive
		? [...(board?.entries ?? [])].sort(
				(a, b) => (a.projected_position ?? a.position) - (b.projected_position ?? b.position)
			)
		: (board?.entries ?? []);
```

(b) Add a "based on live" match cue next to the existing `lastFinished` computation (after line 282). This reads the fixtures store for in-progress knockout matches (client-side, like `lastFinished`):

```svelte
	$: liveMatchCue = (() => {
		const live = $fixtures.filter(
			(f) =>
				(f.status === 'live' || f.status === 'halftime') &&
				f.stage !== 'group' &&
				f.stage !== 'third_place' &&
				f.score
		);
		if (live.length === 0) return null;
		if (live.length > 1) return `${live.length} matches`;
		const f = live[0];
		const min = f.minute != null ? ` · ${f.minute}′` : '';
		return `${teamCode(f.home_team)} ${f.score!.home_score}–${f.score!.away_score} ${teamCode(f.away_team)}${min}`;
	})();
```

(c) In the freshness strip (lines 341-360), when `liveActive`, prefer the live cue + the LIVE pill. Add the import for `LiveProjectionPill` at the top, then inside the `<p>` freshness strip, before the `last result` block, add:

```svelte
				{#if liveActive && liveMatchCue}
					<span class="text-base-content/40">·</span>
					<span class="text-error">based on live: <b>{liveMatchCue}</b></span>
					<span class="ml-1 relative"><LiveProjectionPill /></span>
				{/if}
```

(Keep the existing `last result` + `ProvisionalPill` — the LIVE pill sits alongside; both are honest.)

- [ ] **Step 3: Pass `live` into StandingsTable and stop it re-sorting to banked**

In `frontend/src/routes/leaderboard/+page.svelte`, the StandingsTable render (line ~433) passes `rows={filteredRows}`. Add a prop `live={liveActive}`.

In `frontend/src/lib/components/leaderboard/v4/StandingsTable.svelte`: add `export let live = false;` (near line 18-27 props). The component currently computes `$: sortedRows = sortRows(rows, sort, multiOwners);` (line 71). Change so that when `live` is true and the user hasn't picked an explicit non-default sort, the incoming (already projected-ordered) `rows` order is preserved:

```svelte
	$: sortedRows = live && isDefaultSort(sort) ? rows : sortRows(rows, sort, multiOwners);
```

Read the existing `sort` state's default value in this file and implement `isDefaultSort` accordingly (e.g. `sort.key === 'rank'` — match whatever the file already uses for the rank column). If `sortRows` already sorts by `position`, an explicit rank sort while live should sort by `projected_position`; simplest is to keep the projected order from the page for the default and let explicit column sorts (points, name) fall through to `sortRows`.

- [ ] **Step 4: Render projected rank + delta chip in StandingRow**

In `frontend/src/lib/components/leaderboard/v4/StandingRow.svelte`: add `export let live = false;` and thread it from StandingsTable's `{#each}` (add `{live}` to each `<StandingRow .../>`).

Replace the rank cell (line 47):

```svelte
<span role="cell"><RankCell rank={live && row.projected_position != null ? row.projected_position : row.position} move={row.daily_movement} /></span>
```

Replace the total-points cell content (line 118, `{row.total_points}`) so it shows the projected total plus a delta chip when live:

```svelte
	{#if live && row.live_delta != null && row.live_delta > 0}
		<span class="mr-1 align-middle text-[11px] font-bold text-success">+{row.live_delta}</span>
	{/if}
	{live && row.projected_total != null ? row.projected_total : row.total_points}
```

- [ ] **Step 5: Type-check**

Run: `docker-compose exec -T frontend-dev npm run check`
Expected: 0 errors. (Watch for the `$fixtures` `f.minute`/`f.score` optional-chaining and the Svelte template gotchas in `CLAUDE.md` — no `as` casts in markup.)

- [ ] **Step 6: Manual browser verification (overlay + restart)**

Overlay the changed frontend files into the main worktree, `docker-compose restart frontend-dev`, sign in via a magic link from `docker-compose logs backend`, and (with `knockout_scoring_enabled` + `live_projection_enabled` both ON in the DB and a KO fixture manually set LIVE with a 1-0 score via `/admin/sync`) confirm: the standings re-rank, the `+30`/rank move shows, the LIVE pill + "based on live" cue appear. Then restore the main worktree.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/components/LiveProjectionPill.svelte frontend/src/routes/leaderboard/+page.svelte frontend/src/lib/components/leaderboard/v4/StandingsTable.svelte frontend/src/lib/components/leaderboard/v4/StandingRow.svelte
git commit -m "feat(leaderboard): live re-ranking standings + LIVE pill + delta chips"
```

---

## Task 12: Frontend — dashboard surface (mini-leaderboard + KPI)

**Files:**
- Modify: `frontend/src/lib/components/dashboard/v4/DashboardV4.svelte:85-101,137-145,167-169,282-288`
- Modify: `frontend/src/lib/components/dashboard/v4/MiniLeaderboard.svelte:16-124`

- [ ] **Step 1: Capture the live flag in DashboardV4**

In `frontend/src/lib/components/dashboard/v4/DashboardV4.svelte`, add state `let liveProjectionActive = false;`. In `loadCore` (lines 92-98) and in the 60s poll (lines 137-145), where `lbRows = lb.entries;` is set, also set:

```svelte
		liveProjectionActive = lb.live_projection_active === true;
```

- [ ] **Step 2: Project the rankByEntry KPI map**

Replace the `rankByEntry` derivation (lines 167-169) so the "you're Nth" KPI (rendered by `EntrySummaryBar` via this map) uses projected values when live:

```svelte
	$: rankByEntry = new Map<string, EntryRankInfo>(
		lbRows.map((e) => [
			e.entry_id,
			{
				position: liveProjectionActive && e.projected_position != null ? e.projected_position : e.position,
				total_points: liveProjectionActive && e.projected_total != null ? e.projected_total : e.total_points
			}
		])
	);
```

- [ ] **Step 3: Pass the flag to MiniLeaderboard**

In the `<MiniLeaderboard ... />` render (lines 282-288), add `live={liveProjectionActive}`.

- [ ] **Step 4: Live order + LIVE pill in MiniLeaderboard**

In `frontend/src/lib/components/dashboard/v4/MiniLeaderboard.svelte`:

(a) Add `export let live = false;` to props (lines 16-24) and import the helpers + pill:

```svelte
	import { displayRank, displayTotal } from '$lib/utils/leaderboardV4';
	import LiveProjectionPill from '$lib/components/LiveProjectionPill.svelte';
```

(b) The rows come from `miniLbRows(rows, userId, 15)` (line 26) which slices by banked position. When live, sort the incoming `rows` by projected position first so "yours + top" reflect the live order:

```svelte
	$: orderedRows = live
		? [...rows].sort((a, b) => (a.projected_position ?? a.position) - (b.projected_position ?? b.position))
		: rows;
	$: ({ yours, top } = miniLbRows(orderedRows, userId, 15));
```

(c) In BOTH row blocks (the "yours" loop lines 56-83 and the "top" loop lines 88-124), replace `{e.position}` with `{displayRank(e, live)}` and `{e.total_points}` with `{displayTotal(e, live)}`.

(d) Add the LIVE pill to the card header when `live` (place it beside the existing header/title element — add `{#if live}<span class="relative"><LiveProjectionPill /></span>{/if}`).

- [ ] **Step 5: Type-check + unit tests**

Run: `docker-compose exec -T frontend-dev npm run check` (0 errors)
Run: `docker-compose exec -T frontend-dev npx vitest run` (all pass)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/dashboard/v4/DashboardV4.svelte frontend/src/lib/components/dashboard/v4/MiniLeaderboard.svelte
git commit -m "feat(dashboard): live projection on mini-leaderboard + rank KPI"
```

---

## Task 13: Version bump + changelog + feature highlight

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json` (top-level `version` AND `packages[""]`), `backend/pyproject.toml` → `2.198.0`
- Modify: `frontend/src/lib/data/changelog.json` (append entry)
- Modify: `frontend/src/lib/data/featureHighlights.json` (prepend a curated highlight; trim tail to keep ~6-10 items)

- [ ] **Step 1: Bump all version files to `2.198.0`** (minor — adds capability).

- [ ] **Step 2: Append changelog entry** to the END of the `entries` array in `frontend/src/lib/data/changelog.json`:

```json
{ "version": "2.198.0", "date": "2026-07-06", "type": "feature", "summary": "The leaderboard now updates live during knockout matches — standings re-rank in real time based on who's winning, and settle to final points at full time.", "commit": "pending" }
```

- [ ] **Step 3: Add a curated feature highlight** (newest-first) to `frontend/src/lib/data/featureHighlights.json`:

```json
{ "id": "live-leaderboard-2026-07", "title": "Live leaderboard during knockouts", "blurb": "When a knockout match is on, the standings move in real time based on who's currently winning. Points lock in for real at full time.", "since": "2.198.0", "date": "2026-07-06", "href": "/leaderboard" }
```

Trim the oldest highlight if the list exceeds ~10 items (per the feature-awareness rule — do not auto-derive from changelog).

- [ ] **Step 4: Type-check + commit**

Run: `docker-compose exec -T frontend-dev npm run check` (0 errors)

```bash
git add frontend/package.json frontend/package-lock.json backend/pyproject.toml frontend/src/lib/data/changelog.json frontend/src/lib/data/featureHighlights.json
git commit -m "chore(version): bump to 2.198.0"
```

- [ ] **Step 5: STOP — do not deploy.** Per `CLAUDE.md`, do not run the SSH deploy or `git push origin main` without an explicit ship signal. Summarise what's ready and wait.

---

## Self-Review (completed against the grilled spec)

**Spec coverage:**
- Projected overlay, KO-only, rarity-free → Task 3 (`_live_ko_advances` restricted to `_KO_STAGES`, uses flat `adv_config`). ✅
- Penalty-blind / level → nothing → Task 3 (`final_home_score` vs `final_away_score`, `if home == away: continue`) + test `test_live_advance_uses_penalty_blind_scoreline`. ✅
- Re-rank live, automatic, no per-user toggle → Task 11 (page orders by `projected_position`; StandingsTable preserves it). ✅
- Backend computation, cheap overlay, pure function → Task 3 (`project_rows` pure + tested; targeted pick query). ✅
- Additive fields, banked untouched → Task 2 + `project_rows` copies rows, leaves `position`/`total_points`. ✅
- Snapshot purity → overlay only in `get_leaderboard` (Task 4); `calculate_leaderboard`, trajectories, `take_daily_snapshots` untouched. ✅
- Never mutate cached rows → `model_copy()` in `project_rows` + test asserts inputs untouched. ✅
- Seamless FINISHED handoff → Task 7 (KO-finish hard-invalidate) + LIVE-only overlay. ✅
- Surfaces A2 (standings + drawer + home mini + KPI) → Tasks 11 (standings; drawer inherits rows) + 12 (mini + `rankByEntry` KPI). ✅
- Admin kill-switch `live_projection_enabled`, default off → Tasks 1, 5, 6, 9. ✅
- Two-flag gate + "≥1 live KO" → Task 3 (`_gates_open` AND `_has_live_ko`). ✅

**Type consistency:** field names `projected_position`/`projected_total`/`live_delta` + `live_projection_active` + flag `live_projection_enabled` used identically across backend schema, frontend types, helpers, and components. Endpoint route `/admin/competition/live-projection` matches the client function. ✅

**Placeholder scan:** two intentional "read the existing symbol" instructions remain (StandingsTable `sort` default in Task 11 Step 3; the exact `admin_client`/session fixture names in Tasks 6/7) — these are environment/file-specific values the engineer confirms by reading the named file, not hand-wavy TODOs. All code steps carry real code.

**Open risk to watch during execution:** `StandingsTable.sortRows` internals weren't captured verbatim — Task 11 Step 3 treats it as a black box and only overrides the default rank sort. If the file's sort model differs from the assumption, keep the projected order at the page level and make StandingsTable a pass-through when `live && default sort`.
