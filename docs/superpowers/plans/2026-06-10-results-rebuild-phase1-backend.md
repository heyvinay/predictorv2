# V4 Results Rebuild — Phase 1: Backend Foundations + Admin Completeness Check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the two additive backend schema fields (`MatchPredictionRead.points`, `CommunityPrediction.rank`) and the admin entry-completeness check (report-only + CSV download) that the V4 Results UI in Phase 2/3 will consume. This phase ships zero user-facing UI to non-admins — only an admin tool that the user runs against prod data before V4 visuals land.

**Architecture:** Three additive deltas to existing endpoints + one new admin service + two new admin endpoints + one new admin modal. No migrations. No schema changes to existing tables. All Python work goes through the existing service layer; the API routes stay thin. Frontend admin UI follows the existing `/admin` pattern: button on the existing page, modal for results, CSV download via a separate endpoint.

**Tech Stack:** FastAPI + SQLModel + Pydantic on the backend, SvelteKit + TypeScript + Tailwind/DaisyUI on the frontend, pytest for backend tests, vitest for frontend logic.

**Spec:** [docs/superpowers/specs/2026-06-10-results-leaderboard-rebuild-design.md](docs/superpowers/specs/2026-06-10-results-leaderboard-rebuild-design.md) — read §Decisions, §Backend changes, §Domain invariants before starting.

