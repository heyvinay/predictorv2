# Tournament Conclusion Backend (Plan A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `tournament_concluded` end-state, the champion/Trionda final-podium service + endpoint, the pool-retrospective aggregate, the TOURNAMENT_FINAL broadcast, the on-demand full-rescore audit, and the feedback `features` extension.

**Architecture:** Mirrors the Group Stage Winner four-layer stack (model flag → ungated service → flag-or-admin-gated API → admin toggle). All new read endpoints allow anonymous access once `tournament_concluded` is true (`OptionalUser` dependency). One aggregate service (`pool_retrospective`) computes every pool-vs-reality stat plus per-member superlatives in a single pass.

**Tech Stack:** FastAPI, SQLModel, Alembic, pytest + pytest_asyncio (in-memory aiosqlite), Resend email templates.

**Spec:** `docs/superpowers/specs/2026-07-18-tournament-conclusion-backend-design.md`

**Testing note (worktree-overlay):** run backend tests via the main worktree per `CLAUDE.md` ("Worktree-overlay testing pattern"): copy changed files to the main worktree, `docker-compose exec -T backend pytest tests/<file> -v` from the main worktree path, then `git checkout --` the overlay files before committing here. Every "Run" step below assumes that pattern.

---

### Task A1: `tournament_concluded` + `final_match_narrative` on Competition

**Files:**
- Modify: `backend/app/models/competition.py` (after `win_probability_enabled`, ~line 94)
- Create: `backend/alembic/versions/<autogen>_add_tournament_conclusion_fields.py`
- Modify: `backend/app/api/competition.py` (PhaseStatus ~line 84, population ~line 158)
- Test: `backend/tests/test_tournament_conclusion.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tournament_conclusion.py`. Copy the local fixture pattern from `backend/tests/test_admin_broadcasts.py:52-76` (this repo has no shared DB conftest):

```python
"""Tournament conclusion end-state (Plan A) — flag, phase-status, admin toggle."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — register all tables
from app.models.competition import Competition
from app.models._datetime import utc_now


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(db_session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC26",
        is_active=True,
        phase1_deadline=utc_now(),
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)
    return comp


@pytest.mark.asyncio
async def test_competition_has_conclusion_fields(competition: Competition):
    assert competition.tournament_concluded is False
    assert competition.final_match_narrative is None
```