**Branch:** `claude/results-page-revamp` (already exists, you're on it).

---

## How to run tests in this worktree

CLAUDE.md documents the worktree-overlay pattern. The running `docker-compose` stack is bound to the **main worktree path** (`C:\Users\vinay\OneDrive - Atlas Insurance PCC\Projects\predictorv2\`), not this Claude worktree. To run tests against your edits:

1. Edit files in this worktree (where you are now).
2. `cp` the changed files into the matching paths in the main worktree.
3. Run `docker-compose exec -T <service> <cmd>` from the main worktree path.
4. Restore main worktree: `git checkout -- <path>` for modified, `rm` for new.
5. Commit in this worktree once main is clean.

For convenience, paths in this plan reference the worktree's own structure (since that's where edits land). When a step says "run pytest," the engineer's responsibility is to overlay-then-run-then-restore per the pattern above.

**Pre-commit gates** every commit must pass:

```bash
docker-compose exec -T backend pytest tests/<your_new_files>.py
docker-compose exec -T frontend-dev npm run check    # MUST be 0 errors
```

---

## File structure (Phase 1)

**Backend — create:**
- `backend/app/services/completeness.py` — entry-completeness service
- `backend/tests/test_match_predictions_points.py` — tests for B.1
- `backend/tests/test_community_predictions_rank.py` — tests for B.3
- `backend/tests/test_completeness.py` — tests for the completeness service + endpoints

**Backend — modify:**
- `backend/app/schemas/prediction.py` — add `PickPointsOut`, extend `MatchPredictionRead.points`, extend `CommunityPrediction.rank`
- `backend/app/api/entry_predictions.py` — wire `points` into `list_match_predictions`
- `backend/app/api/predictions.py` — wire `rank` into `get_community_predictions`
- `backend/app/api/admin.py` — add two new admin endpoints (JSON + CSV)

**Frontend — create:**
- `frontend/src/lib/api/admin.ts` — extend if exists, else create — completeness client
- `frontend/src/lib/types/admin.ts` — extend if exists, else create — completeness types
- `frontend/src/lib/components/admin/CompletenessModal.svelte`

**Frontend — modify:**
- `frontend/src/routes/admin/entries/+page.svelte` — add "Run completeness check" button

---

# Group A — `MatchPredictionRead.points` (B.1)

The Results page's per-fixture Points column reads `prediction.points` directly. Backend computes points for finished fixtures using the existing `compute_match_points` engine, fed by a SINGLE bulk-agreement fetch (not per-fixture).

## Task 1: Add `PickPointsOut` schema and extend `MatchPredictionRead.points`

**Files:**
- Modify: `backend/app/schemas/prediction.py`
- Test: `backend/tests/test_match_predictions_points.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_match_predictions_points.py`:

```python
"""Tests for MatchPredictionRead.points (B.1)."""

from typing import get_args, get_origin

import pytest

from app.schemas.prediction import MatchPredictionRead, PickPointsOut


def test_pick_points_out_has_expected_fields():
    """PickPointsOut carries base, base_kind, rarity, total."""
    pp = PickPointsOut(base=15, base_kind="exact", rarity=3, total=18)
    assert pp.base == 15
    assert pp.base_kind == "exact"
    assert pp.rarity == 3
    assert pp.total == 18


def test_pick_points_out_base_kind_constrained():
    """base_kind only accepts the three documented literals."""
    with pytest.raises(ValueError):
        PickPointsOut(base=0, base_kind="bogus", rarity=0, total=0)


def test_match_prediction_read_points_field_optional_and_defaults_none():
    """MatchPredictionRead.points exists, is optional, defaults to None."""
    fields = MatchPredictionRead.model_fields
    assert "points" in fields, "points field must exist on MatchPredictionRead"
    # Optional → default is None
    assert fields["points"].default is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker-compose exec -T backend pytest backend/tests/test_match_predictions_points.py -v
```

Expected: FAIL on `from app.schemas.prediction import ... PickPointsOut` — ImportError.

- [ ] **Step 3: Implement the schema**

In `backend/app/schemas/prediction.py`, after the existing imports, add the `Literal` import if missing, then add `PickPointsOut` and extend `MatchPredictionRead`. The final file's relevant sections become:

```python
"""Prediction schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.prediction import PredictionPhase
from app.schemas.fixture import FixtureScore


class MatchPredictionCreate(BaseModel):
    """Schema for creating a match prediction."""

    fixture_id: uuid.UUID
    home_score: int = Field(ge=0, le=15)
    away_score: int = Field(ge=0, le=15)


class MatchPredictionUpdate(BaseModel):
    """Schema for updating a match prediction."""

    home_score: int = Field(ge=0, le=15)
    away_score: int = Field(ge=0, le=15)


class PickPointsOut(BaseModel):
    """Per-fixture points decomposition for a finished match.

    `base` is the points earned excluding rarity:
      - "exact"  → correct_outcome + exact_score (e.g. 5+10 = 15)
      - "result" → correct_outcome (e.g. 5)
      - "miss"   → 0
    `rarity` is the rarity bonus on top (0..rarity_cap). `total = base + rarity`.
    """

    base: int
    base_kind: Literal["miss", "result", "exact"]
    rarity: int
    total: int


class MatchPredictionRead(BaseModel):
    """Schema for reading a match prediction."""

    id: uuid.UUID
    fixture_id: uuid.UUID
    home_score: int
    away_score: int
    phase: PredictionPhase
    locked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Include fixture info for display
    home_team: str | None = None
    away_team: str | None = None
    kickoff: datetime | None = None
    is_locked: bool = False

    # Populated by list_match_predictions for FINISHED fixtures; null otherwise.
    # See compute_points_for_finished_fixtures() in services/predictions.py.
    points: PickPointsOut | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec -T backend pytest backend/tests/test_match_predictions_points.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/prediction.py backend/tests/test_match_predictions_points.py
git commit -m "feat(schema): add PickPointsOut + MatchPredictionRead.points (B.1)"
```

---

## Task 2: Add `compute_points_for_finished_fixtures` helper

The helper takes the entry's predictions, the fixtures they joined to, bulk agreements (one query for the whole list), and the scoring config — returns a `dict[fixture_id, PickPointsOut]` for finished fixtures only.

**Files:**
- Modify: `backend/app/services/predictions.py` (add helper near `compute_agreements`)
- Test: `backend/tests/test_match_predictions_points.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_match_predictions_points.py`:

```python
from uuid import uuid4

from app.services.predictions import compute_points_for_finished_fixtures


def _fake_fixture(fixture_id, *, status, home_score=None, away_score=None):
    """Minimal duck-typed Fixture for the pure helper. The helper only
    reads `id`, `status`, and `score.{home_score,away_score}` — passing
    a SimpleNamespace avoids depending on the full SQLModel."""
    from types import SimpleNamespace

    score = (
        SimpleNamespace(home_score=home_score, away_score=away_score)
        if home_score is not None
        else None
    )
    return SimpleNamespace(id=fixture_id, status=status, score=score)


def _fake_pred(fixture_id, h, a):
    from types import SimpleNamespace
    return SimpleNamespace(fixture_id=fixture_id, home_score=h, away_score=a)


SCORING_CONFIG = {
    "mode": "logarithmic",
    "match": {"correct_outcome": 5, "exact_score": 10, "rarity_cap": 10},
}


def test_compute_points_exact_pick():
    """Exact pick on a finished fixture: base_kind='exact', base=15."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="finished", home_score=2, away_score=1)
    pred = _fake_pred(fid, 2, 1)
    agreements = {fid: {"agrees_exact": 1, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    assert fid in result
    out = result[fid]
    assert out.base_kind == "exact"
    assert out.base == 15
    assert out.rarity >= 0  # exact engine value verified separately


def test_compute_points_result_only_pick():
    """Correct-outcome-only pick: base_kind='result', base=5."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="finished", home_score=2, away_score=1)
    pred = _fake_pred(fid, 3, 0)  # home win predicted, home wins, scoreline wrong
    agreements = {fid: {"agrees_exact": 0, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    out = result[fid]
    assert out.base_kind == "result"
    assert out.base == 5


def test_compute_points_miss():
    """Wrong outcome: base_kind='miss', base=0, total=0."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="finished", home_score=2, away_score=1)
    pred = _fake_pred(fid, 0, 3)  # away win predicted, home wins
    agreements = {fid: {"agrees_exact": 0, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    out = result[fid]
    assert out.base_kind == "miss"
    assert out.base == 0
    assert out.total == 0


def test_compute_points_unfinished_fixture_excluded():
    """Unfinished fixture: not in the returned map (caller renders None)."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="scheduled")
    pred = _fake_pred(fid, 2, 1)
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], {}, SCORING_CONFIG
    )
    assert fid not in result


def test_compute_points_live_fixture_excluded():
    """LIVE fixture: not in the returned map (banking is at full-time)."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="live", home_score=1, away_score=0)
    pred = _fake_pred(fid, 2, 1)
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], {}, SCORING_CONFIG
    )
    assert fid not in result


def test_compute_points_total_equals_base_plus_rarity():
    """Invariant: total == base + rarity for every returned entry."""
    fid = uuid4()
    fixture = _fake_fixture(fid, status="finished", home_score=2, away_score=1)
    pred = _fake_pred(fid, 2, 1)
    agreements = {fid: {"agrees_exact": 1, "agrees_outcome": 5, "total": 30}}
    result = compute_points_for_finished_fixtures(
        [(pred, fixture)], agreements, SCORING_CONFIG
    )
    out = result[fid]
    assert out.total == out.base + out.rarity
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker-compose exec -T backend pytest backend/tests/test_match_predictions_points.py -v
```

Expected: ImportError on `compute_points_for_finished_fixtures`.

- [ ] **Step 3: Implement the helper**

In `backend/app/services/predictions.py`, near `compute_agreements`, add:

```python
def compute_points_for_finished_fixtures(
    pred_fixture_pairs,
    agreements_by_fixture: dict,
    scoring_config: dict,
):
    """Compute PickPointsOut for each (pred, fixture) where the fixture is
    FINISHED and has a score row. Returns a map from fixture_id → PickPointsOut.

    Caller is responsible for the bulk-agreement fetch — pass the already-
    computed map keyed by fixture_id. Per-fixture absence is treated as
    {agrees_exact: 0, agrees_outcome: 0, total: 0}.
    """
    from app.schemas.prediction import PickPointsOut
    from app.services.scoring import compute_match_points

    match_cfg = scoring_config.get("match", {})
    outcome_points = int(match_cfg.get("correct_outcome", 5))
    exact_points = int(match_cfg.get("exact_score", 10))
    rarity_cap = int(match_cfg.get("rarity_cap", match_cfg.get("hybrid_cap", 10)))
    mode = str(scoring_config.get("mode", "logarithmic"))

    out: dict = {}
    for pred, fixture in pred_fixture_pairs:
        if str(fixture.status).lower() != "finished":
            continue
        if fixture.score is None:
            continue
        agr = agreements_by_fixture.get(fixture.id, {})
        total_predictors = int(agr.get("total", 0))
        correct_predictors = int(agr.get("agrees_outcome", 0))

        total, correct_outcome, exact_score = compute_match_points(
            mode=mode,
            predicted_home=pred.home_score,
            predicted_away=pred.away_score,
            actual_home=fixture.score.home_score,
            actual_away=fixture.score.away_score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
            outcome_points=outcome_points,
            exact_points=exact_points,
            cap=rarity_cap,
        )

        if exact_score:
            base_kind = "exact"
            base = outcome_points + exact_points
        elif correct_outcome:
            base_kind = "result"
            base = outcome_points
        else:
            base_kind = "miss"
            base = 0

        rarity = total - base
        out[fixture.id] = PickPointsOut(
            base=base, base_kind=base_kind, rarity=rarity, total=total
        )

    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec -T backend pytest backend/tests/test_match_predictions_points.py -v
```

Expected: 9 PASS (3 schema + 6 helper).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/predictions.py backend/tests/test_match_predictions_points.py
git commit -m "feat(predictions): add compute_points_for_finished_fixtures helper"
```

---

## Task 3: Wire `points` into `list_match_predictions`

The API route fetches the entry's match predictions + their fixtures, runs ONE bulk-agreement query, runs ONE config fetch, then maps points into the response.

**Testing approach:** The point-computation logic is unit-tested in Task 2 against the pure helper (`compute_points_for_finished_fixtures`). The wiring in this task is a thin glue layer — verified by manual smoke against the running dev server + regression-test of the existing prediction routes. This matches the existing test pattern in the repo (e.g. `test_community_predictions.py` is schema + service-layer, no AsyncClient).

**Files:**
- Modify: `backend/app/api/entry_predictions.py`

- [ ] **Step 1: Wire the helper into the route**

In `backend/app/api/entry_predictions.py`, modify `list_match_predictions` and `_to_match_read`:

```python
def _to_match_read(pred, fixture, points=None):
    """Map a (MatchPrediction, Fixture) pair to MatchPredictionRead.

    `points` is the PickPointsOut for this fixture (FINISHED only); None
    for not-yet-played and live fixtures.
    """
    return MatchPredictionRead(
        id=pred.id,
        fixture_id=pred.fixture_id,
        home_score=pred.home_score,
        away_score=pred.away_score,
        phase=pred.phase,
        locked_at=pred.locked_at,
        created_at=pred.created_at,
        updated_at=pred.updated_at,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff=fixture.kickoff,
        is_locked=fixture.is_locked(),
        points=points,
    )


@router.get(
    "/{entry_id}/predictions/matches",
    response_model=list[MatchPredictionRead],
)
async def list_match_predictions(
    entry_id: uuid.UUID, session: DbSession, current_user: CurrentUser
) -> list[MatchPredictionRead]:
    _competition, entry = await _get_competition_and_entry_for_view(
        session, entry_id, current_user
    )
    rows = await predictions_service.get_match_predictions(session, entry=entry)

    # Bulk-fetch agreements (one query) + scoring config (one read) so the
    # per-fixture points computation stays O(fixtures), not O(fixtures × entries).
    from app.services.scoring import get_scoring_config
    agreement_rows = await predictions_service.compute_agreements(
        session, entry=entry, fixture_ids=None
    )
    agreements_by_fixture = {a["fixture_id"]: a for a in agreement_rows}
    scoring_config = get_scoring_config()
    points_by_fixture = predictions_service.compute_points_for_finished_fixtures(
        rows, agreements_by_fixture, scoring_config
    )

    return [
        _to_match_read(pred, fixture, points_by_fixture.get(fixture.id))
        for pred, fixture in rows
    ]
```

- [ ] **Step 2: Restart backend and confirm it boots cleanly**

```bash
docker-compose restart backend
docker-compose logs --tail=30 backend
```

Expected: backend boots without import errors. Look for "Application startup complete."

- [ ] **Step 3: Manual smoke test**

In a browser, log in as a user with at least one entry. Open the browser devtools Network tab. Navigate to any page that triggers `GET /api/entries/{entry_id}/predictions/matches` (e.g. the entries wizard). Find the response in Network and confirm:

- Every prediction row has a `points` key.
- For predictions on fixtures with `status = "finished"`, `points` is an object with `base`, `base_kind`, `rarity`, `total`.
- For predictions on fixtures with `status = "scheduled"` or `"live"`, `points` is `null`.

If no finished fixtures exist in your dev DB yet (pre-tournament), force one finished by using the admin score editor at `/admin/sync` — enter a score for any scheduled fixture, save, re-trigger the API call.

Alternatively, hit the endpoint directly. Get a session cookie from your logged-in browser, then:

```bash
curl -s -b "session=<your-session-cookie>" \
  "http://localhost:8000/api/entries/<entry-id>/predictions/matches" \
  | python -m json.tool | head -40
```

- [ ] **Step 4: Run existing prediction tests for regression**

```bash
docker-compose exec -T backend pytest backend/tests/test_entry_predictions_api.py backend/tests/test_entry_predictions_service.py -v
```

Expected: All PASS — no regression on the existing routes from adding the points wiring.

Also re-run the Task 1+2 unit tests:

```bash
docker-compose exec -T backend pytest backend/tests/test_match_predictions_points.py -v
```

Expected: All 9 PASS (schema tests + helper tests, unchanged from Task 2).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/entry_predictions.py
git commit -m "feat(api): populate MatchPredictionRead.points via bulk agreements (B.1)"
```

---

# Group B — `CommunityPrediction.rank` (B.3)

`/community` returns one row per eligible entry's prediction. Adding `rank: int | None` lets the Match Detail pool list show each entry's overall standing without the frontend joining against `/leaderboard`.

## Task 4: Extend `CommunityPrediction.rank` schema

**Files:**
- Modify: `backend/app/schemas/prediction.py`
- Test: `backend/tests/test_community_predictions_rank.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_community_predictions_rank.py`:

```python
"""Tests for CommunityPrediction.rank (B.3)."""

from app.schemas.prediction import CommunityPrediction


def test_community_prediction_rank_field_optional_and_defaults_none():
    """rank exists, is optional, defaults to None."""
    fields = CommunityPrediction.model_fields
    assert "rank" in fields
    assert fields["rank"].default is None


def test_community_prediction_accepts_integer_rank():
    cp = CommunityPrediction(
        user_name="Alice",
        entry_reference="REF1",
        entry_name="Alice's pick",
        home_score=2,
        away_score=1,
        rank=7,
    )
    assert cp.rank == 7


def test_community_prediction_accepts_null_rank():
    cp = CommunityPrediction(
        user_name="Bob",
        entry_reference="REF2",
        entry_name="Bob's pick",
        home_score=0,
        away_score=0,
    )
    assert cp.rank is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker-compose exec -T backend pytest backend/tests/test_community_predictions_rank.py -v
```

Expected: FAIL — `rank` field absent.

- [ ] **Step 3: Add the field**

In `backend/app/schemas/prediction.py`, extend `CommunityPrediction`:

```python
class CommunityPrediction(BaseModel):
    """A single entry's prediction for a match.

    Identified by entry_reference + entry_name + user_name — one row per
    eligible entry, not per user (a user with two entries appears twice
    with distinct references). Visibility is gated by fixture lock /
    finish at the API layer.
    """

    user_name: str
    entry_reference: str
    entry_name: str
    home_score: int
    away_score: int
    # Overall leaderboard rank of this entry at request time. Null when the
    # entry is not in the current ranking (drafts, disabled, pre-tournament
    # before any points are awarded). Populated from the cached leaderboard.
    rank: int | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec -T backend pytest backend/tests/test_community_predictions_rank.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/prediction.py backend/tests/test_community_predictions_rank.py
git commit -m "feat(schema): add CommunityPrediction.rank optional field (B.3)"
```

---

## Task 5: Populate `rank` in `/community` endpoint

**Testing approach:** Schema correctness is unit-tested in Task 4. The wiring here is a leaderboard lookup + dict join — verified by manual smoke against the running dev server plus regression of the existing `/community` test (`test_community_predictions.py`).

**Files:**
- Modify: `backend/app/api/predictions.py`

- [ ] **Step 1: Wire the populator**

In `backend/app/api/predictions.py`, modify `get_community_predictions` to surface `entry_id` from the join and look up rank from the cached leaderboard:

```python
@router.get(
    "/matches/{fixture_id}/community", response_model=CommunityPredictionsResponse
)
async def get_community_predictions(
    fixture_id: uuid.UUID,
    session: DbSession,
    _user: OptionalUser,
) -> CommunityPredictionsResponse:
    """All eligible entries' predictions for a fixture (blind-pool gated).

    Only visible after the fixture's prediction lock (5 min before kickoff)
    or once the match is finished. Returns one row per submitted-or-locked
    entry — a user with two submitted entries appears twice with distinct
    references. Each row includes the entry's current overall leaderboard
    rank (null when the entry is not in the ranking).
    """
    # Load fixture with score.
    fixture_row = await session.execute(
        select(Fixture).options(selectinload(Fixture.score)).where(Fixture.id == fixture_id)
    )
    fixture = fixture_row.scalar_one_or_none()
    if not fixture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found"
        )

    # Blind-pool gate.
    if not fixture.is_locked(LOCK_MINUTES) and fixture.status != MatchStatus.FINISHED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Predictions are not yet visible for this match",
        )

    # Join predictions with entry + user. PredictionEntry.id is surfaced so we
    # can join against the leaderboard for per-row rank below.
    rows = (
        await session.execute(
            select(
                MatchPrediction,
                PredictionEntry,
                User.name,
                User.email,
            )
            .join(
                PredictionEntry,
                MatchPrediction.entry_id == PredictionEntry.id,
            )
            .join(User, PredictionEntry.user_id == User.id)
            .join(
                PredictionEntryPhase,
                (PredictionEntryPhase.entry_id == PredictionEntry.id)
                & (PredictionEntryPhase.phase == MatchPrediction.phase),
            )
            .where(MatchPrediction.fixture_id == fixture_id)
            .where(PredictionEntry.withdrawn_at.is_(None))
            .where(PredictionEntry.is_disabled.is_(False))
            .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
        )
    ).all()

    # One cached leaderboard fetch → rank lookup table.
    from app.services.leaderboard import calculate_leaderboard
    leaderboard = await calculate_leaderboard(session, phase=None)
    rank_by_entry = {e.entry_id: e.position for e in leaderboard.entries}

    predictions = [
        CommunityPrediction(
            user_name=user_name or user_email.split("@")[0],
            entry_reference=entry.reference,
            entry_name=entry.display_name,
            home_score=pred.home_score,
            away_score=pred.away_score,
            rank=rank_by_entry.get(entry.id),
        )
        for pred, entry, user_name, user_email in rows
    ]

    actual = None
    if fixture.status == MatchStatus.FINISHED and fixture.score:
        actual = FixtureScore(
            home_score=fixture.score.home_score,
            away_score=fixture.score.away_score,
            home_score_et=fixture.score.home_score_et,
            away_score_et=fixture.score.away_score_et,
            home_penalties=fixture.score.home_penalties,
            away_penalties=fixture.score.away_penalties,
            outcome=fixture.score.outcome,
        )

    return CommunityPredictionsResponse(
        fixture_id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        predictions=predictions,
        actual=actual,
    )
```

- [ ] **Step 2: Restart backend and confirm it boots cleanly**

```bash
docker-compose restart backend
docker-compose logs --tail=30 backend
```

Expected: backend boots without errors.

- [ ] **Step 3: Manual smoke test**

To exercise the endpoint you need a fixture that's either FINISHED or within 5 minutes of kickoff (the blind-pool gate). The dev environment is usually pre-tournament — use `/admin/sync` to mark a fixture as FINISHED first (admin score editor — enter a score and save).

Then hit the endpoint:

```bash
curl -s http://localhost:8000/api/predictions/matches/<finished-fixture-id>/community \
  | python -m json.tool
```

Verify:

- The response has a `predictions` array.
- Every prediction object has a `rank` key.
- For eligible entries that appear in the leaderboard, `rank` is an integer ≥ 1.
- If any prediction's entry isn't ranked (e.g. tied at zero points pre-tournament), `rank` is `null` — not `0`, not missing.

Also confirm the 403 blind-pool gate still works for a not-yet-locked fixture:

```bash
curl -s -i http://localhost:8000/api/predictions/matches/<scheduled-fixture-id>/community
# Expected: 403 with "Predictions are not yet visible for this match"
```

- [ ] **Step 4: Run existing community tests for regression**

```bash
docker-compose exec -T backend pytest backend/tests/test_community_predictions.py -v
```

Expected: All PASS — schema + blind-pool gating unchanged.

Also re-run the Task 4 unit tests:

```bash
docker-compose exec -T backend pytest backend/tests/test_community_predictions_rank.py -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/predictions.py
git commit -m "feat(api): populate CommunityPrediction.rank from cached leaderboard (B.3)"
```

---

# Group C — Admin completeness check (E.1)

A new service that counts missing picks per eligible entry, plus two endpoints (JSON + CSV) under `/admin/entries/completeness-check`. Admin runs it pre-tournament, gets a CSV, chases users out of band.

## Task 6: Create `completeness.py` service skeleton

**Files:**
- Create: `backend/app/services/completeness.py`
- Test: `backend/tests/test_completeness.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_completeness.py`:

```python
"""Tests for the admin entry-completeness service."""

import pytest

from app.services.completeness import (
    EntryCompletenessResult,
    EntryCompletenessDetail,
    expected_match_count,
    expected_bracket_count,
    expected_bonus_count,
)


@pytest.mark.asyncio
async def test_expected_match_count_uses_group_stage_fixtures(session):
    """expected_match_count returns the number of group-stage fixtures."""
    count = await expected_match_count(session)
    # WC2026 has 72 group-stage fixtures. If the test DB is empty, count == 0.
    assert isinstance(count, int)
    assert count >= 0


def test_expected_bracket_count_sums_stage_quotas():
    """expected_bracket_count returns 87: 24 group_winners + 32 + 16 + 8 + 4 + 2 + 1."""
    assert expected_bracket_count() == 24 + 32 + 16 + 8 + 4 + 2 + 1


def test_expected_bonus_count_matches_yaml_questions():
    """expected_bonus_count returns the number of YAML-configured bonus questions."""
    count = expected_bonus_count()
    assert isinstance(count, int)
    assert count > 0  # currently 4 per CLAUDE.md


def test_entry_completeness_result_schema():
    """Schema accepts the required fields."""
    r = EntryCompletenessResult(
        entry_id="00000000-0000-0000-0000-000000000001",
        entry_name="Test",
        user_name="Tester",
        user_email="t@example.com",
        missing_match_picks=3,
        missing_bracket_picks=5,
        missing_bonus_picks=1,
        is_complete=False,
    )
    assert r.is_complete is False
    assert r.missing_match_picks == 3


def test_entry_completeness_result_detail_optional():
    """detail field is optional, defaults to None."""
    r = EntryCompletenessResult(
        entry_id="00000000-0000-0000-0000-000000000001",
        entry_name="Test",
        user_name="Tester",
        user_email="t@example.com",
        missing_match_picks=0,
        missing_bracket_picks=0,
        missing_bonus_picks=0,
        is_complete=True,
    )
    assert r.detail is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker-compose exec -T backend pytest backend/tests/test_completeness.py -v
```

Expected: ImportError on `app.services.completeness`.

- [ ] **Step 3: Implement the skeleton**

Create `backend/app/services/completeness.py`:

```python
"""Entry-completeness service.

Per CLAUDE.md, all SUBMITTED + eligible entries MUST have every required
pick. This module computes per-entry missing counts so an admin can chase
gaps before the tournament starts. Report-only — no enforcement,
no auto-disable.
"""

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from app.models.entry import EntryStatus, PredictionEntry, PredictionEntryPhase
from app.models.fixture import Fixture
from app.models.prediction import (
    BonusPrediction,
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
)
from app.services.bonus import get_questions as get_bonus_questions


class EntryCompletenessDetail(BaseModel):
    """Drill-down detail returned only when ?detail=true."""

    missing_fixture_ids: list[uuid.UUID] = []
    missing_bracket: dict[str, int] = {}   # stage → missing count
    missing_bonus_ids: list[str] = []


class EntryCompletenessResult(BaseModel):
    """One row per eligible entry."""

    entry_id: uuid.UUID
    entry_name: str
    user_name: str
    user_email: str
    missing_match_picks: int
    missing_bracket_picks: int
    missing_bonus_picks: int
    is_complete: bool
    detail: EntryCompletenessDetail | None = None


# Per-stage expected pick counts. group_winners is 12 groups × 2 positions = 24.
# round_of_32 onwards follows the bracket geometry (32, 16, 8, 4, 2, 1).
_BRACKET_EXPECTED: dict[str, int] = {
    "group_winners": 24,
    "round_of_32": 32,
    "round_of_16": 16,
    "quarter_final": 8,
    "semi_final": 4,
    "final": 2,
    "winner": 1,
}


async def expected_match_count(session: AsyncSession) -> int:
    """Number of group-stage fixtures the entry must predict on."""
    result = await session.execute(
        select(func.count(Fixture.id)).where(Fixture.stage == "group")
    )
    return int(result.scalar_one())


def expected_bracket_count() -> int:
    """Sum of stage-expected counts (87 for WC2026)."""
    return sum(_BRACKET_EXPECTED.values())


def expected_bonus_count() -> int:
    """Number of bonus questions defined in the YAML."""
    return len(get_bonus_questions())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec -T backend pytest backend/tests/test_completeness.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/completeness.py backend/tests/test_completeness.py
git commit -m "feat(completeness): scaffold service module with expected-count helpers"
```

---

## Task 7: Implement bulk-completeness query

The bulk function returns one `EntryCompletenessResult` per eligible entry. Uses three SQL aggregates (match / bracket / bonus) joined against the entry table. **NOT** per-entry iteration.

**Testing approach:** This IS the load-bearing correctness surface (admin emails users based on these counts — wrong = embarrassing). DB-level tests using an inline in-memory SQLite session, following the existing repo pattern in `test_entry_predictions_api.py:29-80`. Single rich scenario fixture covering all branches in one setup.

**Files:**
- Modify: `backend/app/services/completeness.py`
- Modify: `backend/tests/test_completeness.py` (replace top of file with DB scaffolding + extend)

- [ ] **Step 1: Replace the test file top with DB scaffolding + scenario fixture**

Open `backend/tests/test_completeness.py`. **Replace the existing top of the file** (the imports block + the 5 schema/helper tests from Task 6) with the following expanded version. The pure-schema tests are preserved at the bottom unchanged; what's new is the DB engine fixture + the scenario factory:

```python
"""Tests for the admin entry-completeness service."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers all SQLModel tables for metadata
from app.models.competition import Competition
from app.models.entry import (
    EntryStatus,
    PredictionEntry,
    PredictionEntryPhase,
)
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import (
    BonusPrediction,
    MatchPrediction,
    PredictionPhase,
    TeamPrediction,
)
from app.models.user import AuthProvider, User
from app.services.bonus import get_questions as get_bonus_questions
from app.services.completeness import (
    EntryCompletenessDetail,
    EntryCompletenessResult,
    check_all_eligible_entries,
    expected_bracket_count,
    expected_bonus_count,
    expected_match_count,
)


# ─── DB session fixture ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """In-memory SQLite session for one test. Tables created fresh."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


# ─── Factory helpers (private — used only by the scenario fixture below) ──


async def _make_competition(session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC2026",
        external_id="WC2026",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        max_entries_per_user=5,
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _make_user(session: AsyncSession, email: str, name: str) -> User:
    u = User(
        email=email,
        name=name,
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _make_group_fixture(
    session: AsyncSession,
    competition: Competition,
    match_number: int,
    home: str,
    away: str,
) -> Fixture:
    f = Fixture(
        competition_id=competition.id,
        home_team=home,
        away_team=away,
        kickoff=datetime(2026, 6, 11, 18, 0, tzinfo=timezone.utc)
        + timedelta(hours=match_number),
        stage="group",
        group="A",
        match_number=match_number,
        status=MatchStatus.SCHEDULED,
    )
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


async def _make_entry(
    session: AsyncSession,
    user: User,
    competition: Competition,
    *,
    status: EntryStatus = EntryStatus.SUBMITTED,
    is_disabled: bool = False,
    withdrawn: bool = False,
) -> PredictionEntry:
    entry = PredictionEntry(
        user_id=user.id,
        competition_id=competition.id,
        display_name=f"{user.name}'s entry",
        reference=f"REF-{uuid4().hex[:8]}",
        is_disabled=is_disabled,
        withdrawn_at=datetime.now(timezone.utc) if withdrawn else None,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    phase_row = PredictionEntryPhase(
        entry_id=entry.id,
        phase=PredictionPhase.PHASE_1,
        status=status,
    )
    session.add(phase_row)
    await session.commit()
    return entry


async def _add_match_picks(
    session: AsyncSession,
    entry: PredictionEntry,
    fixtures: list[Fixture],
) -> None:
    for f in fixtures:
        session.add(
            MatchPrediction(
                entry_id=entry.id,
                fixture_id=f.id,
                phase=PredictionPhase.PHASE_1,
                home_score=1,
                away_score=0,
            )
        )
    await session.commit()


async def _add_bracket_picks(
    session: AsyncSession,
    entry: PredictionEntry,
    *,
    full: bool = True,
) -> None:
    """Add bracket picks. full=True populates all 87 expected picks
    (24 group_winners + 32 R32 + 16 R16 + 8 QF + 4 SF + 2 Final + 1 Winner).
    full=False skips R32 entirely (leaves 32 missing)."""
    stages = {
        "group_winners": 24,
        "round_of_32": 32 if full else 0,
        "round_of_16": 16,
        "quarter_final": 8,
        "semi_final": 4,
        "final": 2,
        "winner": 1,
    }
    for stage, count in stages.items():
        for i in range(count):
            session.add(
                TeamPrediction(
                    entry_id=entry.id,
                    team=f"Team-{stage}-{i}",
                    stage=stage,
                    phase=PredictionPhase.PHASE_1,
                )
            )
    await session.commit()


async def _add_bonus_picks(
    session: AsyncSession,
    entry: PredictionEntry,
) -> None:
    for q in get_bonus_questions():
        session.add(
            BonusPrediction(
                entry_id=entry.id,
                question_id=q.id,
                phase=PredictionPhase.PHASE_1,
                answer="placeholder",
            )
        )
    await session.commit()


# ─── Scenario fixture — one DB state covering every branch ─────────────


@pytest_asyncio.fixture
async def completeness_scenario(db_session: AsyncSession):
    """Build a DB containing one of each entry shape we test against:

    - complete_entry: all picks present, eligible. is_complete=True.
    - missing_match: missing 3 of 10 group picks. is_complete=False.
    - missing_bracket: missing all 32 R32 picks. is_complete=False.
    - disabled_entry: complete but is_disabled=True. Excluded.
    - withdrawn_entry: complete but withdrawn. Excluded.

    Group-stage fixture count is 10 (proxy for 72 — the math is the same).
    """
    comp = await _make_competition(db_session)
    fixtures = [
        await _make_group_fixture(db_session, comp, i, f"H{i}", f"A{i}")
        for i in range(1, 11)
    ]

    users = {}
    for slug, email in [
        ("complete", "complete@test"),
        ("missing_match", "mm@test"),
        ("missing_bracket", "mb@test"),
        ("disabled", "dis@test"),
        ("withdrawn", "wdr@test"),
    ]:
        users[slug] = await _make_user(db_session, email, slug.title())

    entries = {}

    entries["complete"] = await _make_entry(db_session, users["complete"], comp)
    await _add_match_picks(db_session, entries["complete"], fixtures)
    await _add_bracket_picks(db_session, entries["complete"], full=True)
    await _add_bonus_picks(db_session, entries["complete"])

    entries["missing_match"] = await _make_entry(
        db_session, users["missing_match"], comp
    )
    await _add_match_picks(db_session, entries["missing_match"], fixtures[:7])  # 3 missing
    await _add_bracket_picks(db_session, entries["missing_match"], full=True)
    await _add_bonus_picks(db_session, entries["missing_match"])

    entries["missing_bracket"] = await _make_entry(
        db_session, users["missing_bracket"], comp
    )
    await _add_match_picks(db_session, entries["missing_bracket"], fixtures)
    await _add_bracket_picks(db_session, entries["missing_bracket"], full=False)  # 32 missing
    await _add_bonus_picks(db_session, entries["missing_bracket"])

    entries["disabled"] = await _make_entry(
        db_session, users["disabled"], comp, is_disabled=True
    )
    await _add_match_picks(db_session, entries["disabled"], fixtures)
    await _add_bracket_picks(db_session, entries["disabled"], full=True)
    await _add_bonus_picks(db_session, entries["disabled"])

    entries["withdrawn"] = await _make_entry(
        db_session, users["withdrawn"], comp, withdrawn=True
    )
    await _add_match_picks(db_session, entries["withdrawn"], fixtures)
    await _add_bracket_picks(db_session, entries["withdrawn"], full=True)
    await _add_bonus_picks(db_session, entries["withdrawn"])

    return entries


# ─── Tests ────────────────────────────────────────────────────────────


def test_pick_points_out_unused_here_just_pure_schema_unit():
    """Sentinel — the schema-only tests in this file don't need the DB."""
    pass


@pytest.mark.asyncio
async def test_expected_match_count_uses_group_stage_fixtures(db_session):
    """expected_match_count returns the number of group-stage fixtures."""
    count = await expected_match_count(db_session)
    assert isinstance(count, int)
    assert count >= 0


def test_expected_bracket_count_sums_stage_quotas():
    """expected_bracket_count returns 87."""
    assert expected_bracket_count() == 24 + 32 + 16 + 8 + 4 + 2 + 1


def test_expected_bonus_count_matches_yaml_questions():
    """expected_bonus_count returns the number of YAML-configured bonus questions."""
    count = expected_bonus_count()
    assert isinstance(count, int)
    assert count > 0


def test_entry_completeness_result_schema():
    """Schema accepts the required fields."""
    r = EntryCompletenessResult(
        entry_id=uuid4(),
        entry_name="Test",
        user_name="Tester",
        user_email="t@example.com",
        missing_match_picks=3,
        missing_bracket_picks=5,
        missing_bonus_picks=1,
        is_complete=False,
    )
    assert r.is_complete is False
    assert r.missing_match_picks == 3


def test_entry_completeness_result_detail_optional():
    """detail field is optional, defaults to None."""
    r = EntryCompletenessResult(
        entry_id=uuid4(),
        entry_name="Test",
        user_name="Tester",
        user_email="t@example.com",
        missing_match_picks=0,
        missing_bracket_picks=0,
        missing_bonus_picks=0,
        is_complete=True,
    )
    assert r.detail is None


# ─── DB-level tests for check_all_eligible_entries ────────────────────


@pytest.mark.asyncio
async def test_check_all_eligible_entries_categorizes_correctly(
    db_session, completeness_scenario
):
    """Single rich scenario hits every branch in one go.

    Expected: 3 eligible entries surface (complete, missing_match, missing_bracket).
    Disabled and withdrawn are excluded entirely.
    """
    results = await check_all_eligible_entries(db_session)
    by_id = {r.entry_id: r for r in results}

    # Disabled + withdrawn → excluded.
    assert completeness_scenario["disabled"].id not in by_id
    assert completeness_scenario["withdrawn"].id not in by_id

    # Complete entry → all zeros, is_complete=True.
    complete = by_id[completeness_scenario["complete"].id]
    assert complete.missing_match_picks == 0
    assert complete.missing_bracket_picks == 0
    assert complete.missing_bonus_picks == 0
    assert complete.is_complete is True

    # Missing 3 of 10 group picks.
    mm = by_id[completeness_scenario["missing_match"].id]
    assert mm.missing_match_picks == 3
    assert mm.is_complete is False

    # Missing 32 R32 picks → bracket gap 32.
    mb = by_id[completeness_scenario["missing_bracket"].id]
    assert mb.missing_bracket_picks == 32
    assert mb.is_complete is False


@pytest.mark.asyncio
async def test_check_all_eligible_entries_detail_breakdown(
    db_session, completeness_scenario
):
    """detail=True populates per-fixture / per-stage drill-down."""
    results = await check_all_eligible_entries(db_session, detail=True)
    by_id = {r.entry_id: r for r in results}

    mm = by_id[completeness_scenario["missing_match"].id]
    assert mm.detail is not None
    assert len(mm.detail.missing_fixture_ids) == 3

    mb = by_id[completeness_scenario["missing_bracket"].id]
    assert mb.detail is not None
    assert mb.detail.missing_bracket.get("round_of_32") == 32
```

This replaces the entire content of `test_completeness.py` written in Task 6, expanding it with the scenario scaffolding. The pure-schema tests from Task 6 still pass — they're preserved at the same locations.

- [ ] **Step 2: Run test to verify it fails**

```bash
docker-compose exec -T backend pytest backend/tests/test_completeness.py -v
```

Expected: ImportError on `check_all_eligible_entries`.

- [ ] **Step 3: Implement the bulk function**

Append to `backend/app/services/completeness.py`:

```python
async def check_all_eligible_entries(
    session: AsyncSession,
    *,
    detail: bool = False,
) -> list[EntryCompletenessResult]:
    """For every SUBMITTED + not-disabled + not-withdrawn entry on the
    active competition, count missing picks across match / bracket / bonus
    categories. Single-pass per category; returns one row per entry.
    """
    from app.models.user import User

    # 1. Load eligible entries with owner info. Filter to PHASE_1 only
    # (single-phase invariant; CLAUDE.md).
    eligible_query = (
        select(PredictionEntry, User.name, User.email)
        .join(User, PredictionEntry.user_id == User.id)
        .join(
            PredictionEntryPhase,
            (PredictionEntryPhase.entry_id == PredictionEntry.id)
            & (PredictionEntryPhase.phase == PredictionPhase.PHASE_1),
        )
        .where(PredictionEntry.is_disabled.is_(False))
        .where(PredictionEntry.withdrawn_at.is_(None))
        .where(PredictionEntryPhase.status == EntryStatus.SUBMITTED)
    )
    eligible_rows = (await session.execute(eligible_query)).all()
    if not eligible_rows:
        return []

    entry_ids = [e.id for (e, _name, _email) in eligible_rows]
    by_entry_owner = {e.id: (e, name or email.split("@")[0], email) for (e, name, email) in eligible_rows}

    # 2. Match-pick counts per entry (one query).
    match_query = (
        select(MatchPrediction.entry_id, func.count(MatchPrediction.id))
        .where(MatchPrediction.entry_id.in_(entry_ids))
        .where(MatchPrediction.phase == PredictionPhase.PHASE_1)
        .group_by(MatchPrediction.entry_id)
    )
    match_counts = {eid: int(c) for eid, c in (await session.execute(match_query)).all()}

    # 3. Bracket-pick counts per entry per stage (one query).
    bracket_query = (
        select(TeamPrediction.entry_id, TeamPrediction.stage, func.count(TeamPrediction.id))
        .where(TeamPrediction.entry_id.in_(entry_ids))
        .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
        .group_by(TeamPrediction.entry_id, TeamPrediction.stage)
    )
    bracket_rows = (await session.execute(bracket_query)).all()
    bracket_counts_by_entry: dict[uuid.UUID, dict[str, int]] = {}
    for eid, stage, c in bracket_rows:
        bracket_counts_by_entry.setdefault(eid, {})[stage] = int(c)

    # 4. Bonus-pick counts per entry (one query).
    bonus_query = (
        select(BonusPrediction.entry_id, func.count(BonusPrediction.id))
        .where(BonusPrediction.entry_id.in_(entry_ids))
        .where(BonusPrediction.phase == PredictionPhase.PHASE_1)
        .group_by(BonusPrediction.entry_id)
    )
    bonus_counts = {eid: int(c) for eid, c in (await session.execute(bonus_query)).all()}

    # 5. Expected counts.
    expected_matches = await expected_match_count(session)
    expected_bracket = expected_bracket_count()
    expected_bonus = expected_bonus_count()

    # 6. Optional detail — only computed when requested, per-entry, per-category.
    detail_by_entry: dict[uuid.UUID, EntryCompletenessDetail] = {}
    if detail:
        # Missing fixtures per entry.
        group_fixture_ids = {
            f for (f,) in (
                await session.execute(
                    select(Fixture.id).where(Fixture.stage == "group")
                )
            ).all()
        }
        picked_fixtures_by_entry: dict[uuid.UUID, set] = {}
        for eid, fid in (
            await session.execute(
                select(MatchPrediction.entry_id, MatchPrediction.fixture_id)
                .where(MatchPrediction.entry_id.in_(entry_ids))
                .where(MatchPrediction.phase == PredictionPhase.PHASE_1)
            )
        ).all():
            picked_fixtures_by_entry.setdefault(eid, set()).add(fid)

        all_bonus_ids = {q.id for q in get_bonus_questions()}
        picked_bonus_by_entry: dict[uuid.UUID, set] = {}
        for eid, qid in (
            await session.execute(
                select(BonusPrediction.entry_id, BonusPrediction.question_id)
                .where(BonusPrediction.entry_id.in_(entry_ids))
                .where(BonusPrediction.phase == PredictionPhase.PHASE_1)
            )
        ).all():
            picked_bonus_by_entry.setdefault(eid, set()).add(qid)

        for eid in entry_ids:
            missing_fixtures = list(
                group_fixture_ids - picked_fixtures_by_entry.get(eid, set())
            )
            stage_actual = bracket_counts_by_entry.get(eid, {})
            missing_bracket_by_stage = {
                stage: _BRACKET_EXPECTED[stage] - stage_actual.get(stage, 0)
                for stage in _BRACKET_EXPECTED
                if _BRACKET_EXPECTED[stage] - stage_actual.get(stage, 0) > 0
            }
            missing_bonus = list(all_bonus_ids - picked_bonus_by_entry.get(eid, set()))
            detail_by_entry[eid] = EntryCompletenessDetail(
                missing_fixture_ids=missing_fixtures,
                missing_bracket=missing_bracket_by_stage,
                missing_bonus_ids=missing_bonus,
            )

    # 7. Compose results.
    out: list[EntryCompletenessResult] = []
    for eid in entry_ids:
        entry, name, email = by_entry_owner[eid]
        missing_match = max(0, expected_matches - match_counts.get(eid, 0))
        actual_bracket = sum(bracket_counts_by_entry.get(eid, {}).values())
        missing_bracket = max(0, expected_bracket - actual_bracket)
        missing_bonus = max(0, expected_bonus - bonus_counts.get(eid, 0))
        is_complete = missing_match == 0 and missing_bracket == 0 and missing_bonus == 0
        out.append(
            EntryCompletenessResult(
                entry_id=eid,
                entry_name=entry.display_name,
                user_name=name,
                user_email=email,
                missing_match_picks=missing_match,
                missing_bracket_picks=missing_bracket,
                missing_bonus_picks=missing_bonus,
                is_complete=is_complete,
                detail=detail_by_entry.get(eid) if detail else None,
            )
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker-compose exec -T backend pytest backend/tests/test_completeness.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/completeness.py backend/tests/test_completeness.py
git commit -m "feat(completeness): bulk per-entry completeness check (E.1 service)"
```

---

## Task 8: Add JSON endpoint

**Testing approach:** Service-layer correctness is verified by Task 7's DB-level tests. The route is a thin admin-gated wrapper — verified by manual smoke (admin returns data, non-admin returns 403) plus FastAPI auto-validation of the response model.

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] **Step 1: Add the imports + endpoint**

In `backend/app/api/admin.py`:

1. Confirm `Query` is imported from `fastapi` at the top of the file. If not, add: `from fastapi import APIRouter, HTTPException, Query, status`.
2. Confirm `AdminUser` and `DbSession` are imported from `app.dependencies`. If not, add them.
3. Add the new import block (place near other service imports):

```python
from app.services.completeness import (
    EntryCompletenessResult,
    check_all_eligible_entries,
)
```

4. Add the endpoint at the bottom of the admin router section:

```python
@router.get(
    "/entries/completeness-check",
    response_model=list[EntryCompletenessResult],
)
async def admin_entries_completeness_check(
    session: DbSession,
    _admin: AdminUser,
    detail: bool = Query(False, description="Include per-fixture / per-stage drill-down"),
) -> list[EntryCompletenessResult]:
    """Report-only check of pick fullness for every eligible entry.

    Returns ALL eligible entries; the frontend filters to incompletes for
    display. Admin-only.
    """
    return await check_all_eligible_entries(session, detail=detail)
```

- [ ] **Step 2: Restart backend and confirm it boots cleanly**

```bash
docker-compose restart backend
docker-compose logs --tail=30 backend
```

Expected: backend boots without errors.

- [ ] **Step 3: Manual smoke test — admin returns 200**

Log in to the dev app as an admin user. Grab the session cookie from devtools. Hit the endpoint:

```bash
curl -s -b "session=<admin-session-cookie>" \
  "http://localhost:8000/api/admin/entries/completeness-check" \
  | python -m json.tool | head -40
```

Expected: HTTP 200, JSON array. Each element has keys `entry_id`, `entry_name`, `user_name`, `user_email`, `missing_match_picks`, `missing_bracket_picks`, `missing_bonus_picks`, `is_complete`, `detail`.

Also test the `detail=true` variant:

```bash
curl -s -b "session=<admin-session-cookie>" \
  "http://localhost:8000/api/admin/entries/completeness-check?detail=true" \
  | python -m json.tool | head -60
```

Expected: rows with `is_complete: false` have a `detail` object containing `missing_fixture_ids`, `missing_bracket`, `missing_bonus_ids`. Rows with `is_complete: true` have `detail: null` (or, less commonly, an empty detail).

- [ ] **Step 4: Manual smoke test — non-admin returns 403**

Log in as a non-admin user (or sign out and use the public session). Get that session cookie. Hit the endpoint:

```bash
curl -s -i -b "session=<non-admin-session-cookie>" \
  "http://localhost:8000/api/admin/entries/completeness-check"
```

Expected: HTTP 403 with the standard "admin required" error body. The same as other admin endpoints in this app.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add GET /api/admin/entries/completeness-check (E.1)"
```

---

## Task 9: Add CSV endpoint

**Testing approach:** Same as Task 8 — manual smoke. CSV-formatting correctness is a thin csv.writer wrap; service-layer correctness already verified in Task 7.

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] **Step 1: Add the imports + CSV endpoint**

In `backend/app/api/admin.py`, near the top, add (if not already present):

```python
import csv
import io

from fastapi.responses import StreamingResponse
```

Then add the CSV endpoint near the JSON one from Task 8:

```python
import csv
import io

from fastapi.responses import StreamingResponse


@router.get("/entries/completeness-check.csv")
async def admin_entries_completeness_check_csv(
    session: DbSession,
    _admin: AdminUser,
) -> StreamingResponse:
    """Same check as the JSON endpoint, formatted as CSV. Only includes
    incomplete entries. One row per incomplete entry. Admin-only."""
    rows = await check_all_eligible_entries(session, detail=False)
    incompletes = [r for r in rows if not r.is_complete]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "entry_id",
        "entry_name",
        "user_name",
        "user_email",
        "missing_match_picks",
        "missing_bracket_picks",
        "missing_bonus_picks",
        "total_missing",
    ])
    for r in incompletes:
        total = (
            r.missing_match_picks
            + r.missing_bracket_picks
            + r.missing_bonus_picks
        )
        writer.writerow([
            str(r.entry_id),
            r.entry_name,
            r.user_name,
            r.user_email,
            r.missing_match_picks,
            r.missing_bracket_picks,
            r.missing_bonus_picks,
            total,
        ])

    csv_bytes = buf.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="entry-completeness.csv"'
            )
        },
    )
```

- [ ] **Step 2: Restart backend and confirm it boots cleanly**

```bash
docker-compose restart backend
docker-compose logs --tail=30 backend
```

Expected: backend boots without errors.

- [ ] **Step 3: Manual smoke test — admin downloads CSV**

As an admin user (use the session cookie from Task 8 smoke):

```bash
curl -s -b "session=<admin-session-cookie>" \
  "http://localhost:8000/api/admin/entries/completeness-check.csv" \
  -o /tmp/completeness.csv
cat /tmp/completeness.csv
```

Verify:

- First line is the header: `entry_id,entry_name,user_name,user_email,missing_match_picks,missing_bracket_picks,missing_bonus_picks,total_missing`
- Each subsequent row corresponds to an INCOMPLETE entry. Complete entries do NOT appear.
- `total_missing` equals the sum of the three missing-* columns.

Also confirm the response headers signal a file download:

```bash
curl -s -i -b "session=<admin-session-cookie>" \
  "http://localhost:8000/api/admin/entries/completeness-check.csv" \
  | head -10
```

Expected to include:

```
content-type: text/csv; charset=utf-8
content-disposition: attachment; filename="entry-completeness.csv"
```

- [ ] **Step 4: Manual smoke test — non-admin gets 403**

```bash
curl -s -i -b "session=<non-admin-session-cookie>" \
  "http://localhost:8000/api/admin/entries/completeness-check.csv"
```

Expected: HTTP 403.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add GET /api/admin/entries/completeness-check.csv (E.1)"
```

---

# Group D — Admin frontend

The admin UI is a button on `/admin/entries` that opens a modal with the incompletes table and a CSV download.

## Task 10: Add TypeScript types

**Files:**
- Modify or create: `frontend/src/lib/types/admin.ts`

- [ ] **Step 1: Add the types**

Append (or create new file with) the following to `frontend/src/lib/types/admin.ts`:

```typescript
export interface EntryCompletenessDetail {
	missing_fixture_ids: string[];
	missing_bracket: Record<string, number>;
	missing_bonus_ids: string[];
}

export interface EntryCompletenessResult {
	entry_id: string;
	entry_name: string;
	user_name: string;
	user_email: string;
	missing_match_picks: number;
	missing_bracket_picks: number;
	missing_bonus_picks: number;
	is_complete: boolean;
	detail: EntryCompletenessDetail | null;
}
```

If the file already exists, append. If it doesn't, create. If types live in a different file by repo convention, follow the existing pattern.

- [ ] **Step 2: Verify type-check passes**

```bash
docker-compose exec -T frontend-dev npm run check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types/admin.ts
git commit -m "feat(types): add EntryCompletenessResult/Detail types"
```

---

## Task 11: Add API client helper

**Files:**
- Modify or create: `frontend/src/lib/api/admin.ts`

- [ ] **Step 1: Add the client**

Append (or create new file) `frontend/src/lib/api/admin.ts`:

```typescript
import type { EntryCompletenessResult } from '$lib/types/admin';

/** GET /api/admin/entries/completeness-check */
export async function fetchCompletenessCheck(
	detail = false
): Promise<EntryCompletenessResult[]> {
	const params = new URLSearchParams();
	if (detail) params.set('detail', 'true');
	const url = `/api/admin/entries/completeness-check${
		params.toString() ? '?' + params.toString() : ''
	}`;
	const resp = await fetch(url, { credentials: 'include' });
	if (!resp.ok) {
		throw new Error(`Completeness check failed: ${resp.status}`);
	}
	return resp.json();
}

/** Build a URL the browser can hit to download the CSV. The endpoint
 * sets Content-Disposition: attachment, so window.location.href is
 * sufficient — no fetch needed. */
export function completenessCsvUrl(): string {
	return '/api/admin/entries/completeness-check.csv';
}
```

- [ ] **Step 2: Verify type-check passes**

```bash
docker-compose exec -T frontend-dev npm run check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api/admin.ts
git commit -m "feat(api-client): completeness-check client helpers"
```

---

## Task 12: Build the `CompletenessModal.svelte` component

**Files:**
- Create: `frontend/src/lib/components/admin/CompletenessModal.svelte`

- [ ] **Step 1: Create the component**

Create `frontend/src/lib/components/admin/CompletenessModal.svelte`:

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchCompletenessCheck, completenessCsvUrl } from '$lib/api/admin';
	import type { EntryCompletenessResult } from '$lib/types/admin';

	export let open = false;
	export let onClose: () => void;

	let loading = false;
	let error: string | null = null;
	let allResults: EntryCompletenessResult[] = [];

	$: incompletes = allResults.filter((r) => !r.is_complete);
	$: allComplete = !loading && error === null && allResults.length > 0 && incompletes.length === 0;

	async function load() {
		loading = true;
		error = null;
		try {
			allResults = await fetchCompletenessCheck(false);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load completeness check';
			allResults = [];
		} finally {
			loading = false;
		}
	}

	$: if (open) load();

	function close() {
		onClose();
	}

	function downloadCsv() {
		window.location.href = completenessCsvUrl();
	}
</script>

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-base-300/70 backdrop-blur"
		role="dialog"
		aria-modal="true"
		aria-labelledby="completeness-title"
	>
		<div class="bg-base-200 rounded-box shadow-xl w-full max-w-3xl max-h-[85vh] flex flex-col">
			<header class="flex items-center justify-between p-4 border-b border-base-300">
				<h2 id="completeness-title" class="font-display text-xl tracking-wide">
					Entry completeness check
				</h2>
				<div class="flex items-center gap-2">
					<button
						class="btn btn-sm btn-outline"
						on:click={downloadCsv}
						disabled={loading || incompletes.length === 0}
					>
						Download CSV
					</button>
					<button class="btn btn-sm btn-ghost" on:click={close} aria-label="Close">✕</button>
				</div>
			</header>

			<div class="flex-1 overflow-y-auto p-4">
				{#if loading}
					<div class="flex justify-center py-12">
						<span class="loading loading-spinner loading-lg text-primary"></span>
					</div>
				{:else if error}
					<div class="text-error text-center py-8">{error}</div>
				{:else if allComplete}
					<div class="bg-success/20 border border-success/40 rounded-btn p-4 text-center">
						<p class="text-success font-semibold">All eligible entries are complete ✓</p>
						<p class="text-base-content/55 text-sm mt-1">
							{allResults.length} eligible entries checked — no gaps.
						</p>
					</div>
				{:else if incompletes.length > 0}
					<p class="text-sm text-base-content/70 mb-3">
						{incompletes.length} of {allResults.length} eligible entries have missing picks. Download
						the CSV to chase up.
					</p>
					<table class="table table-sm">
						<thead>
							<tr>
								<th>Entry</th>
								<th>User</th>
								<th class="text-right">Missing matches</th>
								<th class="text-right">Missing bracket</th>
								<th class="text-right">Missing bonus</th>
							</tr>
						</thead>
						<tbody>
							{#each incompletes as r (r.entry_id)}
								<tr>
									<td>{r.entry_name}</td>
									<td>
										<div class="text-sm">{r.user_name}</div>
										<div class="text-xs text-base-content/55">{r.user_email}</div>
									</td>
									<td class="text-right {r.missing_match_picks > 0 ? 'text-error' : ''}"
										>{r.missing_match_picks}</td
									>
									<td class="text-right {r.missing_bracket_picks > 0 ? 'text-error' : ''}"
										>{r.missing_bracket_picks}</td
									>
									<td class="text-right {r.missing_bonus_picks > 0 ? 'text-error' : ''}"
										>{r.missing_bonus_picks}</td
									>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<div class="text-center py-8 text-base-content/55">No eligible entries to check.</div>
				{/if}
			</div>
		</div>
	</div>
{/if}
```

- [ ] **Step 2: Verify the file compiles**

```bash
docker-compose exec -T frontend-dev npm run check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/admin/CompletenessModal.svelte
git commit -m "feat(admin): add CompletenessModal component"
```

---

## Task 13: Wire the button into `/admin/entries`

**Files:**
- Modify: `frontend/src/routes/admin/entries/+page.svelte`

- [ ] **Step 1: Read the existing file**

```bash
# Open frontend/src/routes/admin/entries/+page.svelte and locate the
# top-of-page action area (look for any existing buttons near the page
# header).
```

- [ ] **Step 2: Add the import + state**

In the script section of `frontend/src/routes/admin/entries/+page.svelte`, add:

```typescript
import CompletenessModal from '$lib/components/admin/CompletenessModal.svelte';

let completenessModalOpen = false;
```

- [ ] **Step 3: Add the button**

In the markup, near the page title or the existing action area, add the button:

```svelte
<button
	class="btn btn-sm btn-outline"
	on:click={() => (completenessModalOpen = true)}
>
	Run completeness check
</button>

<CompletenessModal
	open={completenessModalOpen}
	onClose={() => (completenessModalOpen = false)}
/>
```

The exact placement depends on the page's existing layout — place it near other top-level admin actions. If no such area exists, place it directly under the page title.

- [ ] **Step 4: Verify it renders**

```bash
docker-compose exec -T frontend-dev npm run check
```

Expected: 0 errors.

Manually open `http://localhost:5173/admin/entries` (logged in as admin), click the button, confirm the modal opens. Empty state, populated state (if any incompletes exist), and CSV download all work.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/admin/entries/+page.svelte
git commit -m "feat(admin): wire completeness-check button on /admin/entries"
```

---

# Group E — Pre-deploy: run against prod data

The whole point of bundling the completeness check first is to find real gaps before V4 ships. This is a manual operator task; record outcomes here for the team.

## Task 14: Run completeness against prod and chase gaps

**Files:** none — this is an operations task.

- [ ] **Step 1: Push the branch to make it available on prod's git pull**

NOTE: Do NOT push until the user explicitly authorizes pushing. This task only proceeds with user approval since it's affecting production.

When approved:

```bash
git push -u origin claude/results-page-revamp
```

- [ ] **Step 2: Deploy a feature-branch preview** (only if the admin user agrees)

If the user wants to run this against prod without merging:

```bash
ssh root@167.235.145.76 'cd /opt/predictor && git fetch origin claude/results-page-revamp && git checkout claude/results-page-revamp && docker compose --profile prod up -d --build backend'
```

- [ ] **Step 3: Run the check from the prod backend**

```bash
ssh root@167.235.145.76 'curl -s -H "Cookie: <admin-session-cookie>" https://wc26.heyvinay.com/api/admin/entries/completeness-check.csv > /tmp/completeness.csv && head -50 /tmp/completeness.csv'
```

Or, more simply, open `https://wc26.heyvinay.com/admin/entries` in a browser, click "Run completeness check," download CSV.

- [ ] **Step 4: Triage the CSV**

Review the rows. For each incomplete entry:
- Contact the user by email or Slack with the specific gap list.
- Give a deadline (before tournament-live cutover).
- Track responses outside this plan.

- [ ] **Step 5: Re-run until clean OR document accepted exceptions**

Once the CSV is empty (or the remaining rows are accepted-as-disabled-or-withdrawn), Phase 1 is done. Document the final state in the team chat / notes.

If you redeployed `main` to revert the feature-branch test, run:

```bash
ssh root@167.235.145.76 'cd /opt/predictor && git checkout main && docker compose --profile prod up -d --build backend'
```

- [ ] **Step 6: No commit** — this task is operational.

---

# Phase 1 close-out

After Task 14 lands:

- All eligible entries are complete OR documented exceptions exist.
- Branch contains: 4 backend tasks committed (schema/helper/wiring × 2 + completeness service + 2 endpoints), 4 frontend tasks committed (types, client, modal, button).
- Total expected commits on the branch: ~12.
- No version bump yet — that lands at the end of Phase 3 alongside the V4 UI.
- No production deploy unless the user explicitly wants a Phase 1-only intermediate deploy. (Discuss with the user before merging anything to main.)

**Hand off to Phase 2** — the V4 `/results` page core. The schema fields (`points`, `rank`) are now ready for the frontend to consume.

---

# Self-review checklist (engineer-facing)

Before declaring Phase 1 done, verify:

**Automated tests:**
- [ ] `backend/tests/test_match_predictions_points.py` — all PASS (schema + pure-helper)
- [ ] `backend/tests/test_community_predictions_rank.py` — all PASS (schema)
- [ ] `backend/tests/test_completeness.py` — all PASS (schema + DB-level bulk-completeness)
- [ ] Existing test suites unaffected (run `pytest backend/tests/` and confirm no regressions)
- [ ] `npm run check` reports 0 errors

**Manual smoke (since Phase 1 leans on smoke for route wiring per the testing approach):**
- [ ] `GET /api/entries/{id}/predictions/matches` returns `points` populated for FINISHED fixtures, `null` for SCHEDULED/LIVE.
- [ ] `GET /api/predictions/matches/{id}/community` returns `rank` (int or null) on every prediction row.
- [ ] `GET /api/admin/entries/completeness-check` returns 200 for admin, 403 for non-admin.
- [ ] `GET /api/admin/entries/completeness-check.csv` returns 200 + CSV body for admin, 403 for non-admin. CSV body contains only incompletes.
- [ ] `/admin/entries` button opens modal; CSV download button triggers file download; "all complete" empty state renders when no incompletes exist.

**Code-review gates:**
- [ ] No new `# type: ignore` or `eslint-disable` introduced.
- [ ] Bulk-agreement is fetched ONCE per `list_match_predictions` call (not per fixture). Verify by reading the route source — the call to `compute_agreements` should appear exactly once and `fixture_ids=None`.
- [ ] Leaderboard fetch in `/community` uses the cached path (`calculate_leaderboard(session, phase=None)` — its 30s cache is the perf path).
- [ ] No Phase 2 code paths touched. Grep `is_phase2_active` to confirm — no edits.
- [ ] Branch is clean (no stray uncommitted edits).
- [ ] All commits use conventional-commit prefixes (`feat`, `fix`, `chore`, etc.) per CLAUDE.md.

If any are unchecked, fix before handing off.