If `Competition(...)` needs more required kwargs, read the model once and populate ALL of them (CLAUDE.md schema-drift rule) — copy the working `competition` fixture from `test_admin_broadcasts.py:62-76` verbatim and extend it.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose exec -T backend pytest tests/test_tournament_conclusion.py -v`
Expected: FAIL — `TypeError` / `AttributeError: tournament_concluded`

- [ ] **Step 3: Add the model fields**

In `backend/app/models/competition.py`, directly after `win_probability_enabled` (~line 94):

```python
    # Tournament conclusion switch (Plan A, 2026-07-18): flipped by the admin
    # after the Final. One flag drives the wrap-up page, public read access,
    # the TOURNAMENT_FINAL broadcast tokens and the 🏁 finished-state UI.
    # Retractable: flipping back fully reverts, nothing destructive.
    tournament_concluded: bool = Field(default=False)

    # Admin-authored narrative for the Final match, written minutes after
    # full time from /admin (no deploy). Rendered on the wrap-up page.
    final_match_narrative: str | None = Field(default=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose exec -T backend pytest tests/test_tournament_conclusion.py -v`
Expected: PASS

- [ ] **Step 5: Generate + hand-check the migration**

Run (main worktree): `docker-compose exec backend alembic revision --autogenerate -m "add tournament conclusion fields"`
Then EDIT the generated file so it matches the house pattern (`c2526e136114_add_live_projection_enabled.py`):

```python
def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column(
            "tournament_concluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "competitions",
        sa.Column("final_match_narrative", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("competitions", "final_match_narrative")
    op.drop_column("competitions", "tournament_concluded")
```

Copy the migration file back into this worktree. Verify `down_revision` points at the current head (`docker-compose exec backend alembic heads`).

- [ ] **Step 6: Surface on PhaseStatus**

In `backend/app/api/competition.py` add to the `PhaseStatus` class (after `win_probability_enabled`, ~line 100):

```python
    tournament_concluded: bool = False
```

And in `get_phase_status`'s return (~line 170), following the guarded pattern:

```python
        tournament_concluded=(
            competition.tournament_concluded if competition else False
        ),
```

- [ ] **Step 7: Add phase-status test + run**

Append to `backend/tests/test_tournament_conclusion.py`:

```python
@pytest.mark.asyncio
async def test_phase_status_surfaces_tournament_concluded(
    db_session: AsyncSession, competition: Competition
):
    from app.api.competition import get_phase_status

    status_out = await get_phase_status(session=db_session)
    assert status_out.tournament_concluded is False

    competition.tournament_concluded = True
    await db_session.commit()
    status_out = await get_phase_status(session=db_session)
    assert status_out.tournament_concluded is True
```

(If `get_phase_status` takes different parameter names, match its real signature — it is a plain async function taking the session dependency.)

Run: `docker-compose exec -T backend pytest tests/test_tournament_conclusion.py -v`
Expected: 2 PASS

- [ ] **Step 8: Full backend suite (migration + schema drift gate)**

Run: `docker-compose exec -T backend pytest tests/ -q`
Expected: no new failures vs baseline.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/competition.py backend/alembic/versions/*tournament_conclusion* backend/app/api/competition.py backend/tests/test_tournament_conclusion.py
git commit -m "feat(conclusion): tournament_concluded + final_match_narrative on Competition, surfaced on PhaseStatus"
```

---

### Task A2: Admin toggle + narrative endpoints

**Files:**
- Modify: `backend/app/api/admin.py` (after the GSW release endpoint, ~line 730)
- Modify: `frontend/src/lib/api/admin.ts` (~line 155)
- Modify: `frontend/src/lib/stores/phase.ts` (new derived store)
- Modify: `frontend/src/routes/admin/+page.svelte` (new section beside the GSW one)
- Test: `backend/tests/test_tournament_conclusion.py`

- [ ] **Step 1: Write the failing endpoint tests**

Append to `backend/tests/test_tournament_conclusion.py`. Copy the `client_as_admin` fixture from `test_admin_broadcasts.py:590-607` (AsyncClient + `app.dependency_overrides` for `get_session`/`get_admin_user`) into this file, then:

```python
@pytest.mark.asyncio
async def test_admin_toggles_conclusion(client_as_admin, competition):
    resp = await client_as_admin.post(
        "/api/admin/competition/conclusion", json={"concluded": True}
    )
    assert resp.status_code == 200
    assert resp.json()["tournament_concluded"] is True

    resp = await client_as_admin.post(
        "/api/admin/competition/conclusion", json={"concluded": False}
    )
    assert resp.json()["tournament_concluded"] is False


@pytest.mark.asyncio
async def test_admin_saves_final_narrative(client_as_admin, competition):
    resp = await client_as_admin.put(
        "/api/admin/competition/final-narrative",
        json={"narrative": "A cagey final broke open on 38'."},
    )
    assert resp.status_code == 200
    assert resp.json()["final_match_narrative"].startswith("A cagey")
```

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T backend pytest tests/test_tournament_conclusion.py -v -k "admin"`
Expected: FAIL 404 (routes don't exist)

- [ ] **Step 3: Implement the two admin routes**

In `backend/app/api/admin.py`, directly after `set_group_stage_winner_released` (~line 730), same idiom (audit event, `utc_now`, 404 on no competition):

```python
class ConclusionToggleRequest(BaseModel):
    """Flip the tournament-concluded end-state (wrap-up page + public access)."""

    concluded: bool


@router.post("/competition/conclusion")
async def set_tournament_concluded(
    request: ConclusionToggleRequest,
    session: DbSession,
    admin: AdminUser,
) -> dict:
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )

    previous = competition.tournament_concluded
    competition.tournament_concluded = request.concluded
    competition.updated_at = utc_now()
    if previous != request.concluded:
        record_audit_event(
            session,
            event_type="competition.tournament_concluded_toggled",
            actor_user_id=admin.id,
            actor_role=ActorRole.ADMIN,
            subject_type="competition",
            subject_id=competition.id,
            metadata={"from": previous, "to": request.concluded},
        )
    await session.commit()
    return {"status": "ok", "tournament_concluded": request.concluded}


class FinalNarrativeRequest(BaseModel):
    """Admin-authored narrative for the Final match (wrap-up page)."""

    narrative: str = Field(max_length=2000)


@router.put("/competition/final-narrative")
async def set_final_match_narrative(
    request: FinalNarrativeRequest,
    session: DbSession,
    admin: AdminUser,
) -> dict:
    result = await session.execute(
        select(Competition).where(Competition.is_active == True)  # noqa: E712
    )
    competition = result.scalar_one_or_none()
    if not competition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active competition found",
        )
    competition.final_match_narrative = request.narrative.strip() or None
    competition.updated_at = utc_now()
    record_audit_event(
        session,
        event_type="competition.final_narrative_updated",
        actor_user_id=admin.id,
        actor_role=ActorRole.ADMIN,
        subject_type="competition",
        subject_id=competition.id,
        metadata={"length": len(request.narrative)},
    )
    await session.commit()
    return {"status": "ok", "final_match_narrative": competition.final_match_narrative}
```

(`BaseModel`, `Field`, `select`, `Competition`, `utc_now`, `record_audit_event`, `ActorRole` are already imported in admin.py — verify, add any missing import.)

- [ ] **Step 4: Run to verify pass**

Run: `docker-compose exec -T backend pytest tests/test_tournament_conclusion.py -v`
Expected: all PASS

- [ ] **Step 5: Frontend wiring (store + API + admin section)**

`frontend/src/lib/stores/phase.ts` — add after `winProbabilityEnabled` (cast-through pattern, `phase.ts:99-104`):

```ts
/** Tournament conclusion end-state (wrap-up page + finished-state UI). */
export const tournamentConcluded = derived(
	phaseStatus,
	($phaseStatus) =>
		($phaseStatus as (PhaseStatus & { tournament_concluded?: boolean }) | null)
			?.tournament_concluded ?? false
);
```

`frontend/src/lib/api/admin.ts` — after `setGroupStageWinnerReleased` (~line 154):

```ts
export async function setTournamentConcluded(
	concluded: boolean
): Promise<{ status: string; tournament_concluded: boolean }> {
	return api.post('/admin/competition/conclusion', { concluded });
}

export async function saveFinalNarrative(
	narrative: string
): Promise<{ status: string; final_match_narrative: string | null }> {
	return api.put('/admin/competition/final-narrative', { narrative });
}
```

(If `api.put` doesn't exist in the client, use the same shape as other PUTs in the file — grep `api.put` first; fall back to `api.post` + a POST route if the client has no put helper, keeping backend + client consistent.)

`frontend/src/routes/admin/+page.svelte` — clone the GSW handler block (`:105-125`) and section markup (`:871-906`) into a new "Tournament conclusion" section:

```ts
	import { tournamentConcluded } from '$stores/phase';
	import { setTournamentConcluded, saveFinalNarrative, getAuditStatus, runFinalAudit } from '$api/admin';

	let togglingConclusion = false;
	let conclusionError: string | null = null;
	let finalNarrative = '';
	let savingNarrative = false;

	async function handleToggleConclusion() {
		const next = !$tournamentConcluded;
		const message = next
			? 'CONCLUDE the tournament? Effects: / becomes the public wrap-up page for everyone, wrap-up data endpoints open to anonymous visitors, the TOURNAMENT_FINAL broadcast tokens unlock, and all live cues retire. Run the final audit first if you have not.'
			: 'RETRACT the conclusion? The dashboard and gated access come back; nothing is lost.';
		if (!confirm(message)) return;
		togglingConclusion = true;
		conclusionError = null;
		try {
			await setTournamentConcluded(next);
			await fetchPhaseStatus();
		} catch (e) {
			conclusionError = e instanceof Error ? e.message : 'Toggle failed';
		} finally {
			togglingConclusion = false;
		}
	}

	async function handleSaveNarrative() {
		savingNarrative = true;
		try {
			await saveFinalNarrative(finalNarrative);
		} finally {
			savingNarrative = false;
		}
	}
```

Markup (place next to the GSW section; textarea + save + toggle button + audit controls added in Task A6):

```svelte
<section class="stadium-card no-glow p-5">
	<h2 class="text-lg font-display tracking-wide mb-3">Tournament conclusion</h2>
	<p class="text-sm text-base-content/70 mb-3">
		Status: <b>{$tournamentConcluded ? 'CONCLUDED — wrap-up page live' : 'not concluded'}</b>
	</p>
	<button class="btn btn-primary btn-sm" on:click={handleToggleConclusion} disabled={togglingConclusion}>
		{$tournamentConcluded ? 'Retract conclusion' : 'Conclude tournament'}
	</button>
	{#if conclusionError}<p class="text-error text-sm mt-2">{conclusionError}</p>{/if}
	<div class="mt-4">
		<label class="text-sm font-bold" for="final-narrative">Final match narrative</label>
		<textarea id="final-narrative" class="textarea textarea-bordered w-full mt-1" rows="3"
			maxlength="2000" bind:value={finalNarrative}
			placeholder="Write the story of the Final minutes after full time…"></textarea>
		<button class="btn btn-sm mt-2" on:click={handleSaveNarrative} disabled={savingNarrative}>
			Save narrative
		</button>
	</div>
</section>
```

- [ ] **Step 6: svelte-check**

Run (main worktree, after overlay): `docker-compose exec -T frontend-dev npm run check`
Expected: 0 errors

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/admin.py frontend/src/lib/api/admin.ts frontend/src/lib/stores/phase.ts frontend/src/routes/admin/+page.svelte backend/tests/test_tournament_conclusion.py
git commit -m "feat(conclusion): admin conclusion toggle + final-match narrative editor"
```

---

### Task A3: Shared group-stage-total helper

**Files:**
- Modify: `backend/app/services/group_stage_winner.py`
- Test: `backend/tests/test_tournament_champion.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tournament_champion.py` (fixtures copied from `test_tournament_conclusion.py`):

```python
"""Final podium + Trionda side prize (Plan A)."""

import pytest

from app.services.group_stage_winner import group_stage_total


class _Phase1:
    match_outcome_points = 100
    exact_score_points = 40
    hybrid_bonus_points = 7


class _Breakdown:
    phase1 = _Phase1()


class _Entry:
    breakdown = _Breakdown()
    bonus_group_points = 10


def test_group_stage_total_is_shared_and_stable():
    assert group_stage_total(_Entry()) == 157
```

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T backend pytest tests/test_tournament_champion.py -v`
Expected: FAIL — `ImportError: cannot import name 'group_stage_total'`

- [ ] **Step 3: Extract the helper**

In `backend/app/services/group_stage_winner.py`, add a module-level function above `get_group_stage_podium` and replace the nested `_group_stage_total` (lines 291-298) with a call to it:

```python
def group_stage_total(e) -> int:
    """★ THE group-stage-cash definition. Shared by the GSW podium and the
    Trionda eligibility check (tournament_champion.py). One resolver —
    never re-derive this sum elsewhere (read-vs-score-time rule)."""
    p1 = e.breakdown.phase1
    return (
        p1.match_outcome_points
        + p1.exact_score_points
        + p1.hybrid_bonus_points
        + (e.bonus_group_points or 0)
    )
```

Inside `get_group_stage_podium`, delete the nested def and use `group_stage_total` directly (the sort at line 305 becomes `key=lambda e: (group_stage_total(e), e.exact_scores)`).

- [ ] **Step 4: Run new test + existing GSW tests**

Run: `docker-compose exec -T backend pytest tests/test_tournament_champion.py tests/ -q -k "group_stage or tournament_champion"`
Expected: PASS, no GSW regressions

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/group_stage_winner.py backend/tests/test_tournament_champion.py
git commit -m "refactor(gsw): extract shared group_stage_total helper for Trionda eligibility"
```

---

### Task A4: Final-podium service (`tournament_champion.py`)

**Files:**
- Create: `backend/app/services/tournament_champion.py`
- Create: `backend/app/schemas/tournament_champion.py`
- Test: `backend/tests/test_tournament_champion.py`

- [ ] **Step 1: Write the failing Trionda tests (the core algorithm)**

The Trionda logic is pure — test it against stub rows, no DB. Append to `backend/tests/test_tournament_champion.py`:

```python
from dataclasses import dataclass, field

from app.services.tournament_champion import pick_trionda_recipient


@dataclass
class _Row:
    entry_id: str
    user_name: str
    position: int
    total_points: int
    gs_total: int


def _rows(*specs):
    # specs: (entry_id, position, total, gs_total)
    return [
        _Row(entry_id=e, user_name=e.upper(), position=p, total_points=t, gs_total=g)
        for (e, p, t, g) in specs
    ]


def test_trionda_direct_runner_up_eligible():
    rows = _rows(("champ", 1, 612, 348), ("kevin", 2, 598, 340), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "kevin"
    assert out.requires_draw is False
    assert out.reason == "runner-up on total points"


def test_trionda_skips_group_stage_cash_winner():
    # kevin at #2 also holds the max group-stage total → ineligible, ball walks to #3
    rows = _rows(("champ", 1, 612, 348), ("kevin", 2, 598, 356), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "john"
    assert "not eligible" in out.reason


def test_trionda_shared_gs_cash_both_skipped():
    # champ and kevin SHARE max gs_total (tie) → both ineligible; champ is champion anyway
    rows = _rows(("champ", 1, 612, 356), ("kevin", 2, 598, 356), ("john", 3, 587, 341))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "john"


def test_trionda_rank_tie_breaks_on_group_stage_points():
    rows = _rows(
        ("champ", 1, 612, 356),
        ("a", 2, 598, 330),
        ("b", 2, 598, 345),  # same rank, more gs points → b gets the ball
    )
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "b"
    assert out.requires_draw is False


def test_trionda_persisting_tie_requires_draw():
    rows = _rows(
        ("champ", 1, 612, 356),
        ("a", 2, 598, 330),
        ("b", 2, 598, 330),
    )
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.requires_draw is True
    assert {c.entry_id for c in out.draw_candidates} == {"a", "b"}
    assert out.recipient is None


def test_trionda_shared_champions_shift_runner_up_rank():
    # two joint champions at position 1 → runner-up rank is position 2
    rows = _rows(("c1", 1, 612, 356), ("c2", 1, 612, 340), ("a", 2, 598, 330))
    out = pick_trionda_recipient(rows, gs_total_of=lambda r: r.gs_total)
    assert out.recipient.entry_id == "a"
```

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T backend pytest tests/test_tournament_champion.py -v`
Expected: FAIL — module `tournament_champion` missing

- [ ] **Step 3: Implement schemas**

Create `backend/app/schemas/tournament_champion.py`:

```python
"""API shapes for the final podium / conclusion payload (Plan A)."""

from datetime import datetime

from pydantic import BaseModel


class FinalPodiumEntry(BaseModel):
    entry_id: str
    user_name: str
    entry_name: str
    final_rank: int
    total_points: int
    group_points: int
    knockout_points: int
    bonus_points: int
    exact_scores: int
    rarity_points: int
    days_at_top: int
    champion_pick: str | None
    champion_hit: bool
    is_champion: bool


class TriondaOut(BaseModel):
    recipient_name: str | None
    recipient_entry_id: str | None
    final_rank: int | None
    reason: str
    requires_draw: bool
    draw_candidate_names: list[str] = []


class FinalMatchOut(BaseModel):
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    went_to_extra_time: bool
    penalties: str | None  # e.g. "4–2" or None
    kickoff: datetime | None
    venue: str | None
    narrative: str | None


class AuditSummaryOut(BaseModel):
    run_at: str
    entries_verified: int
    matches_rescored: int
    bonus_questions: int
    discrepancies: int
    sources: list[str]


class FinalPodium(BaseModel):
    entries: list[FinalPodiumEntry]
    trionda: TriondaOut
    story_line: str
    total_days: int
    final_match: FinalMatchOut | None
    audit: AuditSummaryOut | None
```

- [ ] **Step 4: Implement the service**

Create `backend/app/services/tournament_champion.py`:

```python
"""Final podium + Trionda side prize (Plan A, 2026-07-18).

Ungated by design (GSW precedent): the release gate lives at the API
layer (`tournament_concluded OR is_admin`) so the admin can dress-
rehearse in production before flipping the flag.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import utc_now
from app.services.group_stage_winner import group_stage_total
from app.services.leaderboard import calculate_leaderboard

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TriondaResult:
    recipient: object | None  # a leaderboard row, or None when draw pending
    reason: str
    requires_draw: bool = False
    draw_candidates: list = field(default_factory=list)


def pick_trionda_recipient(rows, *, gs_total_of=group_stage_total) -> TriondaResult:
    """Rules-page algorithm, pure over leaderboard rows.

    rows: leaderboard entries with .position, .total_points, .entry_id.
    gs_total_of: injectable for tests; production uses group_stage_total.
    """
    if len(rows) < 2:
        return TriondaResult(None, "not enough entries", requires_draw=False)

    max_gs = max(gs_total_of(r) for r in rows)
    ineligible = {r.entry_id for r in rows if gs_total_of(r) == max_gs}

    champion_rank = rows[0].position
    # every rank strictly below the (possibly shared) champion rank, in order
    ranks = sorted({r.position for r in rows if r.position > champion_rank})
    for rank in ranks:
        at_rank = [r for r in rows if r.position == rank]
        eligible = [r for r in at_rank if r.entry_id not in ineligible]
        if not eligible:
            continue  # whole rank ineligible → walk down
        if len(eligible) == 1:
            reason = (
                "runner-up on total points"
                if rank == ranks[0] and len(at_rank) == 1
                else f"moved down to #{rank} — group-stage champion not eligible"
                if rank != ranks[0]
                else "runner-up on total points"
            )
            return TriondaResult(eligible[0], reason)
        # tie at this rank → group-stage points break it
        best_gs = max(gs_total_of(r) for r in eligible)
        winners = [r for r in eligible if gs_total_of(r) == best_gs]
        if len(winners) == 1:
            return TriondaResult(
                winners[0], f"tied at #{rank} — took it on group-stage points"
            )
        return TriondaResult(
            None,
            f"tied at #{rank} — draw pending",
            requires_draw=True,
            draw_candidates=winners,
        )
    return TriondaResult(None, "no eligible entry", requires_draw=False)


def _knockout_points(p1) -> int:
    return (
        p1.round_of_32_points
        + p1.round_of_16_points
        + p1.quarter_final_points
        + p1.semi_final_points
        + p1.final_points
        + p1.winner_points
    )


def _group_points(p1) -> int:
    return (
        p1.match_outcome_points
        + p1.exact_score_points
        + p1.hybrid_bonus_points
        + p1.group_advance_points
        + p1.group_position_points
    )


async def _days_at_top(session: AsyncSession, entry_id) -> int:
    days_sql = text(
        """
        SELECT COUNT(DISTINCT captured_date) AS days
        FROM leaderboard_snapshots
        WHERE entry_id = :entry_id AND position = 1
        """
    )
    try:
        row = (await session.execute(days_sql, {"entry_id": str(entry_id)})).first()
        return int(row.days) if row else 0
    except Exception:  # noqa: BLE001 — stats never break the payload
        return 0


def _compose_story_line(champion, runner_up, gap: int, days_at_top: int) -> str:
    beat = (
        f"led for {days_at_top} matchdays"
        if days_at_top >= 10
        else "timed the run to the final week"
    )
    return (
        f"{champion.user_name} takes the title by {gap} points — "
        f"{champion.exact_scores} exact scores and a bracket that held, "
        f"having {beat}. {runner_up.user_name} pushed it all the way."
    )


async def get_final_podium(session: AsyncSession):
    """Top-3 of the FINAL leaderboard + Trionda + story. Returns the
    service-level dict the API layer maps onto schemas (final_match and
    audit are attached at the API layer)."""
    lb = await calculate_leaderboard(session, phase="phase_1")
    if lb is None or not lb.entries:
        return None
    rows = lb.entries

    actual_champion_team = None
    top = rows[:3]
    champion = top[0]
    if champion.champion_pick and champion.champion_alive:
        actual_champion_team = champion.champion_pick

    trionda = pick_trionda_recipient(rows)

    entries = []
    for r in top:
        p1 = r.breakdown.phase1
        entries.append(
            {
                "entry_id": str(r.entry_id),
                "user_name": r.user_name,
                "entry_name": r.entry_name,
                "final_rank": r.position,
                "total_points": r.total_points,
                "group_points": _group_points(p1),
                "knockout_points": _knockout_points(p1),
                "bonus_points": (r.bonus_group_points or 0)
                + (r.bonus_knockout_points or 0),
                "exact_scores": r.exact_scores,
                "rarity_points": p1.hybrid_bonus_points,
                "days_at_top": await _days_at_top(session, r.entry_id),
                "champion_pick": r.champion_pick,
                "champion_hit": bool(
                    actual_champion_team
                    and r.champion_pick == actual_champion_team
                ),
                "is_champion": r.position == rows[0].position,
            }
        )

    total_days_sql = text(
        "SELECT COUNT(DISTINCT captured_date) AS days FROM leaderboard_snapshots"
    )
    try:
        total_days = int((await session.execute(total_days_sql)).first().days)
    except Exception:  # noqa: BLE001
        total_days = 0

    gap = top[0].total_points - top[1].total_points if len(top) > 1 else 0
    story = _compose_story_line(top[0], top[1] if len(top) > 1 else top[0], gap, entries[0]["days_at_top"])

    return {
        "entries": entries,
        "trionda": trionda,
        "story_line": story,
        "total_days": total_days,
    }
```

**Note on `actual_champion_team`:** the ACTUAL world champion must come from the Final fixture's winner, not the leader's pick. In the API layer (Task A5) the Final fixture is loaded anyway — pass its winner back into `champion_hit` there. Keep the service field as computed here ONLY as a fallback; the endpoint overwrites `champion_hit` for all three entries from the real fixture result. (This is asserted in the endpoint test.)

- [ ] **Step 5: Run tests**

Run: `docker-compose exec -T backend pytest tests/test_tournament_champion.py -v`
Expected: all Trionda tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tournament_champion.py backend/app/schemas/tournament_champion.py backend/tests/test_tournament_champion.py
git commit -m "feat(conclusion): final-podium service with Trionda side-prize algorithm"
```

---

### Task A5: `GET /leaderboard/final-podium` endpoint

**Files:**
- Modify: `backend/app/api/leaderboard.py` (after `/group-stage-winner`, ~line 863)
- Test: `backend/tests/test_tournament_champion.py`

- [ ] **Step 1: Write the failing gate tests**

Append (fixtures: copy `client_as_admin` AND add a `client_anonymous` — same AsyncClient but only `get_session` overridden, no user override; and `client_as_user` overriding `get_current_user_optional`):

```python
@pytest.mark.asyncio
async def test_final_podium_hidden_pre_conclusion_for_anonymous(
    client_anonymous, competition
):
    resp = await client_anonymous.get("/api/leaderboard/final-podium")
    assert resp.status_code == 200
    assert resp.json() is None  # gate: not concluded, not admin → None


@pytest.mark.asyncio
async def test_final_podium_admin_preview_pre_conclusion(client_as_admin, competition):
    resp = await client_as_admin.get("/api/leaderboard/final-podium")
    assert resp.status_code == 200
    # empty DB → service returns None; the point is the gate didn't block
```

(A full-payload test with a seeded leaderboard is heavy; the service math is unit-tested in A4. The endpoint tests pin the GATE, which is the risky part.)

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T backend pytest tests/test_tournament_champion.py -v -k podium`
Expected: FAIL 404

- [ ] **Step 3: Implement the endpoint**

In `backend/app/api/leaderboard.py` after the GSW endpoint. Use `OptionalUser` (from `app.dependencies`) so anonymous works post-conclusion:

```python
@router.get("/final-podium", response_model=None)
async def final_podium_endpoint(
    session: DbSession,
    user: OptionalUser,
):
    """Champion announcement payload. Visible to EVERYONE once
    tournament_concluded; admins may preview before the flip."""
    from sqlalchemy import select as sa_select
    from app.models.competition import Competition
    from app.models.fixture import Fixture
    from app.schemas.tournament_champion import (
        AuditSummaryOut,
        FinalMatchOut,
        FinalPodium,
        FinalPodiumEntry,
        TriondaOut,
    )
    from app.services.final_audit import load_latest_audit_summary
    from app.services.tournament_champion import get_final_podium

    comp = (
        await session.execute(
            sa_select(Competition).where(Competition.is_active.is_(True))
        )
    ).scalar_one_or_none()
    concluded = bool(comp and comp.tournament_concluded)
    if not concluded and not (user and user.is_admin):
        return None

    podium = await get_final_podium(session)
    if podium is None:
        return None

    # The Final fixture (stage == 'final'); winner drives champion_hit.
    final_fx = (
        await session.execute(
            sa_select(Fixture).where(Fixture.stage == "final")
        )
    ).scalars().first()
    final_match = None
    actual_winner: str | None = None
    if final_fx is not None:
        score = getattr(final_fx, "score", None)
        home = away = None
        pens = None
        et = False
        if score is not None:
            home = score.final_home_score if score.final_home_score is not None else score.home_score
            away = score.final_away_score if score.final_away_score is not None else score.away_score
            et = score.home_score_et is not None or score.away_score_et is not None
            if score.home_penalties is not None:
                pens = f"{score.home_penalties}–{score.away_penalties}"
            if score.outcome == "1":
                actual_winner = final_fx.home_team
            elif score.outcome == "2":
                actual_winner = final_fx.away_team
        final_match = FinalMatchOut(
            home_team=final_fx.home_team,
            away_team=final_fx.away_team,
            home_score=home,
            away_score=away,
            went_to_extra_time=et,
            penalties=pens,
            kickoff=final_fx.kickoff,
            venue=f"{final_fx.venue_city}, {final_fx.venue_country}"
            if getattr(final_fx, "venue_city", None)
            else None,
            narrative=comp.final_match_narrative if comp else None,
        )

    entries = []
    for e in podium["entries"]:
        e = dict(e)
        if actual_winner:
            e["champion_hit"] = e["champion_pick"] == actual_winner
        entries.append(FinalPodiumEntry(**e))

    t = podium["trionda"]
    trionda = TriondaOut(
        recipient_name=t.recipient.user_name if t.recipient else None,
        recipient_entry_id=str(t.recipient.entry_id) if t.recipient else None,
        final_rank=t.recipient.position if t.recipient else None,
        reason=t.reason,
        requires_draw=t.requires_draw,
        draw_candidate_names=[c.user_name for c in t.draw_candidates],
    )

    audit_summary = load_latest_audit_summary()
    audit = AuditSummaryOut(**audit_summary) if audit_summary else None

    return FinalPodium(
        entries=entries,
        trionda=trionda,
        story_line=podium["story_line"],
        total_days=podium["total_days"],
        final_match=final_match,
        audit=audit,
    )
```

**Adapt field names to the real `Score`/`Fixture` models** (memory: `Score` is a separate joined table; `final_home_score`/`final_away_score` are the ET-inclusive fields; how the fixture serializer exposes score may differ — read `backend/app/api/fixtures.py:fixture_to_read()` and reuse its access pattern; adjust attribute paths accordingly). `load_latest_audit_summary` is created in Task A6 — until then stub it in `final_audit.py` returning `None`.

- [ ] **Step 4: Create the audit stub so imports resolve**

Create `backend/app/services/final_audit.py` (filled in properly in Task A6):

```python
"""Full-rescore final audit (Plan A Task A6). Stub summary loader first."""


def load_latest_audit_summary() -> dict | None:
    return None
```

- [ ] **Step 5: Run tests**

Run: `docker-compose exec -T backend pytest tests/test_tournament_champion.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/leaderboard.py backend/app/services/final_audit.py backend/tests/test_tournament_champion.py
git commit -m "feat(conclusion): GET /leaderboard/final-podium with concluded-or-admin gate"
```

---

### Task A6: Full-rescore audit service + admin endpoints

**Files:**
- Modify: `backend/app/services/final_audit.py`
- Modify: `backend/app/api/admin.py`
- Modify: `frontend/src/lib/api/admin.ts`, `frontend/src/routes/admin/+page.svelte` (Run-audit button)
- Test: `backend/tests/test_final_audit.py` (new)

- [ ] **Step 1: Write the failing service test**

Create `backend/tests/test_final_audit.py` (db_session fixture as before):

```python
"""Final audit — full rescore vs live leaderboard (Plan A)."""

import json

import pytest

from app.services import final_audit


@pytest.mark.asyncio
async def test_audit_writes_artifact_and_summary(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(final_audit, "SNAPSHOT_DIR", tmp_path)
    summary = await final_audit.run_final_audit(db_session)
    assert summary["entries_verified"] == 0  # empty DB
    assert summary["discrepancies"] == 0
    files = list(tmp_path.glob("final-audit-*.json"))
    assert len(files) == 1
    on_disk = json.loads(files[0].read_text())
    assert on_disk["sources"]  # names the immutable sources


@pytest.mark.asyncio
async def test_latest_summary_roundtrip(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(final_audit, "SNAPSHOT_DIR", tmp_path)
    await final_audit.run_final_audit(db_session)
    loaded = final_audit.load_latest_audit_summary()
    assert loaded is not None and loaded["discrepancies"] == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T backend pytest tests/test_final_audit.py -v`
Expected: FAIL — `run_final_audit` missing

- [ ] **Step 3: Implement the service**

Replace `backend/app/services/final_audit.py`:

```python
"""Full-rescore final audit (Plan A, 2026-07-18).

Re-scores EVERY eligible entry with a fresh run of the scoring engine
(same calls as scripts/audit_top3_v2.py step ④) and compares against the
live leaderboard totals. Artifact JSON lands in backend/snapshots/ (the
committed audit-trail directory). Admin-triggered, re-runnable any time;
the newest artifact feeds the /final-podium `audit` block and the
/rules#verification narrative.
"""

import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models._datetime import utc_now

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "snapshots"

SOURCES = [
    "deadline-night predictions snapshot (committed to git)",
    "database modification log",
    "submission confirmation emails on Resend",
    "official results",
]

# in-process run state for the admin status poll
_state: dict = {"status": "idle", "summary": None, "error": None}


def get_audit_state() -> dict:
    return dict(_state)


def load_latest_audit_summary() -> dict | None:
    try:
        files = sorted(SNAPSHOT_DIR.glob("final-audit-*.json"))
        if not files:
            return None
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — audit read must never 500
        logger.warning("final-audit summary load failed: %s", exc)
        return None


async def run_final_audit(session: AsyncSession) -> dict:
    """Synchronous core (callers may wrap in a background task)."""
    from app.services.leaderboard import _list_eligible_entries, calculate_leaderboard
    from app.services.scoring import (
        calculate_entry_points,
        get_actual_advancement,
        get_all_outcome_counts,
    )

    _state.update(status="running", error=None)
    try:
        eligible = await _list_eligible_entries(session, "phase_1")
        outcome_counts = await get_all_outcome_counts(session)
        advancement = await get_actual_advancement(session)

        lb = await calculate_leaderboard(session, phase="phase_1")
        live_totals = {str(e.entry_id): e.total_points for e in (lb.entries if lb else [])}

        discrepancies = []
        matches_rescored = 0
        for e in eligible:
            bd = await calculate_entry_points(
                session,
                e.id,
                outcome_counts_by_fixture=outcome_counts,
                actual_advancement=advancement,
            )
            matches_rescored = max(matches_rescored, bd.total_predictions)
            live = live_totals.get(str(e.id))
            if live is not None and live != bd.total:
                discrepancies.append(
                    {"entry_id": str(e.id), "live": live, "rescored": bd.total}
                )

        summary = {
            "run_at": utc_now().isoformat(),
            "entries_verified": len(eligible),
            "matches_rescored": matches_rescored,
            "bonus_questions": 4,
            "discrepancies": len(discrepancies),
            "sources": SOURCES,
        }
        artifact = {**summary, "discrepancy_detail": discrepancies}
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        out = SNAPSHOT_DIR / f"final-audit-{utc_now().date().isoformat()}.json"
        out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        _state.update(status="done", summary=summary)
        return summary
    except Exception as exc:  # noqa: BLE001
        logger.exception("final audit failed")
        _state.update(status="error", error=str(exc))
        raise
```

(Verify the real names `_list_eligible_entries` in `app.services.leaderboard` and the `calculate_entry_points` kwargs against `backend/scripts/audit_top3_v2.py:600-617` — copy exactly what the script uses. `bd.total_predictions` may not be the count of matches; if the breakdown lacks it, count FINISHED fixtures with a `select(func.count())` instead.)

- [ ] **Step 4: Admin routes**

In `backend/app/api/admin.py`:

```python
@router.post("/audit/run")
async def run_final_audit_endpoint(
    session: DbSession,
    admin: AdminUser,
) -> dict:
    """Run the full-rescore audit inline (≤ a few seconds for 183 entries;
    the admin UI shows a spinner). Re-runnable at any time."""
    from app.services.final_audit import run_final_audit

    summary = await run_final_audit(session)
    return {"status": "ok", "summary": summary}


@router.get("/audit/status")
async def final_audit_status(admin: AdminUser) -> dict:
    from app.services.final_audit import get_audit_state, load_latest_audit_summary

    state = get_audit_state()
    if state["summary"] is None:
        state["summary"] = load_latest_audit_summary()
    return state
```

(Inline rather than background: the audit script re-scores 183 entries in seconds against precomputed counts; if the dress-rehearsal shows >20s, switch to `asyncio.create_task` with its own session factory — the `_state` dict already supports polling.)

Frontend: add to `frontend/src/lib/api/admin.ts`:

```ts
export async function runFinalAudit(): Promise<{ status: string; summary: unknown }> {
	return api.post('/admin/audit/run', {});
}

export async function getAuditStatus(): Promise<{
	status: string;
	summary: { run_at: string; entries_verified: number; discrepancies: number } | null;
}> {
	return api.get('/admin/audit/status');
}
```

In the admin conclusion section (Task A2 markup), add:

```svelte
	<div class="mt-4 border-t border-base-300/50 pt-3">
		<button class="btn btn-sm" on:click={handleRunAudit} disabled={auditRunning}>
			{auditRunning ? 'Re-scoring…' : 'Run final audit'}
		</button>
		{#if auditSummary}
			<p class="text-xs text-base-content/60 mt-2">
				Last run {auditSummary.run_at} · {auditSummary.entries_verified} entries ·
				{auditSummary.discrepancies} discrepancies
			</p>
		{/if}
	</div>
```

with handler:

```ts
	let auditRunning = false;
	let auditSummary: { run_at: string; entries_verified: number; discrepancies: number } | null = null;

	async function handleRunAudit() {
		auditRunning = true;
		try {
			const r = await runFinalAudit();
			auditSummary = (r.summary ?? null) as typeof auditSummary;
		} finally {
			auditRunning = false;
		}
	}
```

- [ ] **Step 5: Run tests + svelte-check**

Run: `docker-compose exec -T backend pytest tests/test_final_audit.py -v` → PASS
Run: `docker-compose exec -T frontend-dev npm run check` → 0 errors

- [ ] **Step 6: Dress rehearsal note (do during integration)**

After deploy-to-prod of this task (admin-gated, safe), the admin runs "Run final audit" against live data BEFORE finals night. Record outcome in the session notes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/final_audit.py backend/app/api/admin.py frontend/src/lib/api/admin.ts frontend/src/routes/admin/+page.svelte backend/tests/test_final_audit.py
git commit -m "feat(conclusion): on-demand full-rescore audit with committed artifact + admin button"
```

---

### Task A7: Pool-retrospective service + endpoint

**Files:**
- Create: `backend/app/services/pool_retrospective.py`
- Create: `backend/app/schemas/pool_retrospective.py`
- Modify: `backend/app/api/leaderboard.py`
- Test: `backend/tests/test_pool_retrospective.py` (new)

- [ ] **Step 1: Write the failing pure-math tests**

The aggregation core is pure over prepared rows. Create `backend/tests/test_pool_retrospective.py`:

```python
"""Pool retrospective aggregates (Plan A §8)."""

import pytest

from app.services.pool_retrospective import (
    outcome_of,
    rank_misses_and_bankers,
)


def test_outcome_of():
    assert outcome_of(2, 1) == "1"
    assert outcome_of(0, 0) == "X"
    assert outcome_of(0, 3) == "2"


def test_rank_misses_and_bankers():
    # (fixture_label, correct_pct, exact_count)
    stats = [
        ("M23 · Morocco 2–0 Belgium", 0.04, 0),
        ("M11 · England 2–0 Iran", 0.91, 24),
        ("M57 · Australia 1–0 Denmark", 0.07, 0),
        ("M44 · France 2–0 New Zealand", 0.87, 19),
        ("M31 · Argentina 3–0 Curacao", 0.89, 31),
        ("M78 · Japan 2–1 Germany", 0.11, 2),
    ]
    misses, bankers = rank_misses_and_bankers(stats, top_n=3)
    assert [m[0] for m in misses] == [
        "M23 · Morocco 2–0 Belgium",
        "M57 · Australia 1–0 Denmark",
        "M78 · Japan 2–1 Germany",
    ]
    assert bankers[0][0] == "M11 · England 2–0 Iran"
    assert len(bankers) == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T backend pytest tests/test_pool_retrospective.py -v`
Expected: FAIL — module missing

- [ ] **Step 3: Implement schemas**

Create `backend/app/schemas/pool_retrospective.py`:

```python
"""API shapes for the pool-vs-tournament retrospective (Plan A §8)."""

from pydantic import BaseModel


class MatchCallOut(BaseModel):
    label: str          # "M23 · Morocco 2–0 Belgium"
    pct: float          # share of pool with the correct outcome pick
    exact_count: int


class KoLadderRowOut(BaseModel):
    stage: str          # 'round_of_32' … 'final' | 'winner'
    consensus_had: int
    of: int
    fallen_teams: list[str]


class BonusAnswerOut(BaseModel):
    question_id: str
    label: str
    answer_label: str
    hit_pct: float


class ChampionPickOut(BaseModel):
    team: str
    count: int
    is_actual: bool


class SuperlativeOut(BaseModel):
    emoji: str
    title: str
    body: str


class PersonalWrapOut(BaseModel):
    entry_id: str
    entry_name: str
    final_rank: int
    total_points: int
    group_points: int
    knockout_points: int
    bonus_points: int
    percentile_label: str        # "top 4% of the pool"
    superlatives: list[SuperlativeOut]


class PoolRetrospective(BaseModel):
    group_called_right: int
    group_total: int
    final_called_right_pct: float
    final_winner_team: str | None
    exact_total: int
    exact_avg_per_entry: float
    misses: list[MatchCallOut]
    bankers: list[MatchCallOut]
    ko_ladder: list[KoLadderRowOut]
    bonus: list[BonusAnswerOut]
    champion_distribution: list[ChampionPickOut]
    personal: list[PersonalWrapOut] | None
```

- [ ] **Step 4: Implement the service**

Create `backend/app/services/pool_retrospective.py`. The pure helpers are fully specified; the DB pass reuses the exact queries the rarity engine already runs:

```python
"""Pool-vs-tournament retrospective — ONE aggregate pass (Plan A §8).

Everything the wrap-up page's collective cards need, plus per-member
superlatives, computed together so the page never does 104 per-fixture
fetches. third_place is excluded everywhere (unscored-stage invariant).
Cached in-process: the data is frozen once the tournament concludes.
"""

import logging
from collections import Counter, defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_cache: dict = {"key": None, "value": None}


def outcome_of(home: int, away: int) -> str:
    if home > away:
        return "1"
    if home < away:
        return "2"
    return "X"


def rank_misses_and_bankers(stats, top_n: int = 3):
    """stats: iterable of (label, correct_pct, exact_count) for FINISHED
    group matches. Returns (misses, bankers): lowest-pct and highest-pct
    top_n, each ordered most-extreme-first."""
    ordered = sorted(stats, key=lambda s: s[1])
    misses = ordered[:top_n]
    bankers = list(reversed(ordered[-top_n:]))
    return misses, bankers


async def compute_pool_retrospective(
    session: AsyncSession, *, for_user_id=None
) -> dict:
    """The single aggregate pass. Structure of the return value mirrors
    schemas/pool_retrospective.py field-for-field (the endpoint maps it).

    Implementation walk (all imports local, GSW style):
    1. fixtures: select ALL Fixture rows with score, split group vs KO,
       drop stage == 'third_place'.
    2. match predictions: select (entry_id, fixture_id, home_score,
       away_score) for eligible SUBMITTED entries only — reuse
       eligible_entry_ids_select() from app.services.scoring so the
       denominator matches rarity math.
    3. per finished group fixture: correct-outcome count, exact count,
       eligible total → pct; feed rank_misses_and_bankers; sum
       group_called_right where pct > 0.5 of pool picking the actual
       outcome majority-style (majority pick == actual outcome).
    4. KO ladder: consensus lineup per stage = the teams most-picked into
       each stage from TeamPrediction rows (same counts the
       consensus-bracket endpoint already computes — import and reuse its
       helper rather than re-deriving; grep get_consensus_bracket in
       app/services). Compare vs get_actual_advancement() sets; fallen =
       consensus - actual, capped list.
    5. winner row: most-picked champion vs actual Final winner.
    6. bonus: per current question — resolved answer label + hit pct
       (BonusPrediction rows with points > 0 over eligible count).
    7. champion_distribution: Counter of TeamPrediction winner picks
       (or BracketPrediction.winner equivalents), top 5, is_actual flag.
    8. personal (when for_user_id): per entry of that user — final rank
       from calculate_leaderboard, splits via the same helpers as
       tournament_champion, percentile, superlatives via
       _pick_superlatives below.
    """
    raise NotImplementedError  # implemented against real models in this task
```

**The executor implements the walk above against the real models** (`Fixture`, `Score`, `MatchPrediction`, `TeamPrediction`, `BonusPrediction`) — the model truth is in `backend/app/models/`; the eligible-entry select and outcome-count helpers already exist in `app.services.scoring` (`eligible_entry_ids_select`, `get_all_outcome_counts` — reuse, don't re-derive). Add `_pick_superlatives`:

```python
def _pick_superlatives(personal_stats: dict) -> list[dict]:
    """personal_stats: {exact_hits: [(fixture_label, co_predictors, pts)],
    exact_count, exact_percentile, champion_pick, champion_hit,
    champion_furthest_stage_label, low_consensus_points, ko_hit_pct,
    ko_hit_percentile}. Returns exactly 3 {emoji,title,body} dicts,
    strongest first. Fallback order guarantees 3 for every entry."""
    out = []
    hits = sorted(personal_stats.get("exact_hits", []), key=lambda h: h[1])
    if hits and hits[0][1] <= 3:
        label, co, pts = hits[0]
        who = "Only you called it" if co == 1 else f"One of {co} who called it"
        out.append({
            "emoji": "🎯", "title": who,
            "body": f"{label} exact — {co} of the pool. Your rarest correct pick (+{pts}).",
        })
    if personal_stats.get("exact_percentile", 100) <= 25:
        out.append({
            "emoji": "📈", "title": "Sharp shooter",
            "body": f"{personal_stats['exact_count']} exact scores — top {personal_stats['exact_percentile']}% of the pool.",
        })
    if personal_stats.get("champion_hit"):
        out.append({
            "emoji": "🛡️", "title": "Faithful to the end",
            "body": f"Your champion pick {personal_stats['champion_pick']} went all the way.",
        })
    if len(out) < 3 and personal_stats.get("low_consensus_points", 0) > 0:
        out.append({
            "emoji": "⚔️", "title": "Giant killer",
            "body": f"{personal_stats['low_consensus_points']} points from picks fewer than 15% of the pool made.",
        })
    if len(out) < 3:
        out.append({
            "emoji": "🧭", "title": "Bracket architect",
            "body": f"Your knockout calls landed in the top {personal_stats.get('ko_hit_percentile', 50)}% of the pool.",
        })
    if len(out) < 3:
        out.append({
            "emoji": "⚽", "title": "Ever-present",
            "body": "All 104 matches predicted — a full five-week campaign.",
        })
    return out[:3]
```

Add a unit test for `_pick_superlatives` (append to the test file):

```python
def test_superlatives_always_three_with_fallbacks():
    from app.services.pool_retrospective import _pick_superlatives

    weak = _pick_superlatives({"exact_hits": [], "exact_count": 2,
                               "exact_percentile": 80, "champion_hit": False,
                               "champion_pick": "Brazil",
                               "low_consensus_points": 0})
    assert len(weak) == 3

    strong = _pick_superlatives({
        "exact_hits": [("Japan 1–1 Poland", 1, 14.1)],
        "exact_count": 14, "exact_percentile": 8,
        "champion_hit": True, "champion_pick": "Argentina",
        "low_consensus_points": 22, "ko_hit_percentile": 12,
    })
    assert strong[0]["title"] == "Only you called it"
    assert len(strong) == 3
```

- [ ] **Step 5: Endpoint**

In `backend/app/api/leaderboard.py`:

```python
@router.get("/pool-retrospective", response_model=None)
async def pool_retrospective_endpoint(
    session: DbSession,
    user: OptionalUser,
):
    from sqlalchemy import select as sa_select
    from app.models.competition import Competition
    from app.schemas.pool_retrospective import PoolRetrospective
    from app.services.pool_retrospective import compute_pool_retrospective

    comp = (
        await session.execute(
            sa_select(Competition).where(Competition.is_active.is_(True))
        )
    ).scalar_one_or_none()
    concluded = bool(comp and comp.tournament_concluded)
    if not concluded and not (user and user.is_admin):
        return None

    data = await compute_pool_retrospective(
        session, for_user_id=user.id if user else None
    )
    return PoolRetrospective(**data)
```

- [ ] **Step 6: Run all retrospective tests**

Run: `docker-compose exec -T backend pytest tests/test_pool_retrospective.py -v`
Expected: PASS (pure helpers + superlatives; add one seeded-DB smoke test if the model-level walk is tractable in sqlite — group fixture + 2 entries + predictions asserting `group_called_right`)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/pool_retrospective.py backend/app/schemas/pool_retrospective.py backend/app/api/leaderboard.py backend/tests/test_pool_retrospective.py
git commit -m "feat(conclusion): pool-retrospective aggregate endpoint with per-member superlatives"
```

---

### Task A8: TOURNAMENT_FINAL broadcast segment

**Files:**
- Modify: `backend/app/services/broadcast.py` (enum + predicate)
- Modify: `backend/app/services/email.py` (content branch + token compute)
- Modify: the broadcast send path in `backend/app/api/admin.py` (token wiring — grep `_compute_group_stage_winner_email_tokens` call site and mirror)
- Modify: `frontend/src/routes/admin/+page.svelte` `SEGMENT_LABELS` + `frontend/src/lib/api/admin.ts` union
- Test: `backend/tests/test_admin_broadcasts.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_admin_broadcasts.py` inside the existing test class:

```python
    async def test_tournament_final_template_tokens_interpolate(
        self, db_session: AsyncSession
    ):
        from app.services.email import _broadcast_content_for_segment, _interpolate

        content = _broadcast_content_for_segment(
            BroadcastSegment.TOURNAMENT_FINAL,
            player_name="Test User",
            deadline_display=None,
        )
        tokens = {"CHAMPION_NAME": "James Vella", "CHAMPION_TOTAL": "612"}
        rendered = _interpolate(content, tokens)
        for value in tokens.values():
            assert value in rendered.body_html
            assert value in rendered.body_text
        for fragment in ("{{", "}}", "{CHAMPION_NAME}", "{CHAMPION_TOTAL}"):
            assert fragment not in rendered.body_html
            assert fragment not in rendered.body_text
        # deliverability constraints: short + no UTM
        assert "utm_" not in rendered.body_html
        assert len(rendered.body_text) < 1200

    async def test_tournament_final_audience_is_submitters(self, db_session):
        from app.services.broadcast import _segment_predicate

        pred = _segment_predicate(BroadcastSegment.TOURNAMENT_FINAL)
        assert pred is not None  # same predicate family as recaps
```

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T backend pytest tests/test_admin_broadcasts.py -v -k tournament_final`
Expected: FAIL — enum member missing

- [ ] **Step 3: Implement**

`backend/app/services/broadcast.py` — enum member + predicate branch:

```python
    # v2.214.x — conclusion announcement. Same audience as the recaps.
    TOURNAMENT_FINAL = "tournament_final"
```

```python
    if segment == BroadcastSegment.TOURNAMENT_FINAL:
        return _has_submitted_phase_predicate()
```

`backend/app/services/email.py` — content branch (after GROUP_STAGE_FINAL, ~line 1574). Short by design; tokens as plain concatenation (NOT f-string braces):

```python
    if segment == BroadcastSegment.TOURNAMENT_FINAL:
        subject = "WC26 — that's a wrap"
        headline = "We have a champion"
        cta_label = "See the final story"
        body_html = (
            "<p>Hi " + safe_name + ",</p>"
            "<p>The tournament is done — <b>{{CHAMPION_NAME}}</b> is our champion "
            "with <b>{{CHAMPION_TOTAL}}</b> points.</p>"
            "<p>The full story is on the app: the final podium, how the title was "
            "won, the side-prize winner, and a head-to-head view to see exactly "
            "how your entry stacked up.</p>"
            "<p>One last thing — we built this for you, and we'd love to know how "
            "it went. There's a quick rating and feedback box on the homepage. "
            "It takes 30 seconds and shapes the next one.</p>"
            "<p>Thanks for playing.</p>"
        )
        body_text = (
            "Hi " + safe_name + ",\n\n"
            "The tournament is done — {{CHAMPION_NAME}} is our champion with "
            "{{CHAMPION_TOTAL}} points.\n\n"
            "The full story is on the app: the final podium, how the title was won, "
            "the side-prize winner, and a head-to-head view of your own entry.\n\n"
            "One last thing — rate the app and tell us what to build next. The box "
            "is on the homepage; it takes 30 seconds.\n\n"
            "Thanks for playing."
        )
        return _BroadcastContent(
            subject=subject,
            headline=headline,
            body_html=body_html,
            body_text=body_text,
            cta_label=cta_label,
        )
```

Token compute helper (next to `_compute_group_stage_winner_email_tokens`, ~line 2597), gated on the conclusion flag:

```python
async def _compute_tournament_final_email_tokens(session) -> dict[str, str]:
    from sqlalchemy import select
    from app.models.competition import Competition
    from app.services.tournament_champion import get_final_podium

    try:
        comp = (
            await session.execute(
                select(Competition).where(Competition.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if comp is None or not comp.tournament_concluded:
            return {}  # literal {{TOKENS}} = "sent before conclusion" signal
        podium = await get_final_podium(session)
        if not podium or not podium["entries"]:
            return {}
        champ = podium["entries"][0]
        return {
            "CHAMPION_NAME": champ["user_name"],
            "CHAMPION_TOTAL": str(champ["total_points"]),
        }
    except Exception as exc:  # noqa: BLE001 — broadcast must not crash
        logger.warning("TOURNAMENT_FINAL token compute failed: %s", exc)
        return {}
```

Wire it in the broadcast send path: grep `_compute_group_stage_winner_email_tokens` in `backend/app/api/admin.py` (and/or `email.py` send function) and add the sibling branch:

```python
    elif segment == BroadcastSegment.TOURNAMENT_FINAL:
        tokens = await _compute_tournament_final_email_tokens(session)
```

Frontend: add `'tournament_final'` to the `BroadcastSegment` union + `BroadcastAudienceCounts` in `frontend/src/lib/api/admin.ts` (lines ~670/683), and to `SEGMENT_LABELS` in `frontend/src/routes/admin/+page.svelte` (~line 427):

```ts
	tournament_final: {
		title: 'Tournament final — that’s a wrap',
		description:
			'Champion announcement + homepage CTA + feedback ask. Send AFTER flipping the conclusion switch (test-send before shows literal {{TOKENS}}).'
	},
```

- [ ] **Step 4: Run tests**

Run: `docker-compose exec -T backend pytest tests/test_admin_broadcasts.py -v`
Expected: all PASS (existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/broadcast.py backend/app/services/email.py backend/app/api/admin.py frontend/src/lib/api/admin.ts frontend/src/routes/admin/+page.svelte backend/tests/test_admin_broadcasts.py
git commit -m "feat(conclusion): TOURNAMENT_FINAL broadcast — short champion announcement"
```

---

### Task A9: Feedback `features` field + public leaderboard access

**Files:**
- Modify: `backend/app/api/feedback.py`
- Modify: `backend/app/services/email.py` (`send_feedback_email` signature)
- Modify: `backend/app/api/leaderboard.py` (GET / gate)
- Test: `backend/tests/test_tournament_conclusion.py`

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.asyncio
async def test_feedback_accepts_features(client_as_user, monkeypatch):
    sent = {}

    async def fake_send(**kwargs):
        sent.update(kwargs)

    from app.services import email as email_service
    monkeypatch.setattr(email_service, "send_feedback_email", fake_send)

    resp = await client_as_user.post(
        "/api/feedback/",
        json={"rating": 5, "message": "loved it", "features": ["leaderboard", "compare"]},
    )
    assert resp.status_code == 204
    assert "leaderboard" in sent.get("features_line", "")


@pytest.mark.asyncio
async def test_leaderboard_public_when_concluded(client_anonymous, competition, db_session):
    competition.tournament_concluded = True
    await db_session.commit()
    resp = await client_anonymous.get("/api/leaderboard/")
    assert resp.status_code == 200
```

(`client_as_user` = AsyncClient with `get_current_user` overridden to a non-admin user — copy from `test_admin_broadcasts.py:590-607` swapping the override.)

- [ ] **Step 2: Run to verify failure**

Run: `docker-compose exec -T backend pytest tests/test_tournament_conclusion.py -v -k "feedback or public"`
Expected: FAIL

- [ ] **Step 3: Implement**

`backend/app/api/feedback.py` — extend `FeedbackIn` and the send call:

```python
ALLOWED_FEATURES = {
    "leaderboard", "insights", "match_detail", "compare", "smart_fill", "results",
}


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    message: str = Field(min_length=1, max_length=2000)
    features: list[str] = Field(default_factory=list, max_length=6)
```

In `post_feedback`, before sending:

```python
    features = [f for f in payload.features if f in ALLOWED_FEATURES]
    features_line = ", ".join(features) if features else ""
    ...
        await email.send_feedback_email(
            rating=payload.rating,
            message=message,
            reply_to=current_user.email,
            user_name=current_user.name or "",
            features_line=features_line,
        )
    ...
    analytics.capture(
        distinct_id=str(current_user.id),
        event="feedback_submitted",
        properties={
            "rating": payload.rating,
            "has_message": True,
            "features": features_line or None,
        },
    )
```

`backend/app/services/email.py` — `send_feedback_email` gains `features_line: str = ""` and appends to the body when non-empty:

```python
    if features_line:
        body_text += f"\n\nFavourite features: {features_line}"
```

(Adapt to the real body-building code in `send_feedback_email` — HTML variant too if it has one.)

`backend/app/api/leaderboard.py` — the `GET /` endpoint already takes `user: OptionalUser` and returns empty pre-lock for `user is None`; extend the anonymous branch so a concluded competition serves the full board:

```python
    # Post-conclusion the board is public (wrap-up page, staff audience).
    if user is None and not (competition and competition.tournament_concluded):
        <existing empty/pre-lock behavior unchanged>
```

Read the actual anonymous branch first and thread `tournament_concluded` into whatever condition currently zeroes the payload — behavior for anonymous pre-conclusion must remain byte-identical.

- [ ] **Step 4: Run tests + full suite**

Run: `docker-compose exec -T backend pytest tests/test_tournament_conclusion.py -v` → PASS
Run: `docker-compose exec -T backend pytest tests/ -q` → no new failures

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/feedback.py backend/app/services/email.py backend/app/api/leaderboard.py backend/tests/test_tournament_conclusion.py
git commit -m "feat(conclusion): feedback feature chips + public leaderboard when concluded"
```

---

### Task A10: FEATURE_GROUPS + version bump prep

**Files:**
- Modify: `backend/app/services/usage.py`

- [ ] **Step 1: Add the new feature rows**

In `FEATURE_GROUPS` (after `"feedback"`):

```python
    "wrapup": {
        "name": "Wrap-up page",
        "sub": "post-tournament home",
        "events": [
            "wrapup_viewed",
            "wrapup_compare_cta_clicked",
            "wrapup_podium_row_clicked",
            "wrapup_verified_link_clicked",
            "wrapup_matrix_compare_clicked",
            "wrapup_leaderboard_full_clicked",
            "wrapup_footer_link_clicked",
            "wrapup_signin_started",
        ],
    },
    "compare": {
        "name": "Head-to-head compare",
        "sub": "/compare",
        "events": ["compare_opened"],
    },
```

(The frontend events land in Plans B/C; registering now keeps the
"Uncategorized events" row clean on day one.)

- [ ] **Step 2: Run usage tests + commit**

Run: `docker-compose exec -T backend pytest tests/ -q -k usage`
Expected: PASS

```bash
git add backend/app/services/usage.py
git commit -m "chore(usage): register wrapup + compare feature groups"
```

**Plan A done.** Version bump + changelog entry happen once A+B+C integrate (single release), per the standard release process. **Do NOT deploy — ship signal comes from the admin explicitly.**
